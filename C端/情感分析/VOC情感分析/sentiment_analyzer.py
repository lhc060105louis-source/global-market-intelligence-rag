#!/usr/bin/env python
"""Local sentiment and sarcasm analysis through the Ollama HTTP API."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from llm_client import chat_json, is_ollama_provider, ollama_host, text_model
import voc_rules


DEFAULT_HOST = ollama_host()
CPU_FALLBACK_HOST = "http://127.0.0.1:11435"
DEFAULT_TEXT_MODEL = text_model()
DEFAULT_SEED = 42
LABELS = ["正面情感", "中性情感", "负面情感", "混合"]
LEGACY_LABEL_ALIASES = {
    "positive": "正面情感",
    "neutral": "中性情感",
    "negative": "负面情感",
    "轻度负面情感": "负面情感",
    "高危负面情感": "负面情感",
    "mixed": "混合",
    "unknown": "中性情感",
}
DOMAINS = ["general", "automotive", "unknown"]
TOPICS = [
    "app_software",
    "ota_software",
    "battery_range",
    "charging",
    "air_conditioning",
    "customer_service",
    "repair_maintenance",
    "delivery_experience",
    "test_drive",
    "price_competition",
    "brand_reputation",
    "safety_recall",
    "sales_experience",
    "vehicle_quality",
    "infotainment",
    "other",
]
TOPIC_IDS = [
    "app_login_issue", "app_crash", "app_slow_response", "app_remote_control", "app_notification_delay", "app_ui_usability",
    "ota_update_failure", "ota_slow_download", "ota_bug_after_update", "ota_feature_missing", "ota_version_rollout",
    "range_lower_than_claimed", "winter_range_drop", "battery_degradation", "range_display_inaccurate", "high_energy_consumption",
    "slow_charging", "charging_failure", "charger_compatibility", "charging_app_issue", "charging_cost", "charging_network",
    "ac_cooling_issue", "ac_heating_issue", "cabin_noise", "seat_comfort", "odor_issue", "cabin_space",
    "service_no_response", "service_slow_response", "service_attitude", "service_inconsistent", "complaint_handling",
    "repair_delay", "repair_quality", "warranty_dispute", "spare_parts_delay", "maintenance_cost", "service_booking_issue",
    "delivery_delay", "delivery_process", "vehicle_condition", "document_issue", "pickup_experience",
    "test_drive_booking", "test_drive_availability", "test_drive_route", "sales_during_test_drive", "test_drive_vehicle_issue",
    "price_too_high", "price_cut_complaint", "promotion_confusion", "resale_value", "competitor_price",
    "brand_trust", "brand_image", "public_opinion", "word_of_mouth", "brand_expectation",
    "brake_noise", "brake_failure", "airbag_issue", "recall_notice", "safety_warning", "battery_safety",
    "sales_attitude", "sales_misleading", "contract_issue", "order_process", "sales_follow_up",
    "body_quality", "paint_defect", "abnormal_noise", "water_leak", "door_window_issue", "component_failure",
    "screen_lag", "navigation_issue", "voice_assistant_issue", "bluetooth_issue", "media_playback_issue", "carplay_androidauto",
    "unclear_feedback", "general_complaint", "general_praise", "non_vehicle_topic", "other_unclassified",
]
DEFAULT_TOPIC_BY_CATEGORY = {
    "app_software": "app_slow_response",
    "ota_software": "ota_bug_after_update",
    "battery_range": "range_lower_than_claimed",
    "charging": "charging_failure",
    "air_conditioning": "cabin_noise",
    "customer_service": "service_no_response",
    "repair_maintenance": "repair_quality",
    "delivery_experience": "delivery_delay",
    "test_drive": "test_drive_booking",
    "price_competition": "price_too_high",
    "brand_reputation": "brand_trust",
    "safety_recall": "safety_warning",
    "sales_experience": "sales_attitude",
    "vehicle_quality": "component_failure",
    "infotainment": "screen_lag",
    "other": "other_unclassified",
}
TOPIC_ALIASES = {
    "general": "other",
    "delivery": "delivery_experience",
    "after_sales": "customer_service",
    "safety": "safety_recall",
    "price": "price_competition",
    "brand_trust": "brand_reputation",
    "compliance": "other",
    "product_quality": "vehicle_quality",
    "unknown": "other",
}
BUSINESS_STAGES = [
    "pre_sales",
    "sales",
    "after_sales",
    "full_journey",
]
JOURNEY_STAGES = [
    "pre_sales_awareness",
    "pre_sales_lead",
    "sales_experience",
    "after_sales_service",
    "after_sales_community",
    "full_journey",
]
COARSE_STAGE_TO_JOURNEY = {
    "pre_sales": "pre_sales_awareness",
    "sales": "sales_experience",
    "after_sales": "after_sales_service",
    "full_journey": "full_journey",
}
STAGE_ALIASES = {
    "general": "full_journey",
    "unknown": "full_journey",
}
EMOTIONS = [
    "喜悦",
    "高兴",
    "满足",
    "兴奋",
    "感动",
    "爱慕",
    "信任",
    "期待",
    "惊讶",
    "好奇",
    "平静",
    "无感",
    "焦虑",
    "担忧",
    "紧张",
    "恐惧",
    "悲伤",
    "失望",
    "沮丧",
    "愤怒",
    "厌恶",
    "抱怨",
    "羞愧",
    "内疚",
    "嫉妒",
    "羡慕",
    "鄙视",
    "困惑",
]
DEFAULT_EMOTION_BY_LABEL = {
    "正面情感": "满足",
    "中性情感": "平静",
    "负面情感": "抱怨",
    "轻度负面情感": "抱怨",
    "高危负面情感": "抱怨",
    "混合": "满足",
    "positive": "满足",
    "negative": "抱怨",
    "mixed": "满足",
    "neutral": "平静",
    "unknown": "无感",
}
POSITIVE_EMOTION_SET = voc_rules.POSITIVE_EMOTIONS
NEUTRAL_EMOTION_SET = voc_rules.NEUTRAL_EMOTIONS
NEGATIVE_EMOTION_SET = voc_rules.NEGATIVE_EMOTIONS
MILD_NEGATIVE_EMOTION_SET = voc_rules.MILD_NEGATIVE_EMOTIONS
HIGH_RISK_NEGATIVE_EMOTION_SET = voc_rules.HIGH_RISK_NEGATIVE_EMOTIONS

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": LABELS},
        "topic": {"type": "string", "enum": TOPICS},
        "journey_stage": {"type": "string", "enum": JOURNEY_STAGES},
        "sentiment_spec": {
            "oneOf": [
                {"type": "string", "enum": EMOTIONS},
                {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "string", "enum": EMOTIONS},
                },
            ],
        },
        "sentiment_score": {"type": "number"},
        "sentiment_strength": {"type": "integer"},
        "sentiment_categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": TOPICS},
                    "strength": {"type": "integer"},
                },
                "required": ["code", "strength"],
            },
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["vehicle_model", "part", "symptom", "brand", "other"]},
                    "name": {"type": "string"},
                    "sentiment_score": {"type": "number"},
                },
                "required": ["type", "name", "sentiment_score"],
            },
        },
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string", "enum": TOPIC_IDS},
                },
                "required": ["topic_id"],
            },
        },
    },
    "required": [
        "label",
        "topic",
        "journey_stage",
        "sentiment_spec",
        "sentiment_score",
        "sentiment_strength",
        "sentiment_categories",
        "entities",
        "topics",
    ],
}

SYSTEM_PROMPT = """你是客户信号标准化情感分析器。输入是一条用户评论文本和上游 CSV 行上下文。
只按 JSON schema 输出，不要输出解释性正文。

字段要求：
- label 只能是 正面情感、中性情感、负面情感、混合。
- topic、sentiment_categories.code、entities.type、topics.topic_id 必须使用 schema 枚举，不要自造值。
- topic 是一级业务分类，topics.topic_id 是二级问题分类。每个 topic_id 必须属于对应 topic，禁止输出跨类组合；sentiment_categories.code 必须与 topic 一致。
- 先选择最具体的 topic_id，再根据给定层级确定唯一的 topic，不要根据参考案例强行套用不相关标签。
- sentiment_spec 必须从 28 种情绪中选择：喜悦、高兴、满足、兴奋、感动、爱慕、信任、惊讶、好奇、平静、期待、无感、困惑、失望、沮丧、抱怨、担忧、紧张、焦虑、恐惧、悲伤、愤怒、厌恶、羞愧、内疚、嫉妒、鄙视、羡慕。
- 情绪分组：正向=喜悦/高兴/满足/兴奋/感动/爱慕/信任/期待/好奇；中性=平静/无感/惊讶；负面=焦虑/担忧/紧张/恐惧/悲伤/失望/沮丧/愤怒/厌恶/抱怨/羞愧/内疚/嫉妒/羡慕/鄙视/困惑。只要是负面情绪，统一输出 label=负面情感，不要区分轻度负面或高危负面。
- 只要一条评论里既有正面情绪又有负面情绪，label 必须是 混合，sentiment_spec 输出两个情绪词数组，第一个对应正面情绪，第二个对应负面情绪。
- 情感判断必须以说话者真实态度为准，不以单个正面词或负面词的字面含义为准。
- 遇到反讽、讽刺、阴阳怪气、夸张反话，或字面夸奖但后文描述故障、风险、等待、损失、投诉、质量问题、服务失败等负面事实时，应按整体真实态度判为负面或混合，不能因为“真棒、优秀、贴心”等词判为正面。
- 反讽、讽刺、阴阳怪气不需要单独输出字段，只体现在最终 label、sentiment_spec、sentiment_score 中。
- entities 用来抽取车型、品牌、部件、症状等实体，并给出对应 sentiment_score。
- 不要输出 summary、reasoning、suggested_action、evidence、emotions、confidence、domain 等额外字段。

判断原则：
1. 先识别 28 类细粒度情绪，再按情绪分组得到最终 label。
2. 同时有满意点和不满意点时用 混合。
3. 字面正面但真实态度负面时，按真实态度输出 负面情感；如果确实同时存在真实满意点和真实不满意点，才输出 混合。
4. 中文汽车安全问题必须具体识别，例如“幽灵刹车、误刹、急刹、辅助驾驶突然刹车”归入 safety_recall，并抽取 symptom 实体。
5. 不要输出 risk_level 字段；召回/维权关键词命中由本地规则在批处理标准化事件中生成。"""


def topic_hierarchy_prompt() -> str:
    grouped: dict[str, list[str]] = {topic: [] for topic in TOPICS}
    for topic_id, definition in voc_rules.TOPIC_DEFINITIONS.items():
        parent = str(definition.get("parent_category") or "other")
        grouped.setdefault(parent, []).append(topic_id)
    lines = [
        f"- {parent}: {', '.join(topic_ids)}"
        for parent, topic_ids in grouped.items()
        if topic_ids
    ]
    return "\n\n一级 topic 与二级 topic_id 的唯一层级：\n" + "\n".join(lines)


def system_prompt() -> str:
    return SYSTEM_PROMPT + topic_hierarchy_prompt() + voc_rules.taxonomy_prompt_summary()


def request_json(
    host: str, route: str, payload: dict[str, Any] | None = None
) -> Any:
    url = f"{host.rstrip('/')}{route}"
    data = (
        None
        if payload is None
        else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"无法连接 Ollama ({url})。请先启动 Ollama 服务。"
        ) from exc


def installed_models(host: str) -> set[str]:
    response = request_json(host, "/api/tags")
    return {item["name"] for item in response.get("models", [])}


def is_cuda_backend_error(error: Exception) -> bool:
    message = str(error)
    return any(
        marker in message
        for marker in (
            "CUDA error",
            "device kernel image is invalid",
            "0xc0000409",
        )
    )


def start_cpu_ollama(host: str = "127.0.0.1:11435") -> None:
    env = os.environ.copy()
    env["OLLAMA_HOST"] = host
    env["OLLAMA_LLM_LIBRARY"] = "cpu"
    creationFlags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        creationflags=creationFlags,
    )


def wait_for_ollama(host: str, attempts: int = 30) -> bool:
    for _ in range(attempts):
        try:
            request_json(host, "/api/tags")
            return True
        except RuntimeError:
            time.sleep(0.5)
    return False


def valid_label(value: Any) -> str:
    text = str(value or "").strip()
    text = LEGACY_LABEL_ALIASES.get(text, text)
    return text if text in LABELS else "中性情感"


def label_from_emotions(emotion_names: list[str], fallback: str) -> str:
    has_positive = any(name in POSITIVE_EMOTION_SET for name in emotion_names)
    has_negative = any(name in NEGATIVE_EMOTION_SET for name in emotion_names)
    if has_positive and has_negative:
        return "混合"
    if has_positive:
        return "正面情感"
    if any(name in NEGATIVE_EMOTION_SET for name in emotion_names):
        return "负面情感"
    if any(name in NEUTRAL_EMOTION_SET for name in emotion_names):
        return "中性情感"
    return valid_label(fallback)


def valid_choice(value: Any, choices: list[str], default: str) -> str:
    return value if value in choices else default


def normalize_topic(value: Any, default: str = "other") -> str:
    text = str(value or "").strip()
    text = TOPIC_ALIASES.get(text, text)
    return text if text in TOPICS else default


def normalize_topic_id(value: Any, fallback_category: str = "other") -> str:
    text = str(value or "").strip()
    if text in TOPIC_IDS:
        return text
    category = normalize_topic(fallback_category)
    return DEFAULT_TOPIC_BY_CATEGORY.get(category, "other_unclassified")


def parent_topic_for(topic_id: str) -> str:
    definition = voc_rules.TOPIC_DEFINITIONS.get(topic_id, {})
    return normalize_topic(definition.get("parent_category"), "other")


def normalize_stage(value: Any, default: str = "full_journey") -> str:
    text = str(value or "").strip()
    text = STAGE_ALIASES.get(text, text)
    return text if text in BUSINESS_STAGES else default


def normalize_journey_stage(value: Any, default: str = "full_journey") -> str:
    text = str(value or "").strip()
    if text in JOURNEY_STAGES:
        return text
    return COARSE_STAGE_TO_JOURNEY.get(normalize_stage(text, default), default)


def clamp_confidence(value: Any, default: float = 0.7) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(-1.0, min(1.0, score))


def clamp_strength(value: Any, default: int = 3) -> int:
    try:
        strength = int(round(float(value)))
    except (TypeError, ValueError):
        strength = default
    return max(1, min(5, strength))


def normalize_emotion_names(label: str, emotion_names: list[str], sentiment_spec: Any = "") -> list[str]:
    names = [name for name in emotion_names if name in EMOTIONS]
    for spec in voc_rules.raw_sentiment_specs(sentiment_spec):
        if spec in EMOTIONS and spec not in names:
            names.insert(0, spec)

    if label in {"positive", "正面情感"}:
        names = [name for name in names if name in POSITIVE_EMOTION_SET]
    elif label in {"negative", "负面情感", "轻度负面情感", "高危负面情感"}:
        names = [name for name in names if name in NEGATIVE_EMOTION_SET]
    elif label in {"neutral", "中性情感"}:
        names = [name for name in names if name in NEUTRAL_EMOTION_SET]
    elif label in {"mixed", "混合"}:
        positive = next((name for name in names if name in POSITIVE_EMOTION_SET), "满足")
        negative = next((name for name in names if name in NEGATIVE_EMOTION_SET), "抱怨")
        names = [positive, negative]
    elif label == "unknown":
        names = [name for name in names if name == DEFAULT_EMOTION_BY_LABEL[label]]

    if not names and label in DEFAULT_EMOTION_BY_LABEL:
        names = [DEFAULT_EMOTION_BY_LABEL[label]]
    return names


def normalize_result(
    result: dict[str, Any], source_text: str
) -> dict[str, Any]:
    raw_emotions = result.get("emotions", [])
    if not isinstance(raw_emotions, list):
        raw_emotions = []

    label = valid_label(result.get("label"))
    emotion_names: list[str] = []
    for item in raw_emotions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if name in EMOTIONS and name not in emotion_names:
            emotion_names.append(name)
    if not emotion_names and label in {"mixed", "混合"}:
        emotion_names.extend(["满足", "抱怨"])
    elif not emotion_names and label in DEFAULT_EMOTION_BY_LABEL:
        emotion_names.append(DEFAULT_EMOTION_BY_LABEL[label])
    raw_sentiment_spec = result.get("sentiment_spec", "")
    sentiment_spec: str | list[str] = voc_rules.raw_sentiment_specs(raw_sentiment_spec)
    if not sentiment_spec:
        sentiment_spec = ""
    elif len(sentiment_spec) == 1:
        sentiment_spec = sentiment_spec[0]
    if not isinstance(sentiment_spec, list) and sentiment_spec not in EMOTIONS:
        sentiment_spec = emotion_names[0] if emotion_names else DEFAULT_EMOTION_BY_LABEL.get(label, "无感")
    detected_emotions = [
        spec for spec in voc_rules.raw_sentiment_specs(raw_sentiment_spec)
        if spec in EMOTIONS
    ]
    for name in detected_emotions:
        if name not in emotion_names:
            emotion_names.append(name)
    if emotion_names:
        label = label_from_emotions(emotion_names, label)
    emotion_names = normalize_emotion_names(label, emotion_names, sentiment_spec)
    if emotion_names:
        sentiment_spec = emotion_names if label in {"mixed", "混合"} else emotion_names[0]
    inferred_domain, inferred_topic, inferred_stage = voc_rules.infer_business_context(source_text)
    domain = valid_choice(result.get("domain"), DOMAINS, inferred_domain)
    topic = normalize_topic(result.get("topic"), inferred_topic)
    journey_stage = normalize_journey_stage(result.get("journey_stage"))
    business_stage = normalize_stage(result.get("business_stage"), inferred_stage)
    sentiment_score = clamp_score(result.get("sentiment_score"))
    if result.get("sentiment_score") is None:
        sentiment_score = {
            "positive": 0.7,
            "正面情感": 0.7,
            "negative": -0.7,
            "负面情感": -1.0,
            "轻度负面情感": -1.0,
            "高危负面情感": -1.0,
            "mixed": 0.0,
            "混合": 0.0,
            "neutral": 0.0,
            "中性情感": 0.0,
        }.get(label, 0.0)
    sentiment_strength = clamp_strength(result.get("sentiment_strength"), 1 if label in {"neutral", "中性情感"} else 4)
    raw_categories = result.get("sentiment_categories", [])
    if not isinstance(raw_categories, list):
        raw_categories = []
    sentiment_categories: list[dict[str, Any]] = []
    for item in raw_categories:
        if not isinstance(item, dict):
            continue
        code = normalize_topic(item.get("code"), topic)
        sentiment_categories.append({
            "code": code,
            "label": str(item.get("label") or code),
            "strength": clamp_strength(item.get("strength"), sentiment_strength),
        })
    if not sentiment_categories:
        sentiment_categories.append({"code": topic, "label": topic, "strength": sentiment_strength})
    raw_entities = result.get("entities", [])
    if not isinstance(raw_entities, list):
        raw_entities = []
    entities: list[dict[str, Any]] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        entity_type = str(item.get("type") or "other").strip()
        if entity_type not in {"vehicle_model", "part", "symptom", "brand", "other"}:
            entity_type = "other"
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        taxonomy_match = voc_rules.normalize_entity_with_taxonomy(entity_type, name)
        if taxonomy_match:
            name = taxonomy_match["name"]
        normalized_name = str(item.get("normalized_name") or name).strip()
        if taxonomy_match:
            normalized_name = name
        entities.append({
            "type": entity_type,
            "name": name,
            "normalized_name": normalized_name,
            "sentiment_score": clamp_score(item.get("sentiment_score"), sentiment_score),
        })
    voc_rules.enrich_entities_from_text(entities, source_text, sentiment_score)
    raw_topics = result.get("topics", [])
    if not isinstance(raw_topics, list):
        raw_topics = []
    topics: list[dict[str, str]] = []
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        topic_id = normalize_topic_id(item.get("topic_id"), topic)
        topics.append({"topic_id": topic_id, "name": str(item.get("name") or topic_id)})
    if not topics:
        topic_id = normalize_topic_id("", topic)
        topics.append({"topic_id": topic_id, "name": topic_id})
    if inferred_domain == "automotive" and topic == "other":
        domain = inferred_domain
        topic = inferred_topic
        journey_stage = normalize_journey_stage(journey_stage, COARSE_STAGE_TO_JOURNEY.get(inferred_stage, "full_journey"))
    if topic == "app_software" and inferred_topic in {
        "charging",
        "battery_range",
        "air_conditioning",
        "ota_software",
    }:
        topic = inferred_topic
        journey_stage = normalize_journey_stage(journey_stage, COARSE_STAGE_TO_JOURNEY.get(inferred_stage, "full_journey"))
    if inferred_domain == "automotive" and inferred_stage != "full_journey":
        journey_stage = normalize_journey_stage(journey_stage, COARSE_STAGE_TO_JOURNEY.get(inferred_stage, "full_journey"))
    topic = normalize_topic(topic)
    if topic != "other":
        if not sentiment_categories or normalize_topic(sentiment_categories[0].get("code")) == "other":
            sentiment_categories = [
                {"code": topic, "label": topic, "strength": sentiment_strength}
            ]
        if not topics or topics[0].get("topic_id") == "other_unclassified":
            topic_id = normalize_topic_id("", topic)
            topics = [{"topic_id": topic_id, "name": topic_id}]
    if journey_stage == "full_journey":
        journey_stage = normalize_journey_stage(result.get("business_stage"), COARSE_STAGE_TO_JOURNEY.get(business_stage, "full_journey"))
    if domain == "general":
        topic = "other"
        journey_stage = "full_journey"

    # A valid child label is more specific than the coarse topic. Enforce the
    # one-to-one taxonomy relationship before the result can enter the case store.
    primary_topic_id = topics[0]["topic_id"] if topics else "other_unclassified"
    expected_parent = parent_topic_for(primary_topic_id)
    if primary_topic_id != "other_unclassified" and expected_parent != "other":
        topic = expected_parent
        domain = "automotive"
        topics = [
            item
            for item in topics
            if parent_topic_for(item["topic_id"]) == topic
        ]
        sentiment_categories = [
            {
                "code": topic,
                "label": topic,
                "strength": sentiment_strength,
            }
        ]
    elif topic != "other":
        primary_topic_id = normalize_topic_id("", topic)
        topics = [{"topic_id": primary_topic_id, "name": primary_topic_id}]
        sentiment_categories = [
            {
                "code": topic,
                "label": topic,
                "strength": sentiment_strength,
            }
        ]
    sentiment_score = voc_rules.standard_sentiment_score(label)
    sentiment_strength = voc_rules.standard_sentiment_strength(label, topic)
    sentiment_spec = voc_rules.standard_sentiment_spec(
        label,
        emotion_names if label in {"mixed", "混合"} else sentiment_spec,
    )
    sentiment_categories = [
        {**item, "strength": sentiment_strength}
        for item in sentiment_categories
    ]

    return {
        "label": label,
        "confidence": clamp_confidence(result.get("confidence")),
        "domain": domain,
        "topic": topic,
        "journey_stage": journey_stage,
        "sentiment_spec": sentiment_spec,
        "sentiment_score": sentiment_score,
        "sentiment_strength": sentiment_strength,
        "sentiment_categories": sentiment_categories,
        "entities": entities,
        "topics": topics,
    }


def analyze(
    host: str,
    model: str,
    text: str,
    context: str = "",
    retrieved_examples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    request_content: dict[str, Any] = {
        "text": text.strip(),
        "context": context.strip() or "未提供",
    }
    if retrieved_examples:
        request_content["reference_cases"] = retrieved_examples
        request_content["reference_case_instruction"] = (
            "参考案例只用于理解隐晦表达和分类边界。独立分析当前文本，"
            "不要复制案例中的品牌、车型、部件或其他实体。"
        )
    user_content = json.dumps(request_content, ensure_ascii=False)
    payload = {
        "model": model,
        "stream": False,
        "format": RESULT_SCHEMA,
        "options": {"temperature": 0, "seed": DEFAULT_SEED},
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_content},
        ],
    }
    result = chat_json(payload["messages"], RESULT_SCHEMA, model=model, host=host)
    if not isinstance(result, dict):
        raise RuntimeError(f"模型返回的 JSON 不是对象：{result}")
    return normalize_result(result, text)


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return the compact CLI response while keeping internal fields available."""
    hidden_fields = {
        "confidence",
        "domain",
        "topic",
        "business_stage",
        "risk_level",
    }
    return {
        key: value
        for key, value in result.items()
        if key not in hidden_fields
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="分析文本情感与业务主题。"
    )
    parser.add_argument("text", nargs="?", default="", help="要分析的文字")
    parser.add_argument(
        "--context", default="", help="对话背景、说话者立场或前后文"
    )
    parser.add_argument("--model", help="模型名称")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Ollama 服务地址")
    parser.add_argument("--list-models", action="store_true", help="列出本地模型")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        host = args.host
        if args.list_models:
            if not is_ollama_provider():
                raise RuntimeError("当前是 remote 模式，只有 LLM_PROVIDER=ollama 时才能列出本地模型。")
            if host == DEFAULT_HOST and wait_for_ollama(CPU_FALLBACK_HOST, attempts=1):
                host = CPU_FALLBACK_HOST
            models = installed_models(host)
            print(json.dumps(sorted(models), ensure_ascii=False, indent=2))
            return 0
        if not args.text:
            raise ValueError("请提供要分析的文字。")

        model = args.model or DEFAULT_TEXT_MODEL
        if is_ollama_provider():
            if host == DEFAULT_HOST and wait_for_ollama(CPU_FALLBACK_HOST, attempts=1):
                host = CPU_FALLBACK_HOST
            models = installed_models(host)
            if model not in models:
                raise RuntimeError(
                    f"本地没有模型 {model!r}。请先运行：ollama pull {model}"
                )
        try:
            result = analyze(
                host,
                model,
                args.text,
                args.context,
            )
        except RuntimeError as exc:
            if not is_ollama_provider() or host != DEFAULT_HOST or not is_cuda_backend_error(exc):
                raise
            start_cpu_ollama()
            if not wait_for_ollama(CPU_FALLBACK_HOST):
                raise RuntimeError("CPU 模式 Ollama 启动失败。") from exc
            models = installed_models(CPU_FALLBACK_HOST)
            if model not in models:
                raise RuntimeError(
                    f"本地没有模型 {model!r}。请先运行：ollama pull {model}"
                ) from exc
            result = analyze(
                CPU_FALLBACK_HOST,
                model,
                args.text,
                args.context,
            )
        print(json.dumps(public_result(result), ensure_ascii=False, indent=2))
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
