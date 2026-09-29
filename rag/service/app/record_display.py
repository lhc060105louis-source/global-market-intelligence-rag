"""Deterministic presentation fields for knowledge records.

These fields are calculated at response time.  They deliberately do not use
``retrieval_text``: that field is an indexing and traceability representation,
not a reliable source for classifying a record or writing a short summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import json
import re
from typing import Any


DISPLAY_CATEGORIES = frozenset({
    "feedback", "risk_assessment", "risk_alert", "policy", "project", "kol_trend",
})
RISK_STATES = frozenset({"none", "normal", "alert"})

_C_FEEDBACK_TYPES = frozenset({
    "consumer_journey_sentiment",
    "consumer_nps_prediction",
    "consumer_key_complaints",
    "consumer_brand_attitude",
})
_C_RISK_TYPES = frozenset({"consumer_recall_risk", "consumer_legal_risk"})

_JOURNEY_STAGE_LABELS = {
    "pre_sales_awareness": "Pre-sales awareness",
    "pre_sales_consideration": "Pre-sales consideration",
    "purchase": "Purchase",
    "delivery": "Delivery",
    "ownership": "Ownership",
    "after_sales": "After-sales service",
    "after_sales_service": "After-sales service",
    "renewal": "Renewal",
}
_ATTITUDE_LABELS = {
    "positive": "Positive",
    "negative": "Negative",
    "neutral": "Neutral",
    "mixed": "Mixed",
}
_RISK_LABELS = {
    "recall_signal": "Recall risk signal",
    "legal_action_signal": "Legal risk signal",
    "class_action": "Class action risk",
    "overheat": "Overheating risk",
    "battery": "Battery",
    "consumer_rights": "Consumer rights",
    "brand_trust": "Brand trust",
}
_TREND_LABELS = {
    "up": "Increasing",
    "down": "Decreasing",
    "stable": "Stable",
    "increasing": "Increasing",
    "decreasing": "Decreasing",
    "unchanged": "Unchanged",
}


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _format_number(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    if float(number).is_integer():
        return str(int(number))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _format_signed_number(value: Any) -> str | None:
    number = _number(value)
    rendered = _format_number(number)
    if rendered is None:
        return None
    return f"+{rendered}" if number > 0 else rendered


def _format_percent(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    # Upstream contracts have used both ratios (0.6) and percentages (60.0).
    percentage = number * 100 if abs(number) <= 1 else number
    return f"{percentage:.1f}".rstrip("0").rstrip(".") + "%"


def _format_date(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if not isinstance(value, str):
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if match:
        return match.group(0)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date().isoformat()


def _label(value: Any, labels: Mapping[str, str] | None = None) -> str | None:
    value_text = _text(value)
    if not value_text:
        return None
    lookup = labels or {}
    return lookup.get(value_text.casefold(), value_text.replace("_", " "))


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _period_text(payload: Mapping[str, Any]) -> str | None:
    start = _format_date(payload.get("period_start"))
    end = _format_date(payload.get("period_end"))
    if start and end:
        return f"Reporting period: {start} to {end}"
    if start or end:
        return f"Reporting period: {start or end}"
    return None


def _join_clauses(clauses: Sequence[str], *, separator: str = ", ") -> str:
    return separator.join(clause for clause in clauses if clause)


def _journey_summary(payload: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    stage = _label(payload.get("journey_stage"), _JOURNEY_STAGE_LABELS)
    count = _format_number(payload.get("signal_count"))
    if stage and count:
        first = f"{stage}: {count} feedback items"
    elif count:
        first = f"{count} feedback items"
    elif stage:
        first = f"Consumer feedback during {stage}"
    else:
        first = ""

    clauses = [first]
    for key, label in (
        ("positive_ratio", "Positive sentiment: "),
        ("neutral_ratio", "Neutral sentiment: "),
        ("negative_ratio", "Negative sentiment: "),
    ):
        value = _format_percent(result.get(key))
        if value:
            clauses.append(label + value)
    trend = _label(result.get("trend_direction"), _TREND_LABELS)
    if trend:
        clauses.append("Overall trend: " + trend)
    body = _join_clauses(clauses)
    period = _period_text(payload)
    if period:
        body += ("; " if body else "") + period
    return body + "." if body else "No summary available."


def _nps_summary(result: Mapping[str, Any]) -> str:
    first: list[str] = []
    nps = _format_number(result.get("nps_value"))
    change = _format_signed_number(result.get("change_from_previous"))
    if nps:
        first.append(f"NPS forecast: {nps}")
    if change:
        first.append(f"Change from previous period: {change}")
    second: list[str] = []
    for key, label in (
        ("promoter_ratio", "Promoters: "),
        ("passive_ratio", "Passives: "),
        ("detractor_ratio", "Detractors: "),
    ):
        value = _format_percent(result.get(key))
        if value:
            second.append(label + value)
    body = _join_clauses(first, separator="; ")
    if second:
        body += ("; " if body else "") + _join_clauses(second, separator="; ")
    return body + "." if body else "No summary available."


def _key_complaints_summary(result: Mapping[str, Any]) -> str:
    raw_complaints = result.get("complaints")
    if not isinstance(raw_complaints, Sequence) or isinstance(raw_complaints, (str, bytes)):
        return "No summary available."
    complaints = [item for item in raw_complaints if isinstance(item, Mapping)]
    complaints.sort(key=lambda item: _number(item.get("frequency")) or 0, reverse=True)
    details: list[str] = []
    total_frequency = 0.0
    for item in complaints[:3]:
        topic = _text(item.get("part")) or _text(item.get("topic_name"))
        frequency = _format_number(item.get("frequency"))
        trend = _label(item.get("trend_direction"), _TREND_LABELS)
        attributes = []
        if frequency:
            attributes.append(f"{frequency} occurrences")
            total_frequency += float(_number(item.get("frequency")) or 0)
        if trend:
            attributes.append("Trend: " + trend)
        if topic:
            details.append(topic + (f" ({_join_clauses(attributes, separator=', ')})" if attributes else ""))
    if not details:
        return "No summary available."
    body = "Key complaints: " + _join_clauses(details, separator="; ")
    if total_frequency:
        total = _format_number(total_frequency)
        body += f". Top items total {total} occurrences"
    body += ". See structured details for other complaints."
    return body


def _brand_attitude_summary(result: Mapping[str, Any]) -> str:
    clauses: list[str] = []
    attitude = _label(result.get("attitude"), _ATTITUDE_LABELS)
    if attitude:
        clauses.append("Current brand sentiment: " + attitude)
    for key, label in (
        ("positive_ratio", "Positive sentiment: "),
        ("neutral_ratio", "Neutral sentiment: "),
        ("negative_ratio", "Negative sentiment: "),
    ):
        value = _format_percent(result.get(key))
        if value:
            clauses.append(label + value)
    trend = _label(result.get("trend_direction"), _TREND_LABELS)
    if trend:
        clauses.append("Overall trend: " + trend)
    body = _join_clauses(clauses)
    return body + "." if body else "No summary available."


def _risk_summary(result: Mapping[str, Any], threshold_exceeded: bool) -> str:
    subject = _label(result.get("part"), _RISK_LABELS) or _label(result.get("risk_type"), _RISK_LABELS) or "Current risk"
    hit_count = _format_number(result.get("hit_count"))
    threshold = _format_number(result.get("threshold"))
    if threshold_exceeded:
        if hit_count and threshold:
            body = f"{subject}: {hit_count} hits reached the alert threshold of {threshold}, creating a production risk alert."
        elif hit_count:
            body = f"{subject}: {hit_count} hits. A production risk alert is active."
        else:
            body = f"A production risk alert is active for {subject}."
    else:
        if hit_count and threshold:
            body = f"{subject}: {hit_count} hits against an alert threshold of {threshold}. Risk assessment is normal; no production alert has been triggered."
        elif hit_count:
            body = f"{subject}: {hit_count} hits. Risk assessment is normal; no production alert has been triggered."
        else:
            body = f"Risk assessment is normal for {subject}; no production alert has been triggered."
    risk_status = _label(result.get("risk_status"))
    if risk_status:
        body += f" Risk status: {risk_status}."
    return body


def _business_summary(payload: Mapping[str, Any]) -> str:
    for key in ("published_summary", "business_impact", "recommended_action"):
        value = _text(payload.get(key))
        if value:
            return value
        return "No summary available."


def _kol_summary(record_type: str, payload: Mapping[str, Any]) -> str:
    if record_type == "kol_current_assessment":
        candidates = ("cooperation_conclusion", "review_conclusion", "performance_summary", "distribution_conclusion")
    else:
        candidates = ("review_conclusion", "distribution_conclusion", "performance_summary", "public_opinion_conclusion")
    first = next((_text(payload.get(key)) for key in candidates), None)
    if record_type == "kol_cooperation_result" and first:
        additions: list[str] = []
        project = _text(payload.get("project_name")) or _text(payload.get("project_id"))
        stage = _text(payload.get("final_stage"))
        performance = _text(payload.get("performance_summary"))
        if project and stage:
            additions.append(f"Project {project} is currently in the {stage} stage")
        if performance and performance != first:
            additions.append("Performance: " + performance)
        if additions:
            return first + "; " + "; ".join(additions)
    return first or "No summary available."


def build_record_display(*, source_system: str, record_type: str, payload_json: Any) -> dict[str, str]:
    """Return stable category, risk state, and a short deterministic summary."""

    payload = _as_mapping(payload_json)
    result = _as_mapping(payload.get("result"))
    source = (source_system or "").strip().upper()
    record_type = (record_type or "").strip()

    if source == "C" and record_type in _C_RISK_TYPES:
        threshold_exceeded = _as_bool(result.get("threshold_exceeded")) is True
        category = "risk_alert" if threshold_exceeded else "risk_assessment"
        risk_state = "alert" if threshold_exceeded else "normal"
        summary = _risk_summary(result, threshold_exceeded)
    elif source == "C" and record_type in _C_FEEDBACK_TYPES:
        category = "feedback"
        risk_state = "none"
        if record_type == "consumer_journey_sentiment":
            summary = _journey_summary(payload, result)
        elif record_type == "consumer_nps_prediction":
            summary = _nps_summary(result)
        elif record_type == "consumer_key_complaints":
            summary = _key_complaints_summary(result)
        else:
            summary = _brand_attitude_summary(result)
    elif source == "C":
        # Persisted C records are validated against the known contract.  If an
        # old or manually inserted unknown type appears, do not call it normal
        # consumer feedback and do not infer a risk state from its text.
        category = "project"
        risk_state = "none"
        summary = "No summary available."
    elif source == "B":
        category = "policy" if record_type == "business_policy" else "project"
        risk_state = "none"
        summary = _business_summary(payload)
    elif source == "KOL":
        category = "kol_trend"
        risk_state = "none"
        summary = _kol_summary(record_type, payload)
    else:
        category = "project"
        risk_state = "none"
        summary = "No summary available."

    return {
        "display_category": category,
        "risk_state": risk_state,
        "display_summary": summary,
    }
