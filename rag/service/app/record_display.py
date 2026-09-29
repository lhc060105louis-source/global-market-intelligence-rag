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
    "pre_sales_awareness": "售前认知",
    "pre_sales_consideration": "售前考虑",
    "purchase": "购买",
    "delivery": "交付",
    "ownership": "用车",
    "after_sales": "售后服务",
    "after_sales_service": "售后服务",
    "renewal": "续购",
}
_ATTITUDE_LABELS = {
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "mixed": "混合",
}
_RISK_LABELS = {
    "recall_signal": "召回风险信号",
    "legal_action_signal": "法律风险信号",
    "class_action": "集体诉讼风险",
    "overheat": "过热风险",
    "battery": "电池",
    "consumer_rights": "消费者权益",
    "brand_trust": "品牌信任",
}
_TREND_LABELS = {
    "up": "上升",
    "down": "下降",
    "stable": "稳定",
    "increasing": "上升",
    "decreasing": "下降",
    "unchanged": "稳定",
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
        return f"统计期为{start}至{end}"
    if start or end:
        return f"统计期为{start or end}"
    return None


def _join_clauses(clauses: Sequence[str], *, separator: str = "，") -> str:
    return separator.join(clause for clause in clauses if clause)


def _journey_summary(payload: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    stage = _label(payload.get("journey_stage"), _JOURNEY_STAGE_LABELS)
    count = _format_number(payload.get("signal_count"))
    if stage and count:
        first = f"{stage}阶段共{count}条反馈"
    elif count:
        first = f"共{count}条反馈"
    elif stage:
        first = f"{stage}阶段有消费者反馈"
    else:
        first = ""

    clauses = [first]
    for key, label in (
        ("positive_ratio", "正面情绪占"),
        ("neutral_ratio", "中性情绪占"),
        ("negative_ratio", "负面情绪占"),
    ):
        value = _format_percent(result.get(key))
        if value:
            clauses.append(label + value)
    trend = _label(result.get("trend_direction"), _TREND_LABELS)
    if trend:
        clauses.append("整体趋势" + trend)
    body = _join_clauses(clauses)
    period = _period_text(payload)
    if period:
        body += ("；" if body else "") + period
    return body + "。" if body else "暂无可展示摘要。"


def _nps_summary(result: Mapping[str, Any]) -> str:
    first: list[str] = []
    nps = _format_number(result.get("nps_value"))
    change = _format_signed_number(result.get("change_from_previous"))
    if nps:
        first.append(f"NPS预测值为{nps}")
    if change:
        first.append(f"较前期{change}")
    second: list[str] = []
    for key, label in (
        ("promoter_ratio", "推荐者占"),
        ("passive_ratio", "中立者占"),
        ("detractor_ratio", "贬损者占"),
    ):
        value = _format_percent(result.get(key))
        if value:
            second.append(label + value)
    body = _join_clauses(first)
    if second:
        body += ("；" if body else "") + _join_clauses(second)
    return body + "。" if body else "暂无可展示摘要。"


def _key_complaints_summary(result: Mapping[str, Any]) -> str:
    raw_complaints = result.get("complaints")
    if not isinstance(raw_complaints, Sequence) or isinstance(raw_complaints, (str, bytes)):
        return "暂无可展示摘要。"
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
            attributes.append(f"{frequency}次")
            total_frequency += float(_number(item.get("frequency")) or 0)
        if trend:
            attributes.append("趋势" + trend)
        if topic:
            details.append(topic + (f"（{_join_clauses(attributes)}）" if attributes else ""))
    if not details:
        return "暂无可展示摘要。"
    body = "主要抱怨集中在" + _join_clauses(details, separator="、")
    if total_frequency:
        total = _format_number(total_frequency)
        body += f"，重点项共{total}次"
    body += "；其余抱怨见结构化明细。"
    return body


def _brand_attitude_summary(result: Mapping[str, Any]) -> str:
    clauses: list[str] = []
    attitude = _label(result.get("attitude"), _ATTITUDE_LABELS)
    if attitude:
        clauses.append("当前品牌态度为" + attitude)
    for key, label in (
        ("positive_ratio", "正面情绪占"),
        ("neutral_ratio", "中性情绪占"),
        ("negative_ratio", "负面情绪占"),
    ):
        value = _format_percent(result.get(key))
        if value:
            clauses.append(label + value)
    trend = _label(result.get("trend_direction"), _TREND_LABELS)
    if trend:
        clauses.append("整体趋势" + trend)
    body = _join_clauses(clauses)
    return body + "。" if body else "暂无可展示摘要。"


def _risk_summary(result: Mapping[str, Any], threshold_exceeded: bool) -> str:
    subject = _label(result.get("part"), _RISK_LABELS) or _label(result.get("risk_type"), _RISK_LABELS) or "当前风险"
    hit_count = _format_number(result.get("hit_count"))
    threshold = _format_number(result.get("threshold"))
    if threshold_exceeded:
        if hit_count and threshold:
            body = f"{subject}当前命中{hit_count}次，已达到{threshold}次预警阈值，当前形成正式风险预警。"
        elif hit_count:
            body = f"{subject}当前命中{hit_count}次，当前形成正式风险预警。"
        else:
            body = f"{subject}当前形成正式风险预警。"
    else:
        if hit_count and threshold:
            body = f"{subject}当前命中{hit_count}次，预警阈值为{threshold}次，当前为正常风险评估，尚未触发正式风险预警。"
        elif hit_count:
            body = f"{subject}当前命中{hit_count}次，当前为正常风险评估，尚未触发正式风险预警。"
        else:
            body = f"{subject}当前为正常风险评估，尚未触发正式风险预警。"
    risk_status = _label(result.get("risk_status"))
    if risk_status:
        body += f"风险状态为{risk_status}。"
    return body


def _business_summary(payload: Mapping[str, Any]) -> str:
    for key in ("published_summary", "business_impact", "recommended_action"):
        value = _text(payload.get(key))
        if value:
            return value
    return "暂无可展示摘要。"


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
            additions.append(f"项目{project}当前阶段为{stage}")
        if performance and performance != first:
            additions.append("表现：" + performance)
        if additions:
            return first + "；" + "；".join(additions)
    return first or "暂无可展示摘要。"


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
        summary = "暂无可展示摘要。"
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
        summary = "暂无可展示摘要。"

    return {
        "display_category": category,
        "risk_state": risk_state,
        "display_summary": summary,
    }
