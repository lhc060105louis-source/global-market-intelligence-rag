"""Deterministic query planning for RAG retrieval.

The user's wording is never rewritten for the first MaxKB retrieval. This
module only derives bounded constraints for filtering, reranking, and one
optional fallback query.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


# Canonical values use payload_json spellings. The same helper canonicalizes
# question aliases and payload values before comparison. Brand and model seeds
# cover C-side vehicle identity data; regulation names seed B-side topics. The
# C-side part and symptom taxonomy is intentionally not imported here.
ENTITY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "brand": {
        "Tesla": ("Tesla",), "BYD": ("BYD",),
        "Hyundai": ("Hyundai",), "NIO": ("NIO",),
        "XPeng": ("XPeng",), "Li Auto": ("Li Auto",),
        "Volkswagen": ("Volkswagen", "VW"),
        "MG": ("MG",),
    },
    "vehicle_model": {
        "Model Y": ("Model Y", "Model-Y", "Model_Y"),
        "Model 3": ("Model 3", "Model-3", "Model_3"),
        "Dolphin": ("Dolphin",),
        "Seal": ("Seal",),
        "Atto 3": ("Atto 3", "Atto-3"),
        "Ioniq 5": ("Ioniq 5", "Ioniq-5"),
        "EL6": ("EL6", "EL 6"),
        "ID.3": ("ID.3", "ID_3", "ID 3"),
        "ID.4": ("ID.4", "ID_4", "ID 4"),
        "MG4 EV": ("MG4 EV", "MG4-EV", "MG4", "MG_4"),
        "Marvel R": ("Marvel R", "Marvel-R", "Marvel_R"),
    },
    "region": {
        "EU": (
            "EU", "E.U.", "European Union", "Europe",
            "EU-wide", "EU imports", "EU public procurement", "EU + 60+ contracting parties, including the UK",
        ),
        "UK": ("UK", "United Kingdom"),
        "US": ("US", "U.S.", "United States"), "China": ("China",), "ASEAN": ("ASEAN",),
        "Germany": ("Germany", "DE"),
        "France": ("France", "FR"),
        "Italy": ("Italy", "IT"),
        "Spain": ("Spain", "ES"),
        "Netherlands": ("Netherlands", "NL"),
        "Norway": ("Norway", "NO"),
    },
    "regulation_topic": {
        "General Safety Regulation": (
            "General Safety Regulation", "GSR", "(EU) 2019/2144",
        ),
        "AI Act": (
            "EU AI Act", "AI Act", "Artificial Intelligence Act", "(EU) 2024/1689",
        ),
        "REACH": (
            "REACH", "REACH / SVHC", "SVHC", "EU chemicals regulation",
            "Registration, Evaluation, Authorisation and Restriction of Chemicals", "(EC) 1907/2006",
        ),
        "Battery Regulation": (
            "Battery Regulation", "EU Battery Regulation", "(EU) 2023/1542",
        ),
        "WVTA": (
            "WVTA", "Whole Vehicle Type Approval", "Regulation 2018/858",
            "(EU) 2018/858",
        ),
        "UNECE R155": (
            "UNECE R155", "UN R155", "R155", "CSMS", "UN R155 / CSMS", "Cybersecurity regulation",
        ),
        "AFIR": (
            "AFIR", "Alternative Fuels Infrastructure Regulation", "(EU) 2023/1804",
        ),
        "UNECE R156": (
            "UNECE R156", "UN R156", "R156", "SUMS",
        ),
        "Data Act": (
            "Data Act", "EU Data Act", "GDPR + EU Data Act", "(EU) 2023/2854",
        ),
        "CBAM": (
            "CBAM", "Carbon Border Adjustment Mechanism", "Carbon Border Adjustment Mechanism",
            "(EU) 2023/956",
        ),
        "Euro 7": (
            "Euro 7", "Euro7", "emissions and battery durability regulation",
            "(EU) 2024/1257",
        ),
        "EU CO2 Standards": (
            "EU CO2 passenger car and van emission standards", "CO2 Standards",
            "EU CO2 standards", "EU CO2 emission standards",
        ),
        "Clean Vehicles Directive": (
            "Clean Vehicles Directive", "Clean Vehicles Directive", "(EU) 2019/1161",
        ),
        "Foreign Subsidies Regulation": (
            "Foreign Subsidies Regulation", "Foreign Subsidies Regulation", "(EU) 2022/2560",
        ),
        "Euro NCAP": ("Euro NCAP", "Euro NCAP 2026", "safety assessment protocol"),
        "German KBA/BAFA": (
            "German federal subsidy and local certification requirements", "DE-KBA / BAFA", "KBA", "BAFA",
        ),
    },
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "risk_status": ("risk_status", "risk status", "is the risk normal", "risk condition", "open risk status"),
    "risk_level": ("risk_level", "risk level", "risk severity"),
    "trend_direction": ("trend_direction", "trend", "direction of change", "trend direction"),
    "key_complaints": ("key_complaints", "key complaints", "main complaints", "complaint points", "user feedback"),
    "complaints": ("complaints", "complaint", "dissatisfaction", "negative feedback"),
    "brand_attitude": ("brand_attitude", "brand sentiment", "brand reputation", "how users view the brand"),
    "attitude": ("attitude", "reputation", "sentiment"),
    "recall_risk": ("recall_risk", "recall risk", "recall", "safety recall"),
    "legal_risk": ("legal_risk", "legal risk", "legal action", "lawsuit", "legal liability"),
    "threshold_exceeded": ("threshold_exceeded", "above threshold", "reached threshold", "action signal threshold"),
}

_UNKNOWN_VALUES = {"", "unknown", "unknown_brand", "n/a", "na", "none", "null", "unrecognized"}
_RISK_MARKERS = ("risk", "legal", "recall", "complaint", "trend", "risk level")
_C_ENTITY_MARKERS = ("consumer", "user", "vehicle model", "brand", "vehicle", "risk", "complaint", "reputation", "sentiment")
_LATIN_ALIAS = re.compile(r"[a-z0-9][a-z0-9 ._-]*$", re.IGNORECASE)
_DOMAIN_MARKERS = {
    "c": ("consumer", "user", "review", "comment", "sentiment", "complaint", "reputation", "recall", "repair"),
    "b": ("business", "regulation", "compliance", "client", "project", "procurement", "charging", "AFIR", "CPO", "power grid", "energy storage"),
    "kol": ("KOL", "creator", "influencer", "reach", "partnership", "content creator"),
}


def _normal_text(value: str) -> str:
    return re.sub(r"[\s_.-]+", " ", value.strip().casefold()).strip()


def _contains_alias(question: str, alias: str) -> bool:
    normalized_alias = _normal_text(alias)
    if _LATIN_ALIAS.fullmatch(alias):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])", _normal_text(question)) is not None
    return normalized_alias in _normal_text(question)


def canonicalize_entity_value(entity_type: str, value: Any) -> str | None:
    """Return a known canonical entity; unknown or fuzzy values do not match."""
    if not isinstance(value, str) or _normal_text(value) in _UNKNOWN_VALUES:
        return None
    for canonical, aliases in ENTITY_ALIASES.get(entity_type, {}).items():
        if any(_normal_text(value) == _normal_text(alias) for alias in aliases):
            return canonical
    return None


def entity_matches(entity_type: str, expected: str, actual: Any) -> bool:
    if canonicalize_entity_value(entity_type, actual) == expected:
        return True
    if entity_type == "region" and isinstance(actual, str):
        # B scopes can contain several regions, for example
        # ``EU + 60+ contracting parties, including the UK``. Treat a named region inside that
        # structured scope as a match without broadening model/entity matching.
        return any(_contains_alias(actual, alias) for alias in ENTITY_ALIASES["region"].get(expected, ()))
    return False


def regulation_topic_matches(expected: str, values: Iterable[Any]) -> bool:
    """Match one named regulation rather than a generic policy-related token."""
    for value in values:
        if not isinstance(value, str) or _normal_text(value) in _UNKNOWN_VALUES:
            continue
        if any(_contains_alias(value, alias) for alias in ENTITY_ALIASES["regulation_topic"].get(expected, ())):
            return True
    return False


@dataclass(frozen=True)
class QueryPlan:
    original_question: str
    normalized_entities: dict[str, str]
    requested_fields: frozenset[str]
    entity_confidence: dict[str, float]
    field_confidence: dict[str, float]
    auxiliary_query: str | None
    clarification_required: bool
    clarification_reason: str | None
    broad_query: bool

    @property
    def entities(self) -> dict[str, str]:
        return self.normalized_entities

    @property
    def high_confidence_entities(self) -> dict[str, str]:
        return {key: value for key, value in self.normalized_entities.items() if self.entity_confidence.get(key, 0.0) >= 0.85}

    @property
    def medium_confidence_entities(self) -> dict[str, str]:
        return {key: value for key, value in self.normalized_entities.items() if 0.60 <= self.entity_confidence.get(key, 0.0) < 0.85}

    @property
    def high_confidence_fields(self) -> frozenset[str]:
        return frozenset(field for field in self.requested_fields if self.field_confidence.get(field, 0.0) >= 0.85)

    @property
    def explicit_domains(self) -> frozenset[str]:
        normalized = self.original_question.casefold()
        return frozenset(
            domain for domain, markers in _DOMAIN_MARKERS.items()
            if any(marker.casefold() in normalized for marker in markers)
        )


def _find_entities(question: str) -> tuple[dict[str, str], dict[str, float]]:
    entities: dict[str, str] = {}
    confidence: dict[str, float] = {}
    for entity_type, values in ENTITY_ALIASES.items():
        matches = [(canonical, alias) for canonical, aliases in values.items() for alias in aliases if _contains_alias(question, alias)]
        if len({canonical for canonical, _ in matches}) == 1:
            canonical, alias = max(matches, key=lambda item: len(item[1]))
            entities[entity_type] = canonical
            confidence[entity_type] = 1.0 if len(alias) >= 3 else 0.90
        elif matches:
            canonical, _ = max(matches, key=lambda item: len(item[1]))
            entities[entity_type] = canonical
            confidence[entity_type] = 0.70
    return entities, confidence


def _find_fields(question: str) -> tuple[frozenset[str], dict[str, float]]:
    fields: set[str] = set()
    confidence: dict[str, float] = {}
    explicit = {"risk_status", "risk_level", "trend_direction", "key_complaints", "brand_attitude", "recall_risk", "legal_risk"}
    for field, aliases in FIELD_ALIASES.items():
        if any(_contains_alias(question, alias) for alias in aliases):
            fields.add(field)
            confidence[field] = 1.0 if field in explicit else 0.80
    return frozenset(fields), confidence


def _date_range(question: str) -> str | None:
    month = re.search(r"(?<!\d)(20\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.]|$)", question)
    year = re.search(r"(?<!\d)(20\d{2})(?:[-/.])", question)
    if month:
        return f"{month.group(1)}-{int(month.group(2)):02d}"
    if year:
        return year.group(1)
    return "current" if any(token in question for token in ("latest", "recent", "current", "currently")) else None


def _needs_c_entity(question: str, targets: list[str] | None) -> bool:
    return (not targets or bool(set(targets).intersection({"c_current", "c_history"}))) and any(marker in question for marker in _C_ENTITY_MARKERS)


def _auxiliary_query(entities: dict[str, str], fields: frozenset[str]) -> str | None:
    parts = [value for key, value in entities.items() if key != "date_range"]
    parts.extend(sorted(field.replace("_", " ") for field in fields))
    return " ".join(parts) or None


def plan_query(question: str, *, targets: list[str] | None = None) -> QueryPlan:
    original = question.strip()
    normalized = re.sub(r"\s+", " ", original.casefold())
    entities, entity_confidence = _find_entities(normalized)
    if date_range := _date_range(normalized):
        entities["date_range"] = date_range
        entity_confidence["date_range"] = 1.0
    fields, field_confidence = _find_fields(normalized)
    has_subject = any(entity_confidence.get(key, 0.0) >= 0.85 for key in ("brand", "vehicle_model"))
    clarification = _needs_c_entity(normalized, targets) and not has_subject and any(marker in normalized for marker in _RISK_MARKERS)
    return QueryPlan(original, entities, fields, entity_confidence, field_confidence, _auxiliary_query(entities, fields), clarification, "c_entity_required" if clarification else None, not bool(set(entities) - {"date_range"}) and not fields)


def select_auxiliary_target(
    plan: QueryPlan,
    targets: list[str],
    *,
    missing_targets: Iterable[str] | None = None,
) -> str | None:
    """Choose the one target allowed to receive an auxiliary retrieval.

    Primary retrieval already queries every selected target.  The auxiliary
    query exists only to repair a high-confidence miss, so it must not fan
    out once per domain.  Prefer the domain represented by an explicit
    question marker, then the domain implied by the entity type.
    """

    if not targets:
        return None

    missing = set(missing_targets) if missing_targets is not None else None
    candidate_targets = [target for target in targets if missing is None or target in missing]
    if not candidate_targets:
        return None

    def first_target(predicate) -> str | None:
        return next((target for target in candidate_targets if predicate(target)), None)

    explicit = plan.explicit_domains
    selected = first_target(lambda target: target.startswith("c_") and "c" in explicit)
    if selected:
        return selected
    selected = first_target(lambda target: target == "b_business" and "b" in explicit)
    if selected:
        return selected
    selected = first_target(lambda target: target == "kol" and "kol" in explicit)
    if selected:
        return selected

    if set(plan.high_confidence_entities).intersection({"brand", "vehicle_model"}):
        selected = first_target(lambda target: target.startswith("c_"))
        if selected:
            return selected
    if "regulation_topic" in plan.high_confidence_entities:
        selected = first_target(lambda target: target == "b_business")
        if selected:
            return selected
    if plan.high_confidence_fields:
        selected = first_target(lambda target: target.startswith("c_"))
        if selected:
            return selected
    return candidate_targets[0]


def _payload_topic_values(payload: dict[str, Any]) -> list[Any]:
    values: list[Any] = [payload.get(key) for key in ("regulation_topic", "title", "published_summary")]
    values.extend(payload.get("tags") or [])
    for related in payload.get("related_entities") or []:
        if isinstance(related, dict):
            values.extend(related.get(key) for key in ("standard_name", "name", "topic"))
    return values


def _has_usable_value(values: Iterable[Any]) -> bool:
    return any(isinstance(value, str) and _normal_text(value) not in _UNKNOWN_VALUES for value in values)


def _entity_match_for_record(key: str, expected: str, record: Any, payload: dict[str, Any]) -> bool | None:
    """Return None when this record does not carry this entity dimension.

    Cross-domain records are intentionally sparse: C records usually carry
    brand/model but not a regulation topic, while B regulation records often
    carry the topic but not a vehicle subject. Missing dimensions must not be
    treated as a mismatch across domains; an explicitly present value that
    disagrees with the query still is a mismatch.
    """
    if key == "regulation_topic":
        values = _payload_topic_values(payload)
        if not _has_usable_value(values):
            return None if getattr(record, "target_knowledge_base", None) in {"c_current", "c_history"} else False
        return regulation_topic_matches(expected, values)
    if key == "date_range":
        return expected == "current" or str(payload.get("business_date") or getattr(record, "business_date", "")).startswith(expected)
    values = payload.get("regions") if key == "region" and isinstance(payload.get("regions"), list) else [payload.get(key)]
    if key in {"brand", "vehicle_model"} and not _has_usable_value(values):
        return None if getattr(record, "target_knowledge_base", None) == "b_business" else False
    if key == "region" and not _has_usable_value(values):
        return None
    return any(entity_matches(key, expected, value) for value in values)


def score_candidate(plan: QueryPlan, record: Any, base_score: float | None) -> tuple[float, bool, dict[str, Any]]:
    """Score one parent record and report only allowed hard filters."""
    payload = record.payload_json if isinstance(getattr(record, "payload_json", None), dict) else {}
    details: dict[str, Any] = {"entity_matches": {}, "field_matches": []}
    score = float(base_score or 0.0)
    hard_filter = False
    weights = {"brand": 0.30, "vehicle_model": 0.30, "regulation_topic": 0.15, "region": 0.10, "date_range": 0.05}
    for key, expected in plan.high_confidence_entities.items():
        matched = _entity_match_for_record(key, expected, record, payload)
        if matched is None:
            continue
        details["entity_matches"][key] = matched
        if matched:
            score += weights.get(key, 0.0)
        elif key in {"brand", "vehicle_model", "regulation_topic"}:
            hard_filter = True
    for field in plan.requested_fields:
        if field.casefold() in (getattr(record, "retrieval_text", "") or "").casefold():
            details["field_matches"].append(field)
            score += 0.15
    for key, expected in plan.medium_confidence_entities.items():
        matched = _entity_match_for_record(key, expected, record, payload)
        if matched is None:
            continue
        details["entity_matches"][key] = matched
        score += 0.12 if matched else -0.10
    return score, hard_filter, details
