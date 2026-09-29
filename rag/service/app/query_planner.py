"""Deterministic query planning for RAG retrieval.

The user's wording is never rewritten for the first MaxKB retrieval. This
module only derives bounded constraints for filtering, reranking, and one
optional fallback query.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


# Canonical values intentionally use payload_json spellings. The same helper
# canonicalizes both a question alias and the payload value before comparison.
# Brand/model seeds are limited to C-side vehicle identity data and observed
# RAG payload spellings. B-side regulation names are the canonical topic seed.
# The C-side part/symptom taxonomy is intentionally not imported here.
ENTITY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "brand": {
        "Tesla": ("Tesla", "特斯拉"), "BYD": ("BYD", "比亚迪"),
        "Hyundai": ("Hyundai", "现代汽车", "现代"), "NIO": ("NIO", "蔚来"),
        "XPeng": ("XPeng", "小鹏", "小鹏汽车"), "Li Auto": ("Li Auto", "理想", "理想汽车"),
        "Volkswagen": ("Volkswagen", "VW", "大众汽车", "大众"),
        "MG": ("MG",),
    },
    "vehicle_model": {
        "Model Y": ("Model Y", "Model-Y", "Model_Y", "Y车型", "Y 车型"),
        "Model 3": ("Model 3", "Model-3", "Model_3", "3车型", "3 车型"),
        "Dolphin": ("Dolphin", "海豚"),
        "Seal": ("Seal", "海豹"),
        "Atto 3": ("Atto 3", "Atto-3", "元Plus", "元 Plus"),
        "Ioniq 5": ("Ioniq 5", "Ioniq-5", "艾尼氪5"),
        "EL6": ("EL6", "EL 6"),
        "ID.3": ("ID.3", "ID_3", "ID 3"),
        "ID.4": ("ID.4", "ID_4", "ID 4"),
        "MG4 EV": ("MG4 EV", "MG4-EV", "MG4", "MG_4"),
        "Marvel R": ("Marvel R", "Marvel-R", "Marvel_R"),
    },
    "region": {
        "EU": (
            "EU", "E.U.", "欧盟", "欧洲联盟", "欧洲",
            "EU 全域", "EU 进口", "EU 公共采购", "EU + 英国等 60+ 缔约方",
        ),
        "UK": ("UK", "英国", "United Kingdom"),
        "US": ("US", "U.S.", "美国"), "China": ("China", "中国"), "ASEAN": ("ASEAN", "东盟"),
        "Germany": ("Germany", "德国", "DE", "成员国:德国"),
        "France": ("France", "法国", "FR", "成员国:法国"),
        "Italy": ("Italy", "意大利", "IT"),
        "Spain": ("Spain", "西班牙", "ES"),
        "Netherlands": ("Netherlands", "荷兰", "NL"),
        "Norway": ("Norway", "挪威", "NO"),
    },
    "regulation_topic": {
        "General Safety Regulation": (
            "General Safety Regulation", "GSR", "通用安全法规",
            "General Safety Regulation 通用安全法规", "(EU) 2019/2144",
        ),
        "AI Act": (
            "EU AI Act", "AI Act", "人工智能法案", "欧盟人工智能法案",
            "EU 人工智能法案 AI Act", "(EU) 2024/1689",
        ),
        "REACH": (
            "REACH", "REACH / SVHC", "SVHC", "欧盟化学品法规",
            "化学品注册评估授权限制", "(EC) 1907/2006",
        ),
        "Battery Regulation": (
            "Battery Regulation", "电池法规", "欧盟电池法规",
            "EU 电池法规 Battery Regulation", "(EU) 2023/1542",
        ),
        "WVTA": (
            "WVTA", "整车型式批准", "Regulation 2018/858",
            "(EU) 2018/858",
        ),
        "UNECE R155": (
            "UNECE R155", "UN R155", "R155", "CSMS", "UN R155 / CSMS", "网络安全法规",
        ),
        "AFIR": (
            "AFIR", "替代燃料基础设施法规",
            "Alternative Fuels Infrastructure Regulation", "(EU) 2023/1804",
        ),
        "UNECE R156": (
            "UNECE R156", "UN R156", "R156", "SUMS", "软件更新管理",
        ),
        "Data Act": (
            "Data Act", "EU Data Act", "数据法案", "欧盟数据法案",
            "GDPR + EU 数据法案 Data Act", "(EU) 2023/2854",
        ),
        "CBAM": (
            "CBAM", "碳边境调节机制", "Carbon Border Adjustment Mechanism",
            "(EU) 2023/956",
        ),
        "Euro 7": (
            "Euro 7", "Euro7", "欧7", "排放与电池耐久法规",
            "(EU) 2024/1257",
        ),
        "EU CO2 Standards": (
            "EU CO₂ 乘用车/货车排放标准", "CO₂ Standards", "CO2 Standards",
            "EU CO2 standards", "欧盟二氧化碳排放标准",
        ),
        "Clean Vehicles Directive": (
            "Clean Vehicles Directive", "清洁车辆指令", "(EU) 2019/1161",
        ),
        "Foreign Subsidies Regulation": (
            "Foreign Subsidies Regulation", "外国补贴条例", "(EU) 2022/2560",
        ),
        "Euro NCAP": ("Euro NCAP", "Euro NCAP 2026", "安全评估协议"),
        "German KBA/BAFA": (
            "德国联邦补贴与本地化认证要求", "DE-KBA / BAFA", "KBA", "BAFA",
        ),
    },
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "risk_status": ("risk_status", "风险状态", "风险是否正常", "是否正常", "风险情况", "风险开放状态"),
    "risk_level": ("risk_level", "风险等级", "风险级别", "风险程度"),
    "trend_direction": ("trend_direction", "trend", "趋势", "走势", "变化方向", "变化趋势"),
    "key_complaints": ("key_complaints", "主要抱怨", "主要投诉", "投诉点", "用户吐槽", "抱怨点"),
    "complaints": ("complaints", "抱怨", "投诉", "不满", "吐槽"),
    "brand_attitude": ("brand_attitude", "品牌态度", "品牌口碑", "用户对品牌的看法"),
    "attitude": ("attitude", "态度", "口碑", "情感态度"),
    "recall_risk": ("recall_risk", "召回风险", "召回", "安全召回"),
    "legal_risk": ("legal_risk", "法律风险", "法律行动", "法律诉讼", "法律责任"),
    "threshold_exceeded": ("threshold_exceeded", "超过阈值", "达到阈值", "行动信号阈值", "是否超阈值"),
}

_UNKNOWN_VALUES = {"", "unknown", "unknown_brand", "n/a", "na", "none", "null", "未识别", "未知"}
_RISK_MARKERS = ("风险", "法律", "召回", "投诉", "抱怨", "趋势", "风险等级")
_C_ENTITY_MARKERS = ("消费者", "用户", "车型", "品牌", "车", "风险", "抱怨", "投诉", "口碑", "情绪")
_LATIN_ALIAS = re.compile(r"[a-z0-9][a-z0-9 ._-]*$", re.IGNORECASE)
_DOMAIN_MARKERS = {
    "c": ("消费者", "用户", "评论", "情绪", "投诉", "抱怨", "口碑", "召回", "维修"),
    "b": ("商业", "法规", "合规", "客户", "项目", "采购", "充电", "AFIR", "CPO", "电网", "储能"),
    "kol": ("KOL", "达人", "网红", "传播", "合作", "内容创作者"),
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
        # ``EU + 英国等 60+ 缔约方``. Treat a named region inside that
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
    month = re.search(r"(?<!\d)(20\d{2})[-/.](0?[1-9]|1[0-2])(?:月|[-/.]|$)", question)
    year = re.search(r"(?<!\d)(20\d{2})(?:年|[-/.])", question)
    if month:
        return f"{month.group(1)}-{int(month.group(2)):02d}"
    if year:
        return year.group(1)
    return "current" if any(token in question for token in ("最近", "当前", "目前", "latest", "recent")) else None


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
