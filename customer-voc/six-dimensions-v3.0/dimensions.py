from __future__ import annotations

"""
六个维度计算函数 —— 每个维度一个独立函数，互不读取对方中间结果
（文档 §2.5："新增维度只加新函数，不动旧逻辑"）。
"""

from collections import Counter
from datetime import datetime, timedelta, date as date_cls
from typing import Any, Dict, List, Optional

from core import (
    AggBucket, AggKey, RiskEvent,
    POSITIVE_9, NEUTRAL_3, NEGATIVE_16, EMOTION_28,
    PART_SAFETY_THRESHOLDS, LAWSUIT_GENERAL_THRESHOLD,
    min_sample_gate, emotion_ratios,
)


def _sum_counters(buckets: List[AggBucket]) -> Counter:
    total = Counter()
    for b in buckets:
        total.update(b.emotion_28_counter)
    return total


# ------------------------------------------------------------------
# 维度1：旅程阶段情感曲线
# ------------------------------------------------------------------
@min_sample_gate()
def journey_curve(
    buckets: Dict[AggKey, AggBucket],
    model: str, region: str, journey_stage: str,
    date_from: str, date_to: str,
) -> List[Dict[str, Any]]:
    by_date: Dict[str, List[AggBucket]] = {}
    for k, b in buckets.items():
        if k.model != model or k.region != region or k.journey_stage != journey_stage:
            continue
        if not (date_from <= k.published_date <= date_to):
            continue
        by_date.setdefault(k.published_date, []).append(b)

    points = []
    for d in sorted(by_date):
        bs = by_date[d]
        total = sum(b.signal_count for b in bs)
        pos = sum(b.positive_count for b in bs)
        neg = sum(b.negative_count for b in bs)
        neu = sum(b.neutral_count for b in bs)
        emo_counter = _sum_counters(bs)
        points.append({
            "date": d,
            "signal_count": total,
            "positive_ratio": round(pos / total * 100, 1) if total else 0.0,
            "negative_ratio": round(neg / total * 100, 1) if total else 0.0,
            "neutral_ratio": round(neu / total * 100, 1) if total else 0.0,
            "emotion_28_ratio": emotion_ratios(emo_counter, total),
        })
    return points


# ------------------------------------------------------------------
# 维度2：触点NPS预测
# ------------------------------------------------------------------
def _nps_for_window(buckets: Dict[AggKey, AggBucket], model: str, region: str,
                     start: date_cls, end: date_cls) -> Optional[Dict[str, Any]]:
    matched = [
        b for k, b in buckets.items()
        if k.model == model and k.region == region
        and start.isoformat() <= k.published_date <= end.isoformat()
    ]
    total = sum(b.signal_count for b in matched)
    if total == 0:
        return None
    emo = _sum_counters(matched)

    # 【新版】正向9类 → 推荐者，负面16类 → 贬损者，中性3类 → 被动者
    promoter = sum(emo.get(e, 0.0) for e in POSITIVE_9)
    detractor = sum(emo.get(e, 0.0) for e in NEGATIVE_16)
    passive = sum(emo.get(e, 0.0) for e in NEUTRAL_3)

    promoter_ratio = promoter / total
    detractor_ratio = detractor / total
    passive_ratio = passive / total
    nps_raw = (promoter_ratio - detractor_ratio) * 10
    nps_score = round((nps_raw + 10) / 2, 1)
    return {
        "signal_count": total,
        "nps_score": nps_score,
        "promoter_ratio": round(promoter_ratio * 100, 1),
        "detractor_ratio": round(detractor_ratio * 100, 1),
        "passive_ratio": round(passive_ratio * 100, 1),
        "emotion_28_ratio": emotion_ratios(emo, total),
    }


@min_sample_gate()
def nps_predict(
    buckets: Dict[AggKey, AggBucket], model: str, region: str,
    today: Optional[date_cls] = None,
) -> Optional[Dict[str, Any]]:
    today = today or datetime.now().date()
    current = _nps_for_window(buckets, model, region, today - timedelta(days=90), today)
    if current is None:
        return None
    prior_end = today - timedelta(days=30)
    prior = _nps_for_window(buckets, model, region, prior_end - timedelta(days=90), prior_end)
    prior_score = prior["nps_score"] if prior else current["nps_score"]
    current["change_vs_30d_ago"] = round(current["nps_score"] - prior_score, 1)
    return current


# ------------------------------------------------------------------
# 维度3：关键抱怨识别
# ------------------------------------------------------------------
@min_sample_gate()
def complaint_ranking(
    buckets: Dict[AggKey, AggBucket], model: str, region: str,
    date_from: str, date_to: str, journey_stage: Optional[str] = None,
    top_n: int = 10, today: Optional[date_cls] = None,
) -> List[Dict[str, Any]]:
    today = today or datetime.now().date()
    week1_start = (today - timedelta(days=7)).isoformat()
    week2_start = (today - timedelta(days=14)).isoformat()
    week2_end = week1_start

    matched = [
        b for k, b in buckets.items()
        if k.model == model and k.region == region
        and (journey_stage is None or k.journey_stage == journey_stage)
        and date_from <= k.published_date <= date_to
    ]

    def _topic_freq(lo: str, hi: str) -> Counter:
        c = Counter()
        for k, b in buckets.items():
            if k.model != model or k.region != region:
                continue
            if journey_stage is not None and k.journey_stage != journey_stage:
                continue
            if not (lo <= k.published_date < hi):
                continue
            c.update(b.topic_counter)
        return c

    week1_freq = _topic_freq(week1_start, (today + timedelta(days=1)).isoformat())
    week2_freq = _topic_freq(week2_start, week2_end)

    topic_emotion: Dict[str, Counter] = {}
    for b in matched:
        for tname, te in b.topic_emotion_counter.items():
            topic_emotion.setdefault(tname, Counter()).update(te)

    all_topics = set(week1_freq) | set(week2_freq)
    rows = []
    for t in all_topics:
        c1 = week1_freq.get(t, 0)
        c2 = week2_freq.get(t, 0)
        if c2 == 0:
            trend = "上升(新增)" if c1 > 0 else "持平"
        elif c1 > c2 * 1.2:
            trend = f"上升 ({(c1 - c2) / c2 * 100:+.1f}%)"
        elif c1 < c2 * 0.8:
            trend = f"下降 ({(c1 - c2) / c2 * 100:+.1f}%)"
        else:
            trend = "持平"
        te = topic_emotion.get(t, Counter())
        te_total = sum(te.values()) or 1
        rows.append({
            "topic": t,
            "week1_cnt": c1,
            "week2_cnt": c2,
            "trend": trend,
            "signal_count": c1 + c2,
            "emotion_28_ratio": emotion_ratios(te, te_total),
        })
    rows.sort(key=lambda r: r["signal_count"], reverse=True)
    return rows[:top_n]


# ------------------------------------------------------------------
# 维度4：品牌净推荐意愿
# ------------------------------------------------------------------
def _brand_sentiment_window(buckets: Dict[AggKey, AggBucket], brand: str, region: str,
                             start: str, end: str) -> Optional[Dict[str, Any]]:
    matched = [b for k, b in buckets.items() if k.brand == brand and k.region == region and start <= k.published_date < end]
    total = sum(b.signal_count for b in matched)
    if total == 0:
        return None
    pos = sum(b.positive_count for b in matched)
    neg = sum(b.negative_count for b in matched)
    neu = sum(b.neutral_count for b in matched)
    emo = _sum_counters(matched)
    return {
        "signal_count": total,
        "positive_ratio": round(pos / total * 100, 1),
        "negative_ratio": round(neg / total * 100, 1),
        "neutral_ratio": round(neu / total * 100, 1),
        "emotion_28_ratio": emotion_ratios(emo, total),
    }


@min_sample_gate()
def brand_sentiment(
    buckets: Dict[AggKey, AggBucket], brand: str, region: str,
    date_from: str, date_to: str,
) -> Optional[Dict[str, Any]]:
    current = _brand_sentiment_window(buckets, brand, region, date_from, date_to)
    if current is None:
        return None
    d1 = datetime.fromisoformat(date_from).date()
    d2 = datetime.fromisoformat(date_to).date()
    window_len = (d2 - d1).days or 1
    prev_from = (d1 - timedelta(days=window_len)).isoformat()
    prev_to = date_from
    prior = _brand_sentiment_window(buckets, brand, region, prev_from, prev_to)

    current["attitude"] = "正面" if current["positive_ratio"] > current["negative_ratio"] else "负面"
    if prior is None:
        current["trend"] = "持平"
    elif current["positive_ratio"] > prior["positive_ratio"]:
        current["trend"] = "改善"
    elif current["positive_ratio"] < prior["positive_ratio"]:
        current["trend"] = "恶化"
    else:
        current["trend"] = "持平"
    return current


# ------------------------------------------------------------------
# 维度5：召回早期信号
# ------------------------------------------------------------------
def recall_alert(
    risk_events: List[RiskEvent], model: str, part: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(risk_events[0].timestamp.tzinfo if risk_events else None)
    window_start = now - timedelta(hours=72)
    hits = [
        e for e in risk_events
        if e.hit_type == "recall" and e.model == model and e.part_name == part
        and window_start <= e.timestamp <= now
        and e.sentiment_label == "negative"
    ]
    threshold = PART_SAFETY_THRESHOLDS.get(part, PART_SAFETY_THRESHOLDS["_default"])
    hit_count = len(hits)
    emo = Counter()
    for e in hits:
        for k2, v in e.emotion_28.items():
            emo[k2] += v
    return {
        "model": model,
        "part": part,
        "window": "72h",
        "hit_count": hit_count,
        "threshold": threshold,
        "alert_triggered": hit_count >= threshold,
        "first_hit_time": min((e.timestamp for e in hits), default=None),
        "emotion_28_ratio": emotion_ratios(emo, hit_count),
    }


# ------------------------------------------------------------------
# 维度6：维权/集体诉讼风险
# ------------------------------------------------------------------
def legal_risk_alert(
    risk_events: List[RiskEvent], brand: str, region: str,
    date_from: datetime, date_to: datetime,
) -> Dict[str, Any]:
    hits = [
        e for e in risk_events
        if e.brand == brand and e.region == region
        and e.hit_type in ("lawsuit_general", "lawsuit_intent")
        and date_from <= e.timestamp <= date_to
    ]
    intent_hits = [e for e in hits if e.hit_type == "lawsuit_intent"]
    general_hits = [e for e in hits if e.hit_type == "lawsuit_general"]

    alert_triggered = len(intent_hits) >= 1 or len(general_hits) >= LAWSUIT_GENERAL_THRESHOLD
    if intent_hits:
        risk_level = "高"
    elif len(general_hits) >= LAWSUIT_GENERAL_THRESHOLD:
        risk_level = "中"
    elif general_hits:
        risk_level = "低"
    else:
        risk_level = "无"

    emo = Counter()
    for e in hits:
        for k2, v in e.emotion_28.items():
            emo[k2] += v
    return {
        "brand": brand,
        "region": region,
        "hit_count": len(hits),
        "intent_hit_count": len(intent_hits),
        "general_hit_count": len(general_hits),
        "alert_triggered": alert_triggered,
        "risk_level": risk_level,
        "emotion_28_ratio": emotion_ratios(emo, len(hits)),
    }