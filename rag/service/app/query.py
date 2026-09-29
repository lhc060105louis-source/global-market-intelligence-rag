"""FastAPI-owned query orchestration and evidence-safe output assembly."""
from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KnowledgeRecord, RagDocumentMapping
from .query_planner import QueryPlan, score_candidate

REFUSAL = "No evidence supporting an answer was found in the current knowledge base."
OUTPUT_FIELDS = (
    "summary", "consumer_signal", "business_impact", "kol_impact",
    "action_recommendations", "evidence", "data_time", "limitations",
)
TARGETS = ("c_current", "c_history", "b_business", "kol")
SEMANTIC_FIELD_NAMES = ("summary", "consumer_signal", "business_impact", "kol_impact", "actions")
SEMANTIC_DOMAIN_FIELDS = {
    "consumer_signal": "c",
    "business_impact": "b",
    "kol_impact": "kol",
}
SEMANTIC_FIELD_SOURCES = frozenset({"maxkb", "deterministic", "none"})
SEMANTIC_NO_EVIDENCE_NOTICES = {
    "consumer_signal": "No valid evidence supports consumer signals in the selected scope.",
    "business_impact": "No valid evidence supports business impact in the selected scope.",
    "kol_impact": "No valid evidence supports creator impact in the selected scope.",
}


@dataclass(frozen=True)
class Evidence:
    record_id: str
    target: str
    text: str
    score: float | None
    source_version: int


@dataclass(frozen=True)
class SemanticDraft:
    summary: str
    consumer_signal: str | None
    business_impact: str | None
    kol_impact: str | None
    actions: list[str]


@dataclass(frozen=True)
class ParsedSemanticDraft:
    """A JSON draft after harmless shape normalization, before evidence validation."""

    summary: str | None
    consumer_signal: str | None
    business_impact: str | None
    kol_impact: str | None
    actions: list[str] | None
    present_fields: frozenset[str]
    invalid_fields: frozenset[str]


@dataclass(frozen=True)
class SemanticDraftAssessment:
    """The field-level safe merge of a MaxKB draft and deterministic fallbacks."""

    draft: SemanticDraft
    field_sources: dict[str, str]
    invalid_fields: frozenset[str]


class SemanticDraftError(ValueError):
    """A model response does not satisfy the semantic-draft contract."""


@dataclass(frozen=True)
class QueryEvaluation:
    evidence: list[Evidence]
    candidate_count: int
    effective_candidate_count: int
    entity_match_rate: float
    field_match_rate: float
    subject_match_rate: float
    covered_targets: frozenset[str]
    max_score: float | None
    filtered_count: int
    fallback_required: bool


def selected_targets(domains: list[str] | None, *, historical: bool = False) -> list[str]:
    requested = set(domains or [])
    if not requested:
        return ["c_history" if historical else "c_current"]
    targets: list[str] = []
    if requested.intersection({"c", "consumer", "c_current", "c_history"}):
        if "c_history" in requested:
            historical = True
        targets.append("c_history" if historical else "c_current")
    if requested.intersection({"b", "business", "b_business"}):
        targets.append("b_business")
    if "kol" in requested:
        targets.append("kol")
    return targets


def extract_chat_answer(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload or "")
    for key in ("answer", "content", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("content"), str):
            return value["content"]
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(choice.get("text"), str):
                return choice["text"]
    return ""


def extract_chat_error(payload: Any) -> str:
    """Extract an upstream error envelope without mistaking chat content."""

    if not isinstance(payload, dict):
        return ""
    for key in ("error", "error_message", "errorMessage"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            message = value.get("message") or value.get("detail")
            if isinstance(message, str) and message.strip():
                return message.strip()
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        normalized = message.lower()
    if "model" in normalized and any(
        marker in normalized for marker in ("not found", "not exist", "not installed", "missing", "unavailable")
        ):
            return message.strip()
    data = payload.get("data")
    if isinstance(data, dict) and data is not payload:
        return extract_chat_error(data)
    return ""


def answer_structured_question(question: str, evidence: list[Evidence]) -> str:
    normalized = "".join(question.lower().split())
    if any(token in normalized for token in ("which brands", "what brands", "list brands", "whichbrands")):
        brands: set[str] = set()
        for item in evidence:
            for line in item.text.splitlines():
                if line.lower().startswith("brand:"):
                    value = line.split(":", 1)[1].strip()
                    if value and value.upper() not in {"UNKNOWN", "UNKNOWN_BRAND", "N/A", "NONE"}:
                        brands.add(value)
        return "Brands identified in the validated evidence: " + ", ".join(sorted(brands)) + "." if brands else "The validated evidence does not contain an explicit brand field."

    if any(token in normalized for token in ("which emotions", "what emotions", "list emotions", "whichemotions")):
        emotions: set[str] = set()
        for item in evidence:
            for line in item.text.splitlines():
                if not line.lower().startswith("emotion_distribution:"):
                    continue
                try:
                    distribution = json.loads(line.split(":", 1)[1].strip())
                except (TypeError, ValueError, json.JSONDecodeError):
                    distribution = {}
                for label in distribution:
                    values: list[Any] = [label]
                    if isinstance(label, str) and label.startswith("["):
                        try:
                            parsed = ast.literal_eval(label)
                            if isinstance(parsed, (list, tuple, set)):
                                values = list(parsed)
                        except (SyntaxError, ValueError):
                            pass
                    emotions.update(str(value).strip() for value in values if str(value).strip())
        return "Emotions found in the validated evidence: " + ", ".join(sorted(emotions)) + "." if emotions else "The validated evidence does not contain an explicit sentiment field."

    if any(token in normalized for token in ("neutral sentiment share", "neutral ratio", "neutralratio", "neutral_ratio")):
        weighted_total = 0.0
        signal_total = 0.0
        for item in evidence:
            signal_count = 1.0
            neutral_ratio: float | None = None
            for line in item.text.splitlines():
                if line.lower().startswith("signal_count:"):
                    try:
                        signal_count = max(0.0, float(line.split(":", 1)[1].strip()))
                    except ValueError:
                        signal_count = 1.0
                elif line.lower().startswith("result:"):
                    try:
                        result = json.loads(line.split(":", 1)[1].strip())
                        if result.get("neutral_ratio") is not None:
                            neutral_ratio = float(result["neutral_ratio"])
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pass
            if neutral_ratio is not None and signal_count > 0:
                weighted_total += neutral_ratio * signal_count
                signal_total += signal_count
        if signal_total == 0:
            return "The validated evidence does not contain an explicit neutral sentiment share."
        percentage = weighted_total / signal_total * 100
        return f"Neutral sentiment share in the validated evidence: {percentage:.2f}".rstrip("0").rstrip(".") + "% ."
    return ""


def _external_document_id(hit: dict[str, Any]) -> str | None:
    # MaxKB hit_test returns both a chunk ``id`` and its parent ``document_id``.
    # The sync mapping stores the parent document id, so prefer that field.
    for key in ("document_id", "documentId", "document", "id"):
        value = hit.get(key)
        if isinstance(value, dict):
            value = value.get("id")
        if value:
            return str(value)
    return None


def _hit_score(hit: dict[str, Any]) -> float | None:
    score = hit.get("similarity", hit.get("comprehensive_score", hit.get("score")))
    return float(score) if score is not None else None


def _deduplicate_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the strongest hit per parent MaxKB document."""
    strongest: dict[str, dict[str, Any]] = {}
    for hit in hits:
        external_id = _external_document_id(hit)
        if not external_id:
            continue
        previous = strongest.get(external_id)
        if previous is None or (_hit_score(hit) or 0.0) > (_hit_score(previous) or 0.0):
            strongest[external_id] = hit
    return list(strongest.values())


def evaluate_evidence(
    db: Session,
    hits: list[dict[str, Any]],
    allowed_targets: list[str],
    *,
    plan: QueryPlan | None = None,
    minimum_score: float = 0.0,
) -> QueryEvaluation:
    unique_hits = _deduplicate_hits(hits)
    ids = {_external_document_id(hit) for hit in unique_hits}
    ids.discard(None)
    if not ids:
        targeted_constraint = bool(plan and plan.auxiliary_query and (
            plan.high_confidence_entities
            or plan.high_confidence_fields
            or plan.explicit_domains
        ))
        return QueryEvaluation(
            [], 0, 0, 0.0, 0.0, 0.0, frozenset(), None, 0, targeted_constraint,
        )
    rows = db.execute(select(KnowledgeRecord, RagDocumentMapping).join(
        RagDocumentMapping, RagDocumentMapping.record_id == KnowledgeRecord.id
    ).where(RagDocumentMapping.external_document_id.in_(ids))).all()
    valid = {mapping.external_document_id: record for record, mapping in rows
             if record.status == "active" and mapping.external_is_active and record.target_knowledge_base in allowed_targets
             and mapping.mapped_source_version == record.source_version}
    evidence_with_rank: list[tuple[float, Evidence, dict[str, Any]]] = []
    filtered_count = 0
    entity_matches = 0
    entity_checks = 0
    subject_matches = 0
    subject_checks = 0
    field_matches = 0
    field_checks = 0
    for hit in unique_hits:
        external_id = _external_document_id(hit)
        record = valid.get(external_id)
        if record is None:
            continue
        raw_score = _hit_score(hit)
        rank_score = raw_score or 0.0
        details: dict[str, Any] = {"entity_matches": {}, "field_matches": []}
        hard_filter = False
        if plan is not None:
            rank_score, hard_filter, details = score_candidate(plan, record, raw_score)
            entity_values = [value for value in details.get("entity_matches", {}).values() if value is not None]
            entity_checks += len(entity_values)
            entity_matches += sum(1 for value in entity_values if value)
            for key in ("brand", "vehicle_model"):
                if key in plan.high_confidence_entities and key in details.get("entity_matches", {}):
                    subject_checks += 1
                    subject_matches += int(bool(details.get("entity_matches", {}).get(key)))
            fields = details.get("field_matches", [])
            field_checks += len(plan.requested_fields)
            field_matches += len(fields)
        if hard_filter or rank_score < minimum_score:
            filtered_count += 1
            continue
        evidence = Evidence(record.id, record.target_knowledge_base, record.retrieval_text,
                             rank_score if plan is not None else raw_score, record.source_version)
        evidence_with_rank.append((rank_score, evidence, details))
    evidence_with_rank.sort(key=lambda item: item[0], reverse=True)
    evidence: list[Evidence] = []
    seen_records: set[str] = set()
    for _, item, _ in evidence_with_rank:
        if item.record_id not in seen_records:
            evidence.append(item)
            seen_records.add(item.record_id)
    max_score = max((item[0] for item in evidence_with_rank), default=None)
    entity_rate = entity_matches / entity_checks if entity_checks else 0.0
    field_rate = field_matches / field_checks if field_checks else 0.0
    subject_rate = subject_matches / subject_checks if subject_checks else 0.0
    covered_targets = frozenset(item.target for item in evidence)
    explicit_target_domains = {
        target_domain
        for target_domain in allowed_targets
        if (target_domain.startswith("c_") and "c" in (plan.explicit_domains if plan else set()))
        or (target_domain == "b_business" and "b" in (plan.explicit_domains if plan else set()))
        or (target_domain == "kol" and "kol" in (plan.explicit_domains if plan else set()))
    }
    covered_explicit_domains = {
        target_domain for target_domain in covered_targets
        if target_domain in explicit_target_domains
    }
    # A broad query with no hit is not, by itself, a reason to issue another
    # retrieval request.  That was especially wasteful for the all-domain
    # view, where KOL evidence is optional unless the question mentions KOL.
    # Only a high-confidence constraint or an explicitly named domain can
    # justify the one bounded auxiliary retrieval.
    targeted_constraint = bool(plan and (
        plan.high_confidence_entities
        or plan.high_confidence_fields
        or explicit_target_domains
    ))
    fallback_required = bool(plan and plan.auxiliary_query and (
        (not evidence and targeted_constraint)
        or (
            evidence
            and (
                (subject_checks > 0 and subject_rate == 0.0)
                or (bool(plan.high_confidence_fields) and field_matches == 0)
                or (explicit_target_domains and not explicit_target_domains.issubset(covered_explicit_domains))
            )
        )
    ))
    return QueryEvaluation(evidence, len(unique_hits), len(evidence), entity_rate, field_rate, subject_rate,
                           covered_targets, max_score, filtered_count, fallback_required)


def filter_effective_evidence(
    db: Session,
    hits: list[dict[str, Any]],
    allowed_targets: list[str],
    plan: QueryPlan | None = None,
) -> list[Evidence]:
    """Backward-compatible evidence filter with optional query-aware reranking."""
    return evaluate_evidence(db, hits, allowed_targets, plan=plan).evidence


def _evidence_domains(evidence: list[Evidence]) -> set[str]:
    domains: set[str] = set()
    for item in evidence:
        if item.target in {"c_current", "c_history"}:
            domains.add("c")
        elif item.target == "b_business":
            domains.add("b")
        elif item.target == "kol":
            domains.add("kol")
    return domains


def format_evidence_context(evidence: list[Evidence], *, max_chars: int) -> str:
    """Make domain ownership explicit before evidence reaches a model."""
    prefixes = {"c_current": "C", "c_history": "C", "b_business": "B", "kol": "KOL"}
    counters: dict[str, int] = {"C": 0, "B": 0, "KOL": 0}
    domain_order = ("c", "b", "kol")
    domain_labels = {"c": "Consumer evidence", "b": "Business evidence", "kol": "Creator and partnership evidence"}
    grouped: dict[str, list[str]] = {domain: [] for domain in domain_order}
    for item in evidence:
        prefix = prefixes.get(item.target, "UNKNOWN")
        domain = (
            "c" if item.target in {"c_current", "c_history"}
            else "b" if item.target == "b_business"
            else "kol" if item.target == "kol"
            else item.target
        )
        counters[prefix] = counters.get(prefix, 0) + 1
        block = f"[Evidence domain: {item.target}]\n[{prefix}{counters[prefix]}]\n{item.text}"
        grouped.setdefault(domain, []).append(block)
    sections = [
        f"## {domain_labels[domain]}\n" + "\n\n".join(grouped[domain])
        for domain in domain_order
        if grouped[domain]
    ]
    return "\n\n".join(sections)[:max_chars]


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
    decoder = json.JSONDecoder()
    start = cleaned.find("{")
    while start >= 0:
        try:
            value, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            start = cleaned.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        break
    raise SemanticDraftError("semantic_draft_json_invalid")


_SEMANTIC_FIELD_ALIASES = {
    "summary": ("summary", "summary"),
    "consumer_signal": ("consumer_signal", "consumer_signal"),
    "business_impact": ("business_impact", "business_impact"),
    "kol_impact": ("kol_impact", "kol_impact"),
    "actions": ("actions", "action_recommendations"),
}
_SEMANTIC_DOMAIN_WRAPPER_KEYS = {
    "consumer_signal": frozenset({"c_current", "c_history"}),
    "business_impact": frozenset({"b_business"}),
    "kol_impact": frozenset({"kol"}),
}


def _semantic_payload_value(payload: Mapping[str, Any], field: str) -> tuple[bool, Any, bool]:
    """Return an explicit field value and whether aliases disagree."""

    matches = [(alias, payload[alias]) for alias in _SEMANTIC_FIELD_ALIASES[field] if alias in payload]
    if not matches:
        return False, None, False
    canonical = next((value for alias, value in matches if alias == field), matches[0][1])
    conflict = any(value != canonical for _, value in matches)
    return True, canonical, conflict


def _split_semantic_action_text(value: str) -> list[str]:
    actions: list[str] = []
    for line in value.splitlines():
        actions.extend(part.strip() for part in line.split(";") if part.strip())
    return actions


def parse_semantic_draft_partial(text: str) -> ParsedSemanticDraft:
    """Parse harmless response variations while retaining field-level failures.

    This parser never turns free-form prose into a semantic answer.  A JSON
    object is still required; only field names and the action string shape are
    normalized before evidence-bound validation.
    """

    payload = _extract_json_object(text)
    present: set[str] = set()
    invalid: set[str] = set()
    values: dict[str, Any] = {field: None for field in SEMANTIC_FIELD_NAMES}

    for field in SEMANTIC_FIELD_NAMES:
        found, value, conflict = _semantic_payload_value(payload, field)
        if not found:
            continue
        present.add(field)
        if conflict:
            invalid.add(field)
            continue
        if field == "summary":
            if isinstance(value, str) and value.strip():
                values[field] = value.strip()
            else:
                invalid.add(field)
            continue
        if field in _SEMANTIC_DOMAIN_WRAPPER_KEYS:
            if isinstance(value, dict) and len(value) == 1:
                domain_key, domain_value = next(iter(value.items()))
                if domain_key in _SEMANTIC_DOMAIN_WRAPPER_KEYS[field] and isinstance(domain_value, str):
                    value = domain_value
                else:
                    invalid.add(field)
                    continue
            if value is None:
                values[field] = None
            elif isinstance(value, str) and value.strip():
                values[field] = value.strip()
            else:
                invalid.add(field)
            continue
        if isinstance(value, str):
            normalized_actions = _split_semantic_action_text(value)
            if normalized_actions:
                values[field] = normalized_actions
            else:
                invalid.add(field)
        elif isinstance(value, list) and all(isinstance(action, str) and action.strip() for action in value):
            values[field] = [action.strip() for action in value]
        else:
            invalid.add(field)

    usable = any(
        field not in invalid and (
            bool(values[field]) if field != "actions" else bool(values[field])
        )
        for field in SEMANTIC_FIELD_NAMES
    )
    if not usable:
        raise SemanticDraftError("semantic_draft_no_usable_fields")
    return ParsedSemanticDraft(
        summary=values["summary"],
        consumer_signal=values["consumer_signal"],
        business_impact=values["business_impact"],
        kol_impact=values["kol_impact"],
        actions=values["actions"],
        present_fields=frozenset(present),
        invalid_fields=frozenset(invalid),
    )


def parse_semantic_draft(text: str) -> SemanticDraft:
    payload = _extract_json_object(text)
    required = {"summary", "consumer_signal", "business_impact", "kol_impact", "actions"}
    if set(payload) != required:
        raise SemanticDraftError("semantic_draft_schema_fields_invalid")
    summary = payload["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise SemanticDraftError("semantic_draft_summary_invalid")
    values: list[str | None] = []
    allowed_domain_keys = {
        "consumer_signal": {"c_current", "c_history"},
        "business_impact": {"b_business"},
        "kol_impact": {"kol"},
    }
    for key in ("consumer_signal", "business_impact", "kol_impact"):
        value = payload[key]
        # Some local models wrap a valid sentence under the evidence-domain
        # name despite the string-only contract. Tolerate only this exact,
        # one-key shape; validation still rejects a label used as the value.
        if isinstance(value, dict) and len(value) == 1:
            domain_key, domain_value = next(iter(value.items()))
            if domain_key in allowed_domain_keys[key] and isinstance(domain_value, str):
                value = domain_value
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise SemanticDraftError(f"semantic_draft_{key}_invalid")
        values.append(value.strip() if isinstance(value, str) else None)
    actions = payload["actions"]
    if not isinstance(actions, list) or any(not isinstance(action, str) or not action.strip() for action in actions):
        raise SemanticDraftError("semantic_draft_actions_invalid")
    return SemanticDraft(summary.strip(), values[0], values[1], values[2], [action.strip() for action in actions])


_SEMANTIC_PLACEHOLDER_VALUES = frozenset({
    "c", "c_current", "c_history", "consumer", "consumer_signal",
    "b", "b_business", "business", "business_impact",
    "kol", "kol_impact", "kol_current",
    "consumer signals", "business impact", "creator reach and partnership impact",
    "null", "none", "n/a",
})


_SEMANTIC_ACTION_DOMAIN_MARKERS = {
    "c": ("c_current", "c_history", "consumer", "user", "review", "comment", "sentiment", "repair", "complaint", "after-sales", "reputation"),
    "b": ("b_business", "business impact", "regulation", "compliance", "afir", "cpo", "charging", "power grid", "energy storage", "client project"),
    "kol": ("kol", "influencer", "creator", "reach", "exposure", "content creator"),
}


def _is_semantic_placeholder(value: str | None) -> bool:
    if value is None:
        return False
    normalized = "".join(value.casefold().split())
    return normalized in _SEMANTIC_PLACEHOLDER_VALUES


def _action_mentions_unavailable_domain(action: str, evidence_domains: set[str]) -> bool:
    normalized = "".join(action.casefold().split())
    return any(
        domain not in evidence_domains and any(marker in normalized for marker in markers)
        for domain, markers in _SEMANTIC_ACTION_DOMAIN_MARKERS.items()
    )


def validate_semantic_draft(draft: SemanticDraft, evidence: list[Evidence], selected: list[str]) -> SemanticDraft:
    """Apply target-domain and anti-copying boundaries after JSON parsing."""
    if _is_semantic_placeholder(draft.summary):
        raise SemanticDraftError("semantic_draft_summary_placeholder")
    evidence_domains = _evidence_domains(evidence)
    selected_domains = _evidence_domains([Evidence("", target, "", None, 0) for target in selected])
    values = {"c": draft.consumer_signal, "b": draft.business_impact, "kol": draft.kol_impact}
    for domain, value in values.items():
        if domain not in evidence_domains or domain not in selected_domains:
            if value is not None:
                raise SemanticDraftError(f"semantic_draft_{domain}_without_evidence")
        elif value is None:
            raise SemanticDraftError(f"semantic_draft_{domain}_missing")
        if _is_semantic_placeholder(value):
            raise SemanticDraftError(f"semantic_draft_{domain}_placeholder")
    if any(_is_semantic_placeholder(action) for action in draft.actions):
        raise SemanticDraftError("semantic_draft_action_placeholder")
    if any(_action_mentions_unavailable_domain(action, evidence_domains) for action in draft.actions):
        raise SemanticDraftError("semantic_draft_action_domain_mismatch")
    non_null = [value for value in values.values() if value is not None]
    if len(evidence_domains.intersection(selected_domains)) > 1:
        if any(value == draft.summary for value in non_null):
            raise SemanticDraftError("semantic_draft_domain_copies_summary")
        if len(non_null) != len(set(non_null)):
            raise SemanticDraftError("semantic_draft_domains_duplicated")
    return draft


_SEMANTIC_VALUE_DOMAIN_MARKERS = {
    "c": ("consumer", "user", "review", "comment", "sentiment", "after-sales", "reputation"),
    "b": ("business impact", "regulation", "compliance", "procurement", "client project", "charging", "power grid", "energy storage", "cpo"),
    "kol": ("kol", "influencer", "creator", "reach", "partnership", "exposure", "content creator"),
}


def _semantic_value_mentions_other_domain(value: str, domain: str) -> bool:
    normalized = "".join(value.casefold().split())
    return any(
        other_domain != domain and any(marker in normalized for marker in markers)
        for other_domain, markers in _SEMANTIC_VALUE_DOMAIN_MARKERS.items()
    )


def _valid_semantic_domain_value(value: str | None, domain: str) -> bool:
    return bool(
        isinstance(value, str)
        and value.strip()
        and not _is_semantic_placeholder(value)
        and not _semantic_value_mentions_other_domain(value, domain)
    )


def _same_semantic_text(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return "".join(left.casefold().split()) == "".join(right.casefold().split())


def assess_semantic_draft(
    parsed: ParsedSemanticDraft,
    evidence: list[Evidence],
    selected: list[str],
    fallback: SemanticDraft,
) -> SemanticDraftAssessment:
    """Keep safe MaxKB fields and replace only invalid fields with fallbacks."""

    evidence_domains = _evidence_domains(evidence)
    selected_domains = _evidence_domains([Evidence("", target, "", None, 0) for target in selected])
    invalid_fields = set(parsed.invalid_fields)
    field_sources: dict[str, str] = {}

    if parsed.summary and "summary" not in invalid_fields and not _is_semantic_placeholder(parsed.summary):
        summary = parsed.summary
        field_sources["summary"] = "maxkb"
    else:
        summary = fallback.summary
        field_sources["summary"] = "deterministic"
        invalid_fields.add("summary")

    values: dict[str, str | None] = {}
    for field, domain in SEMANTIC_DOMAIN_FIELDS.items():
        candidate = getattr(parsed, field)
        expected = domain in evidence_domains and domain in selected_domains
        if not expected:
            values[field] = None
            field_sources[field] = "none"
            if candidate is not None:
                invalid_fields.add(field)
            continue
        if field not in invalid_fields and _valid_semantic_domain_value(candidate, domain):
            values[field] = candidate.strip()
            field_sources[field] = "maxkb"
        else:
            values[field] = getattr(fallback, field)
            field_sources[field] = "deterministic"
            invalid_fields.add(field)

    present_domains = evidence_domains.intersection(selected_domains)
    if len(present_domains) > 1:
        accepted_values: list[str] = []
        for field in ("consumer_signal", "business_impact", "kol_impact"):
            value = values[field]
            if field_sources[field] != "maxkb" or not value:
                continue
            copied_summary = field_sources["summary"] == "maxkb" and _same_semantic_text(value, summary)
            copied_domain = any(_same_semantic_text(value, accepted) for accepted in accepted_values)
            if copied_summary or copied_domain:
                values[field] = getattr(fallback, field)
                field_sources[field] = "deterministic"
                invalid_fields.add(field)
            else:
                accepted_values.append(value)

    candidate_actions = parsed.actions
    if (
        "actions" not in invalid_fields
        and candidate_actions
        and not any(_is_semantic_placeholder(action) for action in candidate_actions)
        and not any(_action_mentions_unavailable_domain(action, evidence_domains) for action in candidate_actions)
    ):
        actions = candidate_actions
        field_sources["actions"] = "maxkb"
    else:
        actions = fallback.actions
        field_sources["actions"] = "deterministic" if evidence else "none"
        invalid_fields.add("actions")

    return SemanticDraftAssessment(
        draft=SemanticDraft(
            summary=summary,
            consumer_signal=values["consumer_signal"],
            business_impact=values["business_impact"],
            kol_impact=values["kol_impact"],
            actions=actions,
        ),
        field_sources=field_sources,
        invalid_fields=frozenset(invalid_fields),
    )


def semantic_field_metadata(field_sources: Mapping[str, str] | None = None) -> dict[str, dict[str, str | None]]:
    """Expose field provenance without exposing model errors or raw responses."""

    sources = field_sources or {}
    metadata: dict[str, dict[str, str | None]] = {}
    for field in SEMANTIC_FIELD_NAMES:
        source = sources.get(field, "none")
        if source not in SEMANTIC_FIELD_SOURCES:
            source = "none"
        metadata[field] = {
            "source": source,
            "notice": SEMANTIC_NO_EVIDENCE_NOTICES.get(field) if source == "none" else None,
        }
    return metadata


def aggregate_semantic_source(field_sources: Mapping[str, str]) -> str:
    sources = {source for source in field_sources.values() if source != "none"}
    if not sources:
        return "none"
    if sources == {"maxkb"}:
        return "maxkb"
    if sources == {"deterministic"}:
        return "deterministic"
    return "mixed"


def deterministic_semantic_field_sources(evidence: list[Evidence]) -> dict[str, str]:
    domains = _evidence_domains(evidence)
    return {
        "summary": "deterministic" if evidence else "none",
        "consumer_signal": "deterministic" if "c" in domains else "none",
        "business_impact": "deterministic" if "b" in domains else "none",
        "kol_impact": "deterministic" if "kol" in domains else "none",
        "actions": "deterministic" if evidence else "none",
    }


def safe_semantic_draft(evidence: list[Evidence]) -> SemanticDraft:
    draft, _ = deterministic_semantic_draft(evidence)
    return draft


_DETERMINISTIC_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "c_current": (
        "dimension", "brand", "vehicle_model", "region", "business_date", "signal_count",
        "emotion_distribution", "trend", "risk_status",
    ),
    "c_history": (
        "dimension", "brand", "vehicle_model", "region", "business_date", "signal_count",
        "emotion_distribution", "trend", "risk_status",
    ),
    "b_business": (
        "entry_type", "title", "published_summary", "regions", "tags", "business_impact",
        "recommended_action", "effective_at",
    ),
    "kol": (
        "kol_id", "display_name", "primary_platform", "audience_regions", "content_categories",
        "commercial_score", "risk_score", "risk_level", "risk_tags", "cooperation_conclusion",
        "project", "final_stage", "distribution_conclusion", "performance_summary",
        "public_opinion_conclusion", "review_conclusion", "effective_at", "applicable_period",
    ),
}

_DETERMINISTIC_FIELD_LABELS = {
    "dimension": "Dimension", "brand": "Brand", "vehicle_model": "Vehicle model", "region": "Region",
    "business_date": "Business date", "signal_count": "Signal count", "emotion_distribution": "Sentiment distribution",
    "trend": "Trend", "risk_status": "Risk status", "entry_type": "Entry type", "title": "Title",
    "published_summary": "Published summary", "regions": "Applicable regions", "tags": "Tags",
    "business_impact": "Business impact", "recommended_action": "Recommended action", "effective_at": "Effective at",
    "kol_id": "KOL ID", "display_name": "Name", "primary_platform": "Primary platform",
    "audience_regions": "Audience regions", "content_categories": "Content categories", "commercial_score": "Commercial score",
    "risk_score": "Risk score", "risk_level": "Risk level", "risk_tags": "Risk tags",
    "cooperation_conclusion": "Partnership conclusion", "project": "Project", "final_stage": "Final stage",
    "distribution_conclusion": "Distribution conclusion", "performance_summary": "Performance summary",
    "public_opinion_conclusion": "Public opinion conclusion", "review_conclusion": "Review conclusion",
    "applicable_period": "Applicable period",
}

_DETERMINISTIC_RESULT_FIELDS = {
    "positive_ratio": "Positive share", "negative_ratio": "Negative share", "neutral_ratio": "Neutral share",
    "trend_direction": "Trend direction", "risk_status": "Risk status", "risk_level": "Risk level",
    "part": "Component", "risk_type": "Risk type", "hit_count": "Hit count", "threshold": "Threshold",
    "threshold_exceeded": "Threshold exceeded", "first_hit_at": "First detected", "nps_value": "NPS",
    "change_from_previous": "Change from previous period", "promoter_ratio": "Promoter share", "passive_ratio": "Passive share",
    "detractor_ratio": "Detractor share", "complaints": "Complaints", "topic_name": "Complaint topic",
    "frequency": "Frequency", "average_sentiment_intensity": "Average sentiment intensity", "attitude": "Brand sentiment",
}


def _render_structured_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def limit_evidence_per_domain(evidence: list[Evidence], *, max_per_domain: int = 3) -> list[Evidence]:
    """Keep the highest-ranked evidence records used by deterministic fallback."""

    grouped: dict[str, list[Evidence]] = {}
    for item in evidence:
        domain = "c" if item.target in {"c_current", "c_history"} else item.target
        grouped.setdefault(domain, []).append(item)
    limited: list[Evidence] = []
    for items in grouped.values():
        ranked = sorted(items, key=lambda item: item.score if item.score is not None else 0.0, reverse=True)
        limited.extend(ranked[:max_per_domain])
    return limited


def _structured_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and "]" in stripped:
            key, value = stripped[1:].split("]", 1)
            value = value.strip()
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
            key, value = key.strip(), value.strip()
        else:
            continue
        if value:
            values.setdefault(key, value)
    return values


def _deterministic_facts(item: Evidence) -> list[str]:
    values = _structured_lines(item.text)
    facts: list[str] = []
    for key in _DETERMINISTIC_TARGET_FIELDS.get(item.target, ()):
        value = values.get(key)
        if value:
            label = _DETERMINISTIC_FIELD_LABELS.get(key, key)
            facts.append(f"{label}={value}")
    result = values.get("result")
    if result and item.target in {"c_current", "c_history"}:
        try:
            parsed = json.loads(result)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            for key, label in _DETERMINISTIC_RESULT_FIELDS.items():
                value = parsed.get(key)
                if value is None:
                    continue
                rendered = _render_structured_value(value)
                if rendered:
                    facts.append(f"{label}={rendered}")
    return facts[:12]


def _deterministic_domain_summary(domain: str, evidence: list[Evidence]) -> str:
    labels = {"c": "Consumer", "b": "Business", "kol": "Creator"}
    lines: list[str] = []
    for index, item in enumerate(evidence, 1):
        facts = _deterministic_facts(item)
        lines.append(f"Record {index}: " + ("; ".join(facts) if facts else "Validated structured records are available, but no fields suitable for summarization were found."))
    return f"{labels[domain]} evidence-based fallback (top {len(evidence)} records): " + "; ".join(lines)


def format_semantic_evidence_context(
    evidence: list[Evidence], *, max_chars: int, max_per_domain: int = 3,
) -> str:
    """Build a compact, domain-balanced context for the semantic model.

    ``retrieval_text`` is intentionally verbose because it is also used for
    record inspection.  Sending that whole blob to the semantic model makes a
    cross-domain request pay for large nested metric objects and, when the
    global character cap is reached, can hide the later B/KOL sections behind
    the first C section.  The semantic prompt only needs the already
    structured facts that the deterministic fallback can read.

    At least the highest-ranked record from every present domain is retained;
    additional records are added round-robin up to ``max_per_domain`` while
    respecting the overall character budget.
    """

    if max_chars <= 0 or not evidence:
        return ""

    prefixes = {"c": "C", "b": "B", "kol": "KOL"}
    labels = {"c": "Consumer evidence", "b": "Business evidence", "kol": "Creator and partnership evidence"}
    grouped: dict[str, list[Evidence]] = {domain: [] for domain in labels}
    for item in limit_evidence_per_domain(evidence, max_per_domain=max_per_domain):
        domain = (
            "c" if item.target in {"c_current", "c_history"}
            else "b" if item.target == "b_business"
            else "kol" if item.target == "kol"
            else ""
        )
        if domain:
            grouped[domain].append(item)

    blocks: dict[str, list[str]] = {}
    for domain, items in grouped.items():
        if not items:
            continue
        prefix = prefixes[domain]
        domain_blocks: list[str] = []
        for index, item in enumerate(items, 1):
            facts = _deterministic_facts(item)
            fact_text = "; ".join(facts) if facts else "Validated structured records are available, but no fields suitable for summarization were found."
            domain_blocks.append(f"[{prefix}{index}] {fact_text}")
        blocks[domain] = domain_blocks

    present = [domain for domain in ("c", "b", "kol") if domain in blocks]
    if not present:
        return ""

    # Keep each present domain visible.  Add one block per domain first, then
    # spend the remaining budget on the next ranked blocks round-robin.
    sections: dict[str, list[str]] = {
        domain: [f"## {labels[domain]}", blocks[domain][0]] for domain in present
    }
    used = sum(len("\n".join(lines)) for lines in sections.values()) + max(len(present) - 1, 0) * 2
    next_indexes = {domain: 1 for domain in present}
    while True:
        added = False
        for domain in present:
            index = next_indexes[domain]
            if index >= len(blocks[domain]):
                continue
            candidate = blocks[domain][index]
            separator_cost = 1
            if used + len(candidate) + separator_cost > max_chars:
                continue
            sections[domain].append(candidate)
            next_indexes[domain] += 1
            used += len(candidate) + separator_cost
            added = True
        if not added:
            break

    rendered = "\n\n".join("\n".join(sections[domain]) for domain in present)
    return rendered[:max_chars]


def deterministic_semantic_draft(
    evidence: list[Evidence], *, max_per_domain: int = 3, summary: str | None = None,
) -> tuple[SemanticDraft, list[Evidence]]:
    """Build an evidence-only draft without inference or cross-domain copying."""

    limited = limit_evidence_per_domain(evidence, max_per_domain=max_per_domain)
    by_domain: dict[str, list[Evidence]] = {"c": [], "b": [], "kol": []}
    for item in limited:
        if item.target in {"c_current", "c_history"}:
            by_domain["c"].append(item)
        elif item.target == "b_business":
            by_domain["b"].append(item)
        elif item.target == "kol":
            by_domain["kol"].append(item)
    present = [domain for domain in ("c", "b", "kol") if by_domain[domain]]
    summary_parts = [f"{domain.upper()}: {len(by_domain[domain])} records" for domain in present]
    final_summary = summary or (
        "Evidence-based fallback: validated structured fields by domain (" + "; ".join(summary_parts) + "). "
        "No information beyond the evidence was inferred."
    )
    actions_by_domain = {
        "c": "Review the source consumer comments, sentiment labels, and statistical methodology.",
        "b": "Check affected client projects and ask each project owner to confirm the communication approach.",
        "kol": "Review creator content and partnership status, then confirm whether to continue, adjust, or pause.",
    }
    return SemanticDraft(
        final_summary,
        _deterministic_domain_summary("c", by_domain["c"]) if by_domain["c"] else None,
        _deterministic_domain_summary("b", by_domain["b"]) if by_domain["b"] else None,
        _deterministic_domain_summary("kol", by_domain["kol"]) if by_domain["kol"] else None,
        [actions_by_domain[domain] for domain in present],
    ), limited


def structured_semantic_draft(answer: str, evidence: list[Evidence]) -> SemanticDraft:
    """Keep deterministic aggregate answers without turning them into cross-domain copies."""
    domains = _evidence_domains(evidence)
    if len(domains) == 1:
        return SemanticDraft(
            answer,
            answer if "c" in domains else None,
            answer if "b" in domains else None,
            answer if "kol" in domains else None,
            [],
        )
    return SemanticDraft(answer, None, None, None, [])


def build_legacy_prd_output(*, answer: str, evidence: list[Evidence], selected: list[str]) -> dict[str, Any]:
    if not evidence:
        return {"summary": REFUSAL, "consumer_signal": None, "business_impact": None,
                "kol_impact": None, "action_recommendations": None, "evidence": [],
                "data_time": [], "limitations": "No active evidence validated by the primary database was found."}
    sources = [{"record_id": item.record_id, "target_knowledge_base": item.target, "score": item.score,
                "source_version": item.source_version} for item in evidence]
    evidence_targets = {item.target for item in evidence}
    actions = []
    if evidence_targets.intersection({"c_current", "c_history"}):
        actions.append("Review the source consumer comments, sentiment labels, and statistical methodology.")
    if "b_business" in evidence_targets:
        actions.append("Check affected client projects and ask each project owner to confirm the communication approach.")
    if "kol" in evidence_targets:
        actions.append("Review creator content and partnership status, then confirm whether to continue, adjust, or pause.")
    data_times = []
    for item in evidence:
        for line in item.text.splitlines():
            if line.startswith("[business_date]"):
                data_times.append(line.split("] ", 1)[1])
            elif line.startswith("effective_at:"):
                data_times.append(line.split(":", 1)[1].strip())
    return {
        "summary": answer or REFUSAL,
        "consumer_signal": answer if evidence_targets.intersection({"c_current", "c_history"}) else None,
        "business_impact": answer if "b_business" in evidence_targets else None,
        "kol_impact": answer if "kol" in evidence_targets else None,
        "action_recommendations": "; ".join(actions) if actions else "There is no validated evidence for an action recommendation.",
        "evidence": sources,
        "data_time": data_times,
        "limitations": "Based only on retrieved copies that are active in the primary database and have matching versions for the selected scope.",
    }


def build_prd_output(
    *, draft: SemanticDraft, evidence: list[Evidence], selected: list[str],
    allow_missing_domain_values: bool = False,
) -> dict[str, Any]:
    if not evidence:
        return build_legacy_prd_output(answer="", evidence=evidence, selected=selected)
    validated = draft if allow_missing_domain_values else validate_semantic_draft(draft, evidence, selected)
    evidence_domains = _evidence_domains(evidence)
    sources = [{"record_id": item.record_id, "target_knowledge_base": item.target, "score": item.score,
                "source_version": item.source_version} for item in evidence]
    data_times: list[str] = []
    for item in evidence:
        for line in item.text.splitlines():
            value = ""
            if line.startswith("[business_date]"):
                value = line.split("] ", 1)[1].strip() if "] " in line else ""
            elif line.startswith("effective_at:"):
                value = line.split(":", 1)[1].strip()
            if value and value not in data_times:
                data_times.append(value)
    actions = "; ".join(validated.actions) if validated.actions else "No validated action recommendation can be generated at this time."
    return {
        "summary": validated.summary,
        "consumer_signal": validated.consumer_signal if "c" in evidence_domains else None,
        "business_impact": validated.business_impact if "b" in evidence_domains else None,
        "kol_impact": validated.kol_impact if "kol" in evidence_domains else None,
        "action_recommendations": actions,
        "evidence": sources,
        "data_time": data_times,
        "limitations": "Based only on retrieved copies that are active in the primary database and have matching versions for the selected scope.",
    }
