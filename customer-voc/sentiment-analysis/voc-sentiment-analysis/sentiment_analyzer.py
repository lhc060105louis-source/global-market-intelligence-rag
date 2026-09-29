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
LABELS = ["positive", "neutral", "negative", "mixed"]
LEGACY_LABEL_ALIASES = {
    "positive": "positive",
    "neutral": "neutral",
    "negative": "negative",
    "mixed": "mixed",
    "unknown": "neutral",
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
    "joy",
    "happiness",
    "satisfaction",
    "excitement",
    "moved",
    "affection",
    "trust",
    "anticipation",
    "surprise",
    "curiosity",
    "calm",
    "indifference",
    "anxiety",
    "worry",
    "nervousness",
    "fear",
    "sadness",
    "disappointment",
    "frustration",
    "anger",
    "disgust",
    "complaint",
    "shame",
    "guilt",
    "jealousy",
    "envy",
    "contempt",
    "confusion",
]
DEFAULT_EMOTION_BY_LABEL = {
    "positive": "satisfaction",
    "neutral": "calm",
    "negative": "complaint",
    "mixed": "satisfaction",
    "unknown": "indifference",
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

SYSTEM_PROMPT = """You are a customer feedback sentiment classifier. Analyze one user comment with its upstream CSV row context.
Return only JSON that conforms to the supplied schema. Do not include explanatory prose.

Requirements:
- label must be one of: positive, neutral, negative, mixed.
- Use only schema values for topic, sentiment_categories.code, entities.type, and topics.topic_id.
- topic is a top-level business category; topics.topic_id is a specific issue. Every topic_id must belong to the selected topic, and sentiment_categories.code must match that topic.
- Select the most specific topic_id first, then choose its unique parent topic. Do not force an unrelated label from a reference example.
- sentiment_spec must be one of these 28 emotions: joy, happiness, satisfaction, excitement, moved, affection, trust, anticipation, surprise, curiosity, calm, indifference, confusion, disappointment, frustration, complaint, worry, nervousness, anxiety, fear, sadness, anger, disgust, shame, guilt, jealousy, contempt, envy.
- Positive emotions are joy, happiness, satisfaction, excitement, moved, affection, trust, anticipation, and curiosity. Neutral emotions are calm, indifference, and surprise. All remaining emotions are negative. Use label=negative for negative emotion and do not split it into mild or high-risk labels.
- If a comment contains both positive and negative emotion, use label=mixed and return a two-item sentiment_spec array: positive emotion first, negative emotion second.
- Judge the speaker's actual attitude, not the literal polarity of an isolated word.
- For sarcasm, irony, exaggerated retorts, or literal praise followed by a failure, delay, loss, quality issue, or service problem, classify the overall attitude as negative or mixed as appropriate. Do not classify it as positive just because it contains words such as “great,” “excellent,” or “thoughtful.”
- Sarcasm does not need a separate output field; reflect it in label, sentiment_spec, and sentiment_score.
- Extract entities such as vehicle models, brands, components, and symptoms, with a sentiment_score for each.
- Do not return extra fields such as summary, reasoning, suggested_action, evidence, emotions, confidence, or domain.

Decision rules:
1. Identify the most specific emotion, then map it to the final sentiment label.
2. Use mixed when genuine satisfaction and dissatisfaction are both present.
3. If the literal wording is positive but the actual attitude is negative, use negative. Use mixed only when both genuine satisfaction and dissatisfaction are present.
4. Identify vehicle safety issues precisely, such as phantom braking, unintended braking, sudden braking, or unexpected braking by driver assistance. Map them to safety_recall and extract a symptom entity.
5. Do not return risk_level. Local rules add recall and consumer-rights keyword matches during batch normalization."""


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
    return "\n\nUnique parent-child hierarchy for topics and topic_id values:\n" + "\n".join(lines)


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
            f"Could not connect to Ollama at {url}. Start the Ollama service first."
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
    return text if text in LABELS else "neutral"


def label_from_emotions(emotion_names: list[str], fallback: str) -> str:
    has_positive = any(name in POSITIVE_EMOTION_SET for name in emotion_names)
    has_negative = any(name in NEGATIVE_EMOTION_SET for name in emotion_names)
    if has_positive and has_negative:
        return "mixed"
    if has_positive:
        return "positive"
    if any(name in NEGATIVE_EMOTION_SET for name in emotion_names):
        return "negative"
    if any(name in NEUTRAL_EMOTION_SET for name in emotion_names):
        return "neutral"
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

    if label == "positive":
        names = [name for name in names if name in POSITIVE_EMOTION_SET]
    elif label == "negative":
        names = [name for name in names if name in NEGATIVE_EMOTION_SET]
    elif label == "neutral":
        names = [name for name in names if name in NEUTRAL_EMOTION_SET]
    elif label == "mixed":
        positive = next((name for name in names if name in POSITIVE_EMOTION_SET), "satisfaction")
        negative = next((name for name in names if name in NEGATIVE_EMOTION_SET), "complaint")
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
    if not emotion_names and label == "mixed":
        emotion_names.extend(["satisfaction", "complaint"])
    elif not emotion_names and label in DEFAULT_EMOTION_BY_LABEL:
        emotion_names.append(DEFAULT_EMOTION_BY_LABEL[label])
    raw_sentiment_spec = result.get("sentiment_spec", "")
    sentiment_spec: str | list[str] = voc_rules.raw_sentiment_specs(raw_sentiment_spec)
    if not sentiment_spec:
        sentiment_spec = ""
    elif len(sentiment_spec) == 1:
        sentiment_spec = sentiment_spec[0]
    if not isinstance(sentiment_spec, list) and sentiment_spec not in EMOTIONS:
        sentiment_spec = emotion_names[0] if emotion_names else DEFAULT_EMOTION_BY_LABEL.get(label, "indifference")
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
        sentiment_spec = emotion_names if label == "mixed" else emotion_names[0]
    inferred_domain, inferred_topic, inferred_stage = voc_rules.infer_business_context(source_text)
    domain = valid_choice(result.get("domain"), DOMAINS, inferred_domain)
    topic = normalize_topic(result.get("topic"), inferred_topic)
    journey_stage = normalize_journey_stage(result.get("journey_stage"))
    business_stage = normalize_stage(result.get("business_stage"), inferred_stage)
    sentiment_score = clamp_score(result.get("sentiment_score"))
    if result.get("sentiment_score") is None:
        sentiment_score = {"positive": 0.7, "negative": -1.0, "mixed": 0.0, "neutral": 0.0}.get(label, 0.0)
    sentiment_strength = clamp_strength(result.get("sentiment_strength"), 1 if label == "neutral" else 4)
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
        emotion_names if label == "mixed" else sentiment_spec,
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
        "context": context.strip() or "not provided",
    }
    if retrieved_examples:
        request_content["reference_cases"] = retrieved_examples
        request_content["reference_case_instruction"] = (
            "Use reference cases only to interpret indirect phrasing and category boundaries. Analyze the current text independently. "
            "Do not copy brands, vehicle models, components, or other entities from reference cases."
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
        raise RuntimeError(f"The model returned JSON that is not an object: {result}")
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
        description="Analyze sentiment and business topics in text."
    )
    parser.add_argument("text", nargs="?", default="", help="Text to analyze")
    parser.add_argument(
        "--context", default="", help="Conversation context, speaker stance, or surrounding text"
    )
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Ollama service URL")
    parser.add_argument("--list-models", action="store_true", help="List local models")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        host = args.host
        if args.list_models:
            if not is_ollama_provider():
                raise RuntimeError("The current provider is remote. Local models can only be listed when LLM_PROVIDER=ollama.")
            if host == DEFAULT_HOST and wait_for_ollama(CPU_FALLBACK_HOST, attempts=1):
                host = CPU_FALLBACK_HOST
            models = installed_models(host)
            print(json.dumps(sorted(models), ensure_ascii=False, indent=2))
            return 0
        if not args.text:
            raise ValueError("Provide text to analyze.")

        model = args.model or DEFAULT_TEXT_MODEL
        if is_ollama_provider():
            if host == DEFAULT_HOST and wait_for_ollama(CPU_FALLBACK_HOST, attempts=1):
                host = CPU_FALLBACK_HOST
            models = installed_models(host)
            if model not in models:
                raise RuntimeError(
                    f"Model {model!r} is not installed locally. Run this first: ollama pull {model}"
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
                raise RuntimeError("Could not start Ollama in CPU mode.") from exc
            models = installed_models(CPU_FALLBACK_HOST)
            if model not in models:
                raise RuntimeError(
                    f"Model {model!r} is not installed locally. Run this first: ollama pull {model}"
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
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
