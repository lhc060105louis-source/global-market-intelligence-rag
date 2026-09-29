"""Shared bucket-level six-dimensional aggregation service for customer VOC.

This module defines the aggregation boundary between ``analysis_results`` and downstream consumers:

1. Build business buckets by brand, vehicle model, region, journey stage, channel, and language.
2. Adapt each bucket to the legacy standard signal format.
3. Call the legacy ``SignalProcessor`` and its six dimension functions.
4. Shape legacy engine results into a bucket-level contract shared by dashboards and the RAG Hub.

``c_rag_push.py`` is downstream and consumes bucket-level results only. It does not read raw analysis
rows, repeat bucketing, or calculate six-dimensional metrics.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any


# Stable business scope defined by RAG PRD v5. Date is outside the outer scope; the legacy engine
# still buckets by published_date within AggKey for time-series calculations.
BUCKET_FIELDS = ("brand", "model", "region", "journey_stage", "channel", "language")
DIMENSION_NAMES = (
    "journey_sentiment",
    "nps_prediction",
    "key_complaints",
    "brand_attitude",
    "recall_risk",
    "legal_risk",
)
UNKNOWN_DIMENSION_VALUES = {
    "", "-", "n/a", "na", "none", "null", "unknown", "unknown_brand",
    "unknown_model", "unidentified", "unknown",
}
BUCKET_DEFAULTS = {
    "brand": "UNKNOWN_BRAND",
    "model": "UNKNOWN_MODEL",
    "region": "UNKNOWN",
    "journey_stage": "full_journey",
    "channel": "mixed",
    "language": "UNKNOWN",
}

_LEGACY_ENGINE_DIR = Path(__file__).resolve().parents[2] / "six-dimensions-v3.0"
_LEGACY_CORE_MODULE = "_c_voc_legacy_six_core"
_LEGACY_DIMENSIONS_MODULE = "_c_voc_legacy_six_dimensions"
_LEGACY_ENGINE: tuple[ModuleType, ModuleType] | None = None
_LEGACY_LOCK = RLock()


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy six-dimension module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_legacy_engine() -> tuple[ModuleType, ModuleType]:
    """Load the legacy engine while isolating its top-level ``from core import ...`` imports."""
    global _LEGACY_ENGINE
    with _LEGACY_LOCK:
        if _LEGACY_ENGINE is not None:
            return _LEGACY_ENGINE

        core_path = _LEGACY_ENGINE_DIR / "core.py"
        dimensions_path = _LEGACY_ENGINE_DIR / "dimensions.py"
        if not core_path.is_file() or not dimensions_path.is_file():
            raise FileNotFoundError(
                f"Legacy six-dimension engine is incomplete: {core_path}, {dimensions_path}"
            )

        legacy_core = _load_module(_LEGACY_CORE_MODULE, core_path)
        original_core = sys.modules.get("core")
        sys.modules["core"] = legacy_core
        try:
            legacy_dimensions = _load_module(_LEGACY_DIMENSIONS_MODULE, dimensions_path)
        finally:
            if original_core is None:
                sys.modules.pop("core", None)
            else:
                sys.modules["core"] = original_core

        _LEGACY_ENGINE = (legacy_core, legacy_dimensions)
        return _LEGACY_ENGINE


def _clean(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text if text else default


def normalize_bucket_value(value: Any, field: str) -> str:
    """Normalize display values used to define business buckets."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.casefold() in UNKNOWN_DIMENSION_VALUES:
        return BUCKET_DEFAULTS[field]

    if field == "brand":
        return {
            "tesla": "Tesla", "byd": "BYD", "mg": "MG", "hyundai": "Hyundai", "nio": "NIO",
        }.get(text.casefold(), text)
    if field == "model":
        compact = re.sub(r"[\s_-]+", "", text.casefold())
        return {
            "model3": "Model 3", "modely": "Model Y", "modelx": "Model X", "models": "Model S",
            "seal": "Seal", "mg4ev": "MG4 EV", "ioniq5": "Ioniq 5", "el6": "EL6",
        }.get(compact, text)
    if field == "channel":
        return text.casefold()
    if field == "journey_stage":
        return text.casefold()
    if field == "language":
        aliases = {
            "cn": "Chinese", "zh": "Chinese", "zh-cn": "Chinese",
            "chinese": "Chinese", "Chinese": "Chinese", "Chinese": "Chinese",
        }
        upper_text = text.upper()
        return aliases.get(
            text.casefold(),
            upper_text if upper_text in {"DE", "EN", "ES", "FR", "IT"} else text,
        )
    return text.upper() if len(text) <= 3 and text.isascii() else text


def normalize_event_for_bucket(event: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(event)
    for field in BUCKET_FIELDS:
        value = event.get(field)
        if field == "model" and value in (None, ""):
            value = event.get("vehicle_model")
        normalized[field] = normalize_bucket_value(value, field)
    return normalized


def group_events(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split an analysis window using the six-field RAG business scope."""
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        normalized = normalize_event_for_bucket(event)
        key = tuple(normalized[field].casefold() for field in BUCKET_FIELDS)
        buckets[key].append(normalized)
    return [buckets[key] for key in sorted(buckets)]


def _safe_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", value.strip().lower())
    return text.strip("-") or "unknown"


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or text.casefold() == "unknown":
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.combine(date.fromisoformat(text), time.min, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _event_time(event: dict[str, Any]) -> datetime | None:
    return _parse_datetime(event.get("published_at")) or _parse_datetime(event.get("published_date"))


def _period(events: list[dict[str, Any]]) -> tuple[str, str, str]:
    times = [item for item in (_event_time(event) for event in events) if item is not None]
    if not times:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return now.isoformat(), now.isoformat(), now.date().isoformat()
    start = min(times).replace(microsecond=0)
    end = max(times).replace(microsecond=0)
    return start.isoformat(), end.isoformat(), end.date().isoformat()


def _first_hit_at(events: list[dict[str, Any]]) -> str | None:
    times = [item for item in (_event_time(event) for event in events) if item is not None]
    return min(times).replace(microsecond=0).isoformat() if times else None


def _valid_source_url(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        url = str(event.get("source_url") or "").strip()
        if url.startswith(("http://", "https://")):
            return url
    return None


def _dominant(events: list[dict[str, Any]], field: str, default: str) -> str:
    values = [_clean(event.get(field), "") for event in events]
    values = [
        value for value in values
        if value and value.upper() not in {"UNKNOWN", "UNKNOWN_BRAND", "UNKNOWN_MODEL"}
    ]
    return Counter(values).most_common(1)[0][0] if values else default


def _sentiment_bucket(label: Any) -> str:
    text = str(label or "").casefold()
    if any(marker in text for marker in ("positive", "satisfied", "good")):
        return "positive"
    if any(marker in text for marker in ("negative", "complaint", "strongly_negative")):
        return "negative"
    return "neutral"


def _ratio(value: int | float, total: int | float) -> float:
    return round(float(value) / float(total), 4) if total else 0.0


def _emotion_distribution(events: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(_clean(event.get("sentiment_label"), "unknown") for event in events))


def traceable_events(events: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "job_id": event.get("job_id"),
            "source_id": event.get("source_id"),
            "source": event.get("source"),
            "source_url": event.get("source_url", ""),
            "published_at": event.get("published_at") or event.get("published_date"),
            "channel": event.get("channel"),
            "text": event.get("text", ""),
            "sentiment_label": event.get("sentiment_label"),
            "risk_keywords": event.get("risk_keywords", []),
            "brand": event.get("brand"),
            "model": event.get("model"),
            "region": event.get("region"),
        }
        for event in events[:limit]
    ]


def _topic_items(event: dict[str, Any]) -> list[dict[str, Any]]:
    topics = event.get("topics")
    return [item for item in topics if isinstance(item, dict)] if isinstance(topics, list) else []


def _topic_name(event: dict[str, Any]) -> str:
    for topic in _topic_items(event):
        name = _clean(topic.get("name") or topic.get("topic_name") or topic.get("topic_id"), "")
        if name:
            return name
    return "vehicle"


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _legacy_sentiment_label(event: dict[str, Any]) -> str:
    return _sentiment_bucket(event.get("sentiment_label"))


def _legacy_emotion_names(event: dict[str, Any], legacy_core: ModuleType) -> list[str]:
    valid = set(legacy_core.EMOTION_28)
    raw_values: list[Any] = []
    raw = event.get("sentiment_spec")
    raw_values.extend(raw if isinstance(raw, list) else [raw])
    if isinstance(event.get("emotions"), list):
        raw_values.extend(
            item.get("name") if isinstance(item, dict) else item
            for item in event["emotions"]
        )
    aliases = {
        "positive": "satisfaction", "negative": "complaint", "neutral": "calm", "satisfied": "satisfaction",
        "happy": "happiness", "complaint": "complaint", "angry": "anger", "calm": "calm",
    }
    names: list[str] = []
    for value in raw_values:
        text = str(value or "").strip()
        mapped = text if text in valid else aliases.get(text.casefold())
        if mapped and mapped not in names:
            names.append(mapped)
    if not names:
        names = [{"positive": "satisfaction", "negative": "complaint", "neutral": "calm"}[_legacy_sentiment_label(event)]]
    return names


def _legacy_entities(event: dict[str, Any], model: str) -> list[dict[str, Any]]:
    """Convert a current standardized entity to the format expected by the legacy core."""
    entities: list[dict[str, Any]] = []
    raw_entities = event.get("entities") if isinstance(event.get("entities"), list) else []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        entity_type = str(item.get("type") or "other")
        if entity_type in {"vehicle model", "vehicle_model"}:
            continue
        name = _clean(item.get("name") or item.get("normalized_name"), "")
        if name:
            entities.append({"type": entity_type, "name": name})
    # Bucket fields are authoritative; do not rely on legacy entity extraction to determine the vehicle model.
    entities.append({"type": "vehicle_model", "name": model})

    text = " ".join([
        str(event.get("text") or ""),
        " ".join(str(item) for item in event.get("risk_keywords", []) or []),
    ])
    if event.get("recall_keyword_hit"):
        if not any(item.get("type") in {"component", "part"} for item in entities):
            entities.append({"type": "part", "name": _topic_name(event)})
        # Local rules have already determined the match; translate it to the legacy rule vocabulary here.
        entities.append({"type": "symptom", "name": "recall"})
    if event.get("rights_keyword_hit"):
        intent_markers = (
            "lawyer", "solicitor", "legal action", "lawsuit", "class action",
            "group litigation", "sue", "court", "lawyer", "lawsuit",
        )
        entities.append({
            "type": "symptom",
            "name": "litigation" if _contains_any(text, intent_markers) else "compensation",
        })
    return entities


def _legacy_signal(
    event: dict[str, Any],
    *,
    model: str,
    language_token: str,
    fallback_time: datetime,
    legacy_core: ModuleType,
    index: int,
) -> dict[str, Any]:
    published_at = _event_time(event) or fallback_time
    names = _legacy_emotion_names(event, legacy_core)
    share = 1.0 / len(names)
    return {
        "source_id": str(event.get("source_id") or f"voc-signal-{index}"),
        "published_at": published_at.isoformat(),
        "language": language_token,
        "channel": _clean(event.get("channel"), "mixed"),
        "journey_stage": _clean(event.get("journey_stage"), "full_journey"),
        "sentiment_label": _legacy_sentiment_label(event),
        "sentiment_strength": max(1, min(5, int(event.get("sentiment_strength") or 1))),
        "emotion_28": {
            emotion: (share if emotion in names else 0.0)
            for emotion in legacy_core.EMOTION_28
        },
        "entities": _legacy_entities(event, model),
        "topics": _topic_items(event),
    }


def _legacy_processor(
    events: list[dict[str, Any]],
) -> tuple[ModuleType, ModuleType, Any, str, str, str, datetime, datetime]:
    legacy_core, legacy_dimensions = _load_legacy_engine()
    first = events[0]
    model, brand, region = first["model"], first["brand"], first["region"]
    period_start, period_end, _ = _period(events)
    start_time = _parse_datetime(period_start) or datetime.now(timezone.utc)
    end_time = _parse_datetime(period_end) or start_time

    # The legacy core infers region only from language and brand only from model. Use a dedicated
    # mapping token for each business bucket to inject actual fields into the legacy aggregator.
    language_tokens: dict[str, str] = {}
    for event in events:
        language = _clean(event.get("language"), "unknown")
        language_tokens.setdefault(
            language,
            f"__voc_region_{_safe_id(region)}__language_{_safe_id(language)}",
        )
    previous_regions = {
        token: legacy_core.LANGUAGE_TO_REGION.get(token)
        for token in language_tokens.values()
    }
    previous_brand = legacy_core.MODEL_TO_BRAND.get(model)
    with _LEGACY_LOCK:
        for token in language_tokens.values():
            legacy_core.LANGUAGE_TO_REGION[token] = region
        legacy_core.MODEL_TO_BRAND[model] = brand
        processor = legacy_core.SignalProcessor()
        try:
            for index, event in enumerate(events):
                processor.process(
                    _legacy_signal(
                        event,
                        model=model,
                        language_token=language_tokens[_clean(event.get("language"), "unknown")],
                        fallback_time=end_time,
                        legacy_core=legacy_core,
                        index=index,
                    )
                )
        finally:
            for token, previous in previous_regions.items():
                if previous is None:
                    legacy_core.LANGUAGE_TO_REGION.pop(token, None)
                else:
                    legacy_core.LANGUAGE_TO_REGION[token] = previous
            if previous_brand is None:
                legacy_core.MODEL_TO_BRAND.pop(model, None)
            else:
                legacy_core.MODEL_TO_BRAND[model] = previous_brand
    return legacy_core, legacy_dimensions, processor, model, brand, region, start_time, end_time


def _old_counts(processor: Any) -> tuple[int, int, int, int]:
    buckets = list(processor.buckets.values())
    return (
        sum(int(bucket.signal_count) for bucket in buckets),
        sum(int(bucket.positive_count) for bucket in buckets),
        sum(int(bucket.negative_count) for bucket in buckets),
        sum(int(bucket.neutral_count) for bucket in buckets),
    )


def _base_payload(
    events: list[dict[str, Any]], *, dimension: str, result: dict[str, Any], signal_count: int
) -> dict[str, Any]:
    period_start, period_end, business_date = _period(events)
    first = events[0]
    brand, vehicle_model, region, channel = (
        first["brand"], first["model"], first["region"], first["channel"]
    )
    journey_stage = _clean(first.get("journey_stage"), "full_journey")
    language = _clean(first.get("language"), "UNKNOWN")
    scope_id = "voc:{}:{}:{}:{}:{}:{}".format(
        _safe_id(brand), _safe_id(vehicle_model), _safe_id(region),
        _safe_id(journey_stage), _safe_id(channel), _safe_id(language),
    )
    return {
        "scope_id": scope_id,
        "dimension": dimension,
        "brand": brand,
        "vehicle_model": vehicle_model,
        "region": region,
        "journey_stage": journey_stage,
        "channel": channel,
        "language": language,
        "period_start": period_start,
        "period_end": period_end,
        "business_date": business_date,
        "signal_count": signal_count,
        "emotion_distribution": _emotion_distribution(events),
        "result": result,
    }


def _dimension_without_sample_gate(function: Any, *args: Any, **kwargs: Any) -> Any:
    """Bucket-level RAG still requires all six results, so bypass the legacy engine sample gate only here.

    Calculations still come from the legacy engine. The original gate remains for direct dashboard/API calls.
    """
    result = function(*args, **kwargs)
    if result in (None, []) and getattr(function, "__wrapped__", None):
        return function.__wrapped__(*args, **kwargs)
    return result


def _percent_ratio(value: Any) -> float:
    try:
        return round(float(value) / 100, 4)
    except (TypeError, ValueError):
        return 0.0


def _trend_direction(value: Any) -> str:
    text = str(value or "").casefold()
    if any(marker in text for marker in ("up", "increasing", "worsening")):
        return "up"
    if any(marker in text for marker in ("down", "decreasing", "improving")):
        return "down"
    return "stable"


def _trend_from_points(points: list[dict[str, Any]]) -> str:
    if len(points) < 2:
        return "stable"
    ordered = sorted(points, key=lambda item: str(item.get("date") or ""))
    first = float(ordered[0].get("negative_ratio") or 0.0)
    last = float(ordered[-1].get("negative_ratio") or 0.0)
    if last > first + 5:
        return "up"
    if last < first - 5:
        return "down"
    return "stable"


def _topic_intensity(events: list[dict[str, Any]], topic: str) -> float:
    scores: list[float] = []
    for event in events:
        for item in _topic_items(event):
            name = _clean(item.get("name") or item.get("topic_name") or item.get("topic_id"), "")
            if name == topic or name.casefold() == topic.casefold():
                try:
                    scores.append(float(event.get("sentiment_score") or 0.0))
                except (TypeError, ValueError):
                    scores.append(0.0)
                break
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _topic_rows(events: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        topic = _clean(row.get("topic"), "unknown")
        result.append({
            "topic_id": _safe_id(topic),
            "topic_name": topic,
            "part": topic,
            "frequency": int(row.get("signal_count") or 0),
            "average_sentiment_intensity": _topic_intensity(events, topic),
            "trend_direction": _trend_direction(row.get("trend")),
        })
    return result


def _call_recall_dimension(
    legacy_core: ModuleType,
    legacy_dimensions: ModuleType,
    processor: Any,
    *,
    model: str,
    events: list[dict[str, Any]],
    end_time: datetime,
    threshold: int | None,
) -> tuple[dict[str, Any], str]:
    recall_events = [event for event in processor.risk_events if event.hit_type == "recall"]
    part = (
        Counter(event.part_name for event in recall_events).most_common(1)[0][0]
        if recall_events else _topic_name(events[0])
    )
    previous_threshold = legacy_core.PART_SAFETY_THRESHOLDS.get(part)
    if threshold is not None:
        legacy_core.PART_SAFETY_THRESHOLDS[part] = max(1, int(threshold))
    try:
        result = legacy_dimensions.recall_alert(
            processor.risk_events, model=model, part=part, now=end_time
        )
    finally:
        if threshold is not None:
            if previous_threshold is None:
                legacy_core.PART_SAFETY_THRESHOLDS.pop(part, None)
            else:
                legacy_core.PART_SAFETY_THRESHOLDS[part] = previous_threshold
    return result, part


def _call_legal_dimension(
    legacy_dimensions: ModuleType,
    processor: Any,
    *,
    brand: str,
    region: str,
    start_time: datetime,
    end_time: datetime,
    threshold: int | None,
) -> dict[str, Any]:
    previous_threshold = legacy_dimensions.LAWSUIT_GENERAL_THRESHOLD
    if threshold is not None:
        legacy_dimensions.LAWSUIT_GENERAL_THRESHOLD = max(1, int(threshold))
    try:
        return legacy_dimensions.legal_risk_alert(
            processor.risk_events,
            brand=brand,
            region=region,
            date_from=start_time,
            date_to=end_time,
        )
    finally:
        legacy_dimensions.LAWSUIT_GENERAL_THRESHOLD = previous_threshold


def _bucket_result(
    events: list[dict[str, Any]], *, recall_threshold: int | None, legal_threshold: int | None
) -> dict[str, Any]:
    (
        legacy_core, legacy_dimensions, processor, model, brand, region, start_time, end_time
    ) = _legacy_processor(events)
    total, positive, negative, neutral = _old_counts(processor)
    period_start, period_end, business_date = _period(events)
    date_from, date_to = start_time.date().isoformat(), end_time.date().isoformat()
    date_to_exclusive = (end_time.date() + timedelta(days=1)).isoformat()

    # Dimension 1: the legacy engine creates a trend by customer journey stage and date; bucket views retain original label counts.
    stages = sorted({_clean(event.get("journey_stage"), "full_journey") for event in events})
    journey_points: dict[str, list[dict[str, Any]]] = {}
    for stage in stages:
        journey_points[stage] = _dimension_without_sample_gate(
            legacy_dimensions.journey_curve,
            processor.buckets,
            model=model,
            region=region,
            journey_stage=stage,
            date_from=date_from,
            date_to=date_to,
        ) or []
    flat_points = [point for points in journey_points.values() for point in points]
    if flat_points:
        point_total = sum(int(point.get("signal_count") or 0) for point in flat_points)
        pos_ratio = sum(float(point.get("positive_ratio") or 0) * int(point.get("signal_count") or 0) for point in flat_points)
        neg_ratio = sum(float(point.get("negative_ratio") or 0) * int(point.get("signal_count") or 0) for point in flat_points)
        neu_ratio = sum(float(point.get("neutral_ratio") or 0) * int(point.get("signal_count") or 0) for point in flat_points)
        journey_ratios = {
            "positive_ratio": round(pos_ratio / point_total / 100, 4) if point_total else 0.0,
            "negative_ratio": round(neg_ratio / point_total / 100, 4) if point_total else 0.0,
            "neutral_ratio": round(neu_ratio / point_total / 100, 4) if point_total else 0.0,
        }
    else:
        journey_ratios = {
            "positive_ratio": _ratio(positive, total),
            "negative_ratio": _ratio(negative, total),
            "neutral_ratio": _ratio(neutral, total),
        }
    journey_view: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        journey_view[_clean(event.get("journey_stage"), "full_journey")][_clean(event.get("sentiment_label"), "unknown")] += 1
    journey_result = {
        **journey_ratios,
        "trend_direction": _trend_from_points(flat_points),
        "granularity": "job_bucket",
        "journey_curve": journey_points,
    }

    # Dimension 2: reuse the legacy engine nps_predict result; only the bucket-level gate is bypassed here.
    old_nps = _dimension_without_sample_gate(
        legacy_dimensions.nps_predict, processor.buckets, model=model, region=region, today=end_time.date()
    )
    nps_result = {
        "nps_value": float(old_nps["nps_score"]) if old_nps else 0.0,
        "change_from_previous": float(old_nps.get("change_vs_30d_ago") or 0.0) if old_nps else 0.0,
        "promoter_ratio": _percent_ratio(old_nps.get("promoter_ratio")) if old_nps else 0.0,
        "passive_ratio": _percent_ratio(old_nps.get("passive_ratio")) if old_nps else 0.0,
        "detractor_ratio": _percent_ratio(old_nps.get("detractor_ratio")) if old_nps else 0.0,
    }
    if not old_nps:
        nps_result["sample_gate"] = "no_signal"

    # Dimension 3: the legacy engine filters and ranks complaint topics over the previous two weeks.
    old_complaints = _dimension_without_sample_gate(
        legacy_dimensions.complaint_ranking,
        processor.buckets,
        model=model,
        region=region,
        date_from=date_from,
        date_to=date_to,
        journey_stage=None,
        top_n=10,
        today=end_time.date(),
    ) or []
    complaints = _topic_rows(events, old_complaints)

    # Dimension 4: brand sentiment uses the legacy brand-window function.
    old_attitude = _dimension_without_sample_gate(
        legacy_dimensions.brand_sentiment,
        processor.buckets,
        brand=brand,
        region=region,
        date_from=date_from,
        date_to=date_to_exclusive,
    )
    if old_attitude:
        attitude_text = str(old_attitude.get("attitude") or "").casefold()
        attitude = "positive" if "positive" in attitude_text else "negative" if "negative" in attitude_text else "neutral"
        attitude_result = {
            "attitude": attitude,
            "positive_ratio": _percent_ratio(old_attitude.get("positive_ratio")),
            "negative_ratio": _percent_ratio(old_attitude.get("negative_ratio")),
            "neutral_ratio": _percent_ratio(old_attitude.get("neutral_ratio")),
            "trend_direction": _trend_direction(old_attitude.get("trend")),
            "emotion_28_ratio": old_attitude.get("emotion_28_ratio") or {},
        }
    else:
        attitude_result = {
            "attitude": max(
                ("positive", "negative", "neutral"),
                key={"positive": positive, "negative": negative, "neutral": neutral}.get,
            ),
            "positive_ratio": _ratio(positive, total),
            "negative_ratio": _ratio(negative, total),
            "neutral_ratio": _ratio(neutral, total),
            "trend_direction": "stable",
        }

    # Dimensions 5/6: risk fields use the legacy engine RiskEvent pipeline and alert functions.
    old_recall, recall_part = _call_recall_dimension(
        legacy_core,
        legacy_dimensions,
        processor,
        model=model,
        events=events,
        end_time=end_time,
        threshold=recall_threshold,
    )
    recall_events = [event for event in events if event.get("recall_keyword_hit")]
    recall_result = {
        "part": recall_part,
        "risk_type": "recall_signal",
        "hit_count": int(old_recall.get("hit_count") or 0),
        "threshold": int(old_recall.get("threshold") or 0),
        "threshold_exceeded": bool(old_recall.get("alert_triggered")),
        "first_hit_at": (
            old_recall.get("first_hit_time").isoformat()
            if old_recall.get("first_hit_time")
            else _first_hit_at(recall_events or events)
        ),
        "risk_status": "open" if old_recall.get("alert_triggered") else "normal",
        "items": traceable_events(recall_events),
        "emotion_28_ratio": old_recall.get("emotion_28_ratio") or {},
    }

    old_legal = _call_legal_dimension(
        legacy_dimensions,
        processor,
        brand=brand,
        region=region,
        start_time=start_time,
        end_time=end_time,
        threshold=legal_threshold,
    )
    legal_level = {"High": "high", "Medium": "medium", "Low": "low", "None": "none"}.get(
        str(old_legal.get("risk_level") or ""), "none"
    )
    legal_events = [event for event in events if event.get("rights_keyword_hit")]
    legal_threshold_value = max(
        1,
        int(legal_threshold)
        if legal_threshold is not None
        else int(getattr(legacy_dimensions, "LAWSUIT_GENERAL_THRESHOLD", 5)),
    )
    legal_result = {
        "part": "consumer_rights",
        "risk_type": "legal_action_signal",
        "hit_count": int(old_legal.get("hit_count") or 0),
        "threshold": legal_threshold_value,
        "threshold_exceeded": bool(old_legal.get("alert_triggered")),
        "risk_level": legal_level,
        "risk_status": "open" if old_legal.get("alert_triggered") else "normal",
        "items": traceable_events(legal_events),
        "emotion_28_ratio": old_legal.get("emotion_28_ratio") or {},
    }

    def make_payload(dimension: str, result: dict[str, Any]) -> dict[str, Any]:
        return _base_payload(events, dimension=dimension, result=result, signal_count=total)

    payloads = {
        "journey_sentiment": make_payload("journey_sentiment", journey_result),
        "nps_prediction": make_payload("nps_prediction", nps_result),
        "key_complaints": make_payload("key_complaints", {"complaints": complaints}),
        "brand_attitude": make_payload("brand_attitude", attitude_result),
        "recall_risk": make_payload("recall_risk", recall_result),
        "legal_risk": make_payload("legal_risk", legal_result),
    }
    return {
        "scope_id": payloads["journey_sentiment"]["scope_id"],
        "brand": brand,
        "vehicle_model": model,
        "region": region,
        "channel": events[0]["channel"],
        "period_start": period_start,
        "period_end": period_end,
        "business_date": business_date,
        "signal_count": total,
        "source_url": _valid_source_url(events),
        "dimensions": payloads,
        "view": {
            "journey_sentiment_curve": {stage: dict(counter) for stage, counter in journey_view.items()},
            "complaint_ranking": [
                {"name": row["topic_name"], "count": row["frequency"]} for row in complaints
            ],
            "brand_attitude": {
                brand: dict(Counter(_clean(event.get("sentiment_label"), "unknown") for event in events))
            },
            "recall_warning": {"count": recall_result["hit_count"], "items": recall_events},
            "rights_risk": {"count": legal_result["hit_count"], "items": legal_events},
        },
    }


def _threshold(value: int | None, env_name: str) -> int | None:
    if value is not None:
        return max(1, int(value))
    raw = os.getenv(env_name)
    return max(1, int(raw)) if raw else None


def build_bucket_six_dimensions(
    events: list[dict[str, Any]], *, recall_threshold: int | None = None, legal_threshold: int | None = None
) -> list[dict[str, Any]]:
    """Call the legacy engine in each business bucket to generate all six dimensions."""
    if not events:
        return []
    resolved_recall_threshold = _threshold(recall_threshold, "C_RAG_RECALL_THRESHOLD")
    resolved_legal_threshold = _threshold(legal_threshold, "C_RAG_LEGAL_THRESHOLD")
    return [
        _bucket_result(
            bucket_events,
            recall_threshold=resolved_recall_threshold,
            legal_threshold=resolved_legal_threshold,
        )
        for bucket_events in group_events(events)
    ]


def _source_version(conn, job_id: int) -> int:
    row = conn.execute(
        """
        SELECT MAX(a.id) AS max_id
        FROM analysis_results a
        JOIN cleaned_items c ON c.id = a.cleaned_item_id
        JOIN raw_items r ON r.id = c.raw_item_id
        WHERE r.job_id = ?
        """,
        (job_id,),
    ).fetchone()
    return max(1, int(row["max_id"] or job_id) + 1)


def build_job_bucket_six_dimensions(
    conn,
    job_id: int,
    *,
    recall_threshold: int | None = None,
    legal_threshold: int | None = None,
) -> list[dict[str, Any]]:
    """Generate bucket-level six-dimensional results with source metadata from a job analysis."""
    from insight_service import analysis_events

    events = analysis_events(conn, job_id=job_id)
    buckets = build_bucket_six_dimensions(
        events,
        recall_threshold=recall_threshold,
        legal_threshold=legal_threshold,
    )
    source_version = _source_version(conn, job_id)
    source_updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for bucket in buckets:
        bucket["job_id"] = job_id
        bucket["source_version"] = source_version
        bucket["source_updated_at"] = source_updated_at
    return buckets


def _combined_nps(bucket_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(bucket.get("signal_count") or 0) for bucket in bucket_results)
    score_sum = 0.0
    for bucket in bucket_results:
        result = ((bucket.get("dimensions") or {}).get("nps_prediction") or {}).get("result") or {}
        score_sum += float(result.get("nps_value") or 0.0) * int(bucket.get("signal_count") or 0)
    return {"score": round(score_sum / total, 2) if total else 0.0, "basis": total}


def combine_bucket_views(bucket_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate bucket-level results into the overall six-dimensional structure used by the dashboard."""
    journey: dict[str, Counter[str]] = defaultdict(Counter)
    complaint_counter: Counter[str] = Counter()
    brand_attitude: dict[str, Counter[str]] = defaultdict(Counter)
    recall_count = rights_count = 0
    recall_items: list[dict[str, Any]] = []
    rights_items: list[dict[str, Any]] = []

    for bucket in bucket_results:
        view = bucket.get("view") or {}
        for stage, values in (view.get("journey_sentiment_curve") or {}).items():
            journey[stage].update(values)
        for row in view.get("complaint_ranking") or []:
            complaint_counter[str(row.get("name") or "unknown")] += int(row.get("count") or 0)
        for brand, values in (view.get("brand_attitude") or {}).items():
            brand_attitude[brand].update(values)
        recall = view.get("recall_warning") or {}
        rights = view.get("rights_risk") or {}
        recall_count += int(recall.get("count") or 0)
        rights_count += int(rights.get("count") or 0)
        recall_items.extend(recall.get("items") or [])
        rights_items.extend(rights.get("items") or [])

    return {
        "dimensions": {
            "journey_sentiment_curve": "Customer Journey Sentiment Curve",
            "nps_prediction": "NPS Estimate",
            "complaint_ranking": "Top Complaint Topics",
            "brand_attitude": "Brand Sentiment",
            "recall_warning": "Recall Alert",
            "rights_risk": "Consumer Rights Risk",
        },
        "bucket_count": len(bucket_results),
        "buckets": bucket_results,
        "journey_sentiment_curve": {stage: dict(counter) for stage, counter in journey.items()},
        "nps_prediction": _combined_nps(bucket_results),
        "complaint_ranking": [
            {"name": name, "count": count} for name, count in complaint_counter.most_common(10)
        ],
        "brand_attitude": {brand: dict(counter) for brand, counter in brand_attitude.items()},
        "recall_warning": {"count": recall_count, "items": recall_items[:10]},
        "rights_risk": {"count": rights_count, "items": rights_items[:10]},
    }
