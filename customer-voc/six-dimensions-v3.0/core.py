from __future__ import annotations

"""
客户级统一情感档案 —— 核心模块
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# 【新版】28类情感 与 正向/中性/负面 三组的划分
# 依据：客户级统一情感档案-开发需求说明 v3.html §1.2
# ------------------------------------------------------------------
# 正向9类
POSITIVE_9 = ["喜悦", "高兴", "满足", "兴奋", "感动", "爱慕", "信任", "期待", "好奇"]
# 中性3类
NEUTRAL_3 = ["平静", "无感", "惊讶"]
# 负面16类
NEGATIVE_16 = [
    "焦虑", "担忧", "紧张", "恐惧", "悲伤", "失望",
    "沮丧", "愤怒", "厌恶", "抱怨", "羞愧", "内疚",
    "嫉妒", "羡慕", "鄙视", "困惑"
]

# 28类情感（顺序：正向 → 中性 → 负面）
EMOTION_28 = POSITIVE_9 + NEUTRAL_3 + NEGATIVE_16
assert len(EMOTION_28) == 28

# 28类 → 正负中 归并映射
EMOTION_TO_SENTIMENT: Dict[str, str] = {}
for _e in POSITIVE_9:
    EMOTION_TO_SENTIMENT[_e] = "positive"
for _e in NEUTRAL_3:
    EMOTION_TO_SENTIMENT[_e] = "neutral"
for _e in NEGATIVE_16:
    EMOTION_TO_SENTIMENT[_e] = "negative"

# [兼容旧版] 保留旧变量名，方便 dimensions.py 过渡
# 但建议 dimensions.py 也改用新变量名
POSITIVE_6 = POSITIVE_9   # 兼容旧代码，但实际是9类
NEUTRAL_4 = NEUTRAL_3     # 兼容旧代码，但实际是3类
MILD_NEGATIVE_8 = []      # 新版无轻度负面分类
HIGH_RISK_NEGATIVE_10 = NEGATIVE_16  # 新版负面16类

# ... 后续代码不变 ...

DEFAULTS = {
    "model": "未识别车型",
    "brand": "未识别品牌",
    "region": "未知",
    "journey_stage": "全程",
    "channel": "未知渠道",
    "language": "未知语种",
}

LANGUAGE_TO_REGION = {"DE": "德国", "FR": "法国", "UK": "英国", "IT": "意大利", "ES": "西班牙"}

MODEL_TO_BRAND = {
    "Model_Y": "Tesla", "Model_3": "Tesla",
    "Dolphin": "BYD", "Seal": "BYD",
    "MG4": "MG", "Marvel_R": "MG",
    "ID.3": "VW", "ID.4": "VW",
}

RECALL_KEYWORDS = ["刹车失灵", "自燃", "断轴", "召回", "质检总局投诉"]
LAWSUIT_KEYWORDS_GENERAL = ["消费者协会", "赔偿", "12315", "投诉平台"]
LAWSUIT_KEYWORDS_INTENT = ["已联系律师", "准备起诉", "集体诉讼", "起诉"]

PART_SAFETY_THRESHOLDS = {
    "制动系统": 3, "转向系统": 3, "电池": 3,
    "车机": 8, "内饰": 10,
    "_default": 5,
}

LAWSUIT_GENERAL_THRESHOLD = 5
MIN_SAMPLE_SIZE = 5


def _match_any(name: str, keywords: List[str]) -> bool:
    return any(re.search(re.escape(kw), name) for kw in keywords)


def _date_only(published_at: str) -> str:
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).date().isoformat()


# ------------------------------------------------------------------
# 7键聚合桶
# ------------------------------------------------------------------
@dataclass(frozen=True)
class AggKey:
    model: str
    brand: str
    region: str
    journey_stage: str
    channel: str
    language: str
    published_date: str


@dataclass
class AggBucket:
    signal_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    sentiment_strength_sum: int = 0
    emotion_28_counter: Counter = field(default_factory=Counter)
    topic_counter: Counter = field(default_factory=Counter)
    topic_emotion_counter: Dict[str, Counter] = field(default_factory=dict)
    recall_keyword_hit_count: int = 0
    lawsuit_keyword_hit_general_count: int = 0
    lawsuit_keyword_hit_intent_count: int = 0


@dataclass
class RiskEvent:
    timestamp: datetime
    model: str
    brand: str
    region: str
    part_name: str
    hit_type: str
    sentiment_label: str
    emotion_28: Dict[str, float]


# ------------------------------------------------------------------
# 核心处理器
# ------------------------------------------------------------------
class SignalProcessor:
    def __init__(self) -> None:
        self._seen: set[Tuple[str, str]] = set()
        self.buckets: Dict[AggKey, AggBucket] = {}
        self.risk_events: List[RiskEvent] = []

    def process(self, raw: Dict[str, Any]) -> None:
        published_at = str(raw["published_at"])
        published_date = _date_only(published_at)
        ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

        journey_stage = raw.get("journey_stage") or DEFAULTS["journey_stage"]
        channel = raw.get("channel") or DEFAULTS["channel"]
        language = raw.get("language") or DEFAULTS["language"]
        region = LANGUAGE_TO_REGION.get(language, DEFAULTS["region"])

        entities = raw.get("entities", [])
        sentiment_label = raw["sentiment_label"]
        sentiment_strength = int(raw.get("sentiment_strength", 1))
        source_id = str(raw["source_id"])

        # 【关键】直接从原始信号读取 emotion_28
        emotion_28 = raw.get("emotion_28", {}) or {}

        # ---- 风险关键词匹配 ----
        recall_hit = False
        lawsuit_general_hit = False
        lawsuit_intent_hit = False
        hit_part_name = None

        # 【方案一】同时支持中文和英文：部件 / part
        part_entity_name = next(
            (str(e["name"]) for e in entities if e.get("type") in ("部件", "part")),
            None
        )

        for ent in entities:
            name = str(ent.get("name", ""))
            if _match_any(name, RECALL_KEYWORDS):
                recall_hit = True
                hit_part_name = hit_part_name or part_entity_name or name
            if _match_any(name, LAWSUIT_KEYWORDS_INTENT):
                lawsuit_intent_hit = True
                hit_part_name = hit_part_name or part_entity_name or name
            elif _match_any(name, LAWSUIT_KEYWORDS_GENERAL):
                lawsuit_general_hit = True
                hit_part_name = hit_part_name or part_entity_name or name

        # ---- 提取车型 ----
        # 【方案一】同时支持中文和英文：车型 / vehicle_model
        model_entities = [
            e for e in entities
            if e.get("type") in ("车型", "vehicle_model")
        ]
        models = [str(e["name"]) for e in model_entities] or [DEFAULTS["model"]]

        for model in models:
            dedup_key = (source_id, model)
            if dedup_key in self._seen:
                continue
            self._seen.add(dedup_key)

            brand = MODEL_TO_BRAND.get(model, DEFAULTS["brand"])

            key = AggKey(
                model=model, brand=brand, region=region,
                journey_stage=journey_stage, channel=channel,
                language=language, published_date=published_date,
            )
            bucket = self.buckets.setdefault(key, AggBucket())

            # ---- 累加聚合桶 ----
            bucket.signal_count += 1
            if sentiment_label == "positive":
                bucket.positive_count += 1
            elif sentiment_label == "negative":
                bucket.negative_count += 1
            else:
                bucket.neutral_count += 1
            bucket.sentiment_strength_sum += sentiment_strength

            # 累加 28 类情感
            for emo in EMOTION_28:
                bucket.emotion_28_counter[emo] += float(emotion_28.get(emo, 0.0))

            # ---- 话题累加 ----
            for topic in raw.get("topics", []):
                tname = str(topic.get("name", ""))
                if not tname:
                    continue
                bucket.topic_counter[tname] += 1
                te_counter = bucket.topic_emotion_counter.setdefault(tname, Counter())
                for emo in EMOTION_28:
                    te_counter[emo] += float(emotion_28.get(emo, 0.0))

            # ---- 风险命中累加 ----
            if recall_hit:
                bucket.recall_keyword_hit_count += 1
            if lawsuit_general_hit:
                bucket.lawsuit_keyword_hit_general_count += 1
            if lawsuit_intent_hit:
                bucket.lawsuit_keyword_hit_intent_count += 1

            # ---- 风险事件流水 ----
            if recall_hit or lawsuit_general_hit or lawsuit_intent_hit:
                hit_type = "recall" if recall_hit else ("lawsuit_intent" if lawsuit_intent_hit else "lawsuit_general")
                self.risk_events.append(RiskEvent(
                    timestamp=ts, model=model, brand=brand, region=region,
                    part_name=hit_part_name or model, hit_type=hit_type,
                    sentiment_label=sentiment_label, emotion_28=dict(emotion_28),
                ))
                if recall_hit and (lawsuit_general_hit or lawsuit_intent_hit):
                    other_type = "lawsuit_intent" if lawsuit_intent_hit else "lawsuit_general"
                    self.risk_events.append(RiskEvent(
                        timestamp=ts, model=model, brand=brand, region=region,
                        part_name=hit_part_name or model, hit_type=other_type,
                        sentiment_label=sentiment_label, emotion_28=dict(emotion_28),
                    ))


# ------------------------------------------------------------------
# 最小样本量门禁
# ------------------------------------------------------------------
def min_sample_gate(min_n: int = MIN_SAMPLE_SIZE):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            def _gate(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                n = item.get("signal_count", item.get("total_cnt"))
                if n is not None and n < min_n:
                    return None
                return item
            if isinstance(result, list):
                return [r for r in (_gate(item) for item in result) if r is not None]
            elif isinstance(result, dict):
                return _gate(result)
            return result
        return wrapper
    return decorator


# ------------------------------------------------------------------
# emotion_ratios：算占比（百分比）
# ------------------------------------------------------------------
def emotion_ratios(counter: Counter, total: float) -> Dict[str, float]:
    if not total:
        return {e: 0.0 for e in EMOTION_28}
    return {e: round(counter.get(e, 0.0) / total * 100, 1) for e in EMOTION_28}