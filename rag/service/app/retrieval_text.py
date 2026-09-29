import json
from typing import Any

from .models import KnowledgeRecord
from .text_quality import find_text_quality_issues, validate_text_quality


def encoding_corruption(text: str) -> bool:
    """Return true for obvious mojibake/replacement output, not punctuation."""

    return not text or bool(find_text_quality_issues(text, root="retrieval_text"))


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _header(record: KnowledgeRecord) -> str:
    return "\n".join(
        [
            f"[record_id] {record.id}",
            f"[source] {record.source_system}",
            f"[record_type] {record.record_type}",
            f"[source_record_id] {record.source_record_id}",
            f"[source_version] {record.source_version}",
            f"[business_date] {_value(record.business_date)}",
            f"[is_mock] {str(record.is_mock).lower()}",
        ]
    )


def generate_retrieval_text(record: KnowledgeRecord) -> str:
    payload = record.payload_json
    # Keep this deterministic formatter safe when called from maintenance or
    # a one-off script, not only from the HTTP ingestion path.
    validate_text_quality(payload)
    lines: list[tuple[str, Any]]
    if record.target_knowledge_base in {"c_current", "c_history"}:
        result = payload["result"]
        lines = [
            ("dimension", payload["dimension"]),
            ("vehicle_model", payload["vehicle_model"]),
            ("brand", payload["brand"]),
            ("region", payload["region"]),
            ("journey_stage", payload["journey_stage"]),
            ("channel", payload["channel"]),
            ("language", payload["language"]),
            ("period", f"{payload['period_start']} to {payload['period_end']}"),
            ("business_date", payload["business_date"]),
            ("signal_count", payload["signal_count"]),
            ("emotion_distribution", payload["emotion_distribution"]),
            ("result", result),
            ("trend", result.get("trend_direction")),
            ("risk_status", result.get("risk_status")),
        ]
    elif record.target_knowledge_base == "b_business":
        lines = [
            ("entry_type", payload["entry_type"]),
            ("title", payload["title"]),
            ("published_summary", payload["published_summary"]),
            ("regions", payload["regions"]),
            ("tags", payload["tags"]),
            ("related_entities", payload["related_entities"]),
            ("business_impact", payload.get("business_impact")),
            ("recommended_action", payload.get("recommended_action")),
            ("external_sources", payload["external_sources"]),
            ("source_version", record.source_version),
            ("effective_at", record.effective_at.isoformat()),
        ]
    elif record.record_type == "kol_current_assessment":
        lines = [
            ("kol_id", payload["kol_id"]),
            ("display_name", payload["display_name"]),
            ("primary_platform", payload["primary_platform"]),
            ("audience_regions", payload["audience_regions"]),
            ("content_categories", payload["content_categories"]),
            ("commercial_score", payload["commercial_score"]),
            ("commercial_dimensions", payload["commercial_dimensions"]),
            ("risk_score", payload["risk_score"]),
            ("risk_level", payload["risk_level"]),
            ("risk_tags", payload["risk_tags"]),
            ("cooperation_conclusion", payload["cooperation_conclusion"]),
            ("source_version", record.source_version),
            ("effective_at", record.effective_at.isoformat()),
        ]
    else:
        lines = [
            ("cooperation_id", payload["cooperation_id"]),
            ("kol_id", payload["kol_id"]),
            ("project", f"{payload['project_id']} / {payload['project_name']}"),
            ("brand", payload.get("brand")),
            ("vehicle_model", payload.get("vehicle_model")),
            ("final_stage", payload["final_stage"]),
            ("distribution_conclusion", payload.get("distribution_conclusion")),
            ("performance_summary", payload.get("performance_summary")),
            ("public_opinion_conclusion", payload.get("public_opinion_conclusion")),
            ("review_conclusion", payload["review_conclusion"]),
            ("source_version", record.source_version),
            ("applicable_period", f"{payload.get('cooperation_start') or ''} to {payload.get('cooperation_end') or ''}"),
        ]
    body = "\n".join(f"{name}: {_value(value)}" for name, value in lines)
    text = f"{_header(record)}\n\n{body}"
    # Metadata such as source_record_id is outside ``payload_json`` but still
    # becomes part of the MaxKB document; validate the final serialized form
    # as well so maintenance rebuilds cannot reintroduce bad header text.
    validate_text_quality(text, root="retrieval_text")
    return text
