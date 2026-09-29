"""Shared C-end VOC taxonomy, keyword rules, and entity enrichment."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_TAXONOMY_PATH = Path(__file__).resolve().parent / "ner_taxonomy.json"
_TAXONOMY: dict[str, Any] | None = None
_ALIAS_MAP: dict[tuple[str, str], dict[str, str]] | None = None
_ALIAS_ENTRIES: list[tuple[str, str, str]] | None = None


CATEGORY_LABELS = {
    "app_software": "App Experience",
    "ota_software": "OTA and Software Updates",
    "battery_range": "Battery Range",
    "charging": "Charging Experience",
    "air_conditioning": "Climate and Cabin",
    "customer_service": "Customer Service",
    "repair_maintenance": "Repair and Maintenance",
    "delivery_experience": "Delivery Experience",
    "test_drive": "Test Drive Experience",
    "price_competition": "Pricing and Competition",
    "brand_reputation": "Brand Reputation",
    "safety_recall": "Safety and Recall",
    "sales_experience": "Sales Experience",
    "vehicle_quality": "Vehicle Quality",
    "infotainment": "Infotainment",
    "other": "Other Issues",
}

TOPIC_DEFINITIONS = {
    "app_login_issue": {"parent_category": "app_software", "name": "App Login Issue", "keywords": ("login", "sign in", "unable to log in")},
    "app_crash": {"parent_category": "app_software", "name": "App Crash", "keywords": ("app crash", "crash", "app closes unexpectedly")},
    "app_slow_response": {"parent_category": "app_software", "name": "App Slow Response", "keywords": ("slow app", "lag", "slow response")},
    "app_remote_control": {"parent_category": "app_software", "name": "Remote Control Failure", "keywords": ("remote control", "remote unlocking", "remote start")},
    "app_notification_delay": {"parent_category": "app_software", "name": "Notification Delay", "keywords": ("notification", "push notification", "notification delay")},
    "app_ui_usability": {"parent_category": "app_software", "name": "Poor Interface Usability", "keywords": ("ui", "interface", "hard to use")},
    "ota_update_failure": {"parent_category": "ota_software", "name": "OTA Update Failure", "keywords": ("ota failed", "update failed", "upgrade failed")},
    "ota_slow_download": {"parent_category": "ota_software", "name": "Slow Update Download", "keywords": ("download slow", "slow download", "upgrade is slow")},
    "ota_bug_after_update": {"parent_category": "ota_software", "name": "New Issue After Update", "keywords": ("after update", "new bug", "update introduced a problem")},
    "ota_feature_missing": {"parent_category": "ota_software", "name": "Requested Feature Not Delivered", "keywords": ("feature missing", "requested feature not delivered", "feature not included")},
    "ota_version_rollout": {"parent_category": "ota_software", "name": "Inconsistent Version Rollout", "keywords": ("version rollout", "version", "staggered rollout")},
    "range_lower_than_claimed": {"parent_category": "battery_range", "name": "Real-World Range Below Claims", "keywords": ("lower than advertised", "range below advertised", "falls short")},
    "winter_range_drop": {"parent_category": "battery_range", "name": "Winter Range Loss", "keywords": ("winter range", "range drops in winter", "low temperature", "battery drains")},
    "battery_degradation": {"parent_category": "battery_range", "name": "Battery Degradation", "keywords": ("battery degradation", "capacity loss")},
    "range_display_inaccurate": {"parent_category": "battery_range", "name": "Inaccurate Range Display", "keywords": ("range display", "dashboard range estimate")},
    "high_energy_consumption": {"parent_category": "battery_range", "name": "High Energy Consumption", "keywords": ("energy consumption", "high energy use", "excessive battery drain")},
    "slow_charging": {"parent_category": "charging", "name": "Slow Charging Speed", "keywords": ("slow charging", "charges slowly")},
    "charging_failure": {"parent_category": "charging", "name": "unable to charge", "keywords": ("charging failure", "unable to charge", "will not charge", "charge failed")},
    "charger_compatibility": {"parent_category": "charging", "name": "Charger Compatibility Issue", "keywords": ("compatibility", "charger compatibility")},
    "charging_app_issue": {"parent_category": "charging", "name": "Charging App or QR Issue", "keywords": ("charging app", "QR code scanning", "charging app issue")},
    "charging_cost": {"parent_category": "charging", "name": "Charging Cost Issue", "keywords": ("charging cost", "charging fee", "high charging cost")},
    "charging_network": {"parent_category": "charging", "name": "Insufficient Charger Coverage", "keywords": ("charging network", "charging station", "too few chargers", "insufficient coverage")},
    "ac_cooling_issue": {"parent_category": "air_conditioning", "name": "AC cooling issue", "keywords": ("cooling", "cooling", "does not cool")},
    "ac_heating_issue": {"parent_category": "air_conditioning", "name": "AC heating issue", "keywords": ("heating", "heating", "does not heat")},
    "cabin_noise": {"parent_category": "air_conditioning", "name": "cabin noise", "keywords": ("cabin noise", "wind noise", "noise")},
    "seat_comfort": {"parent_category": "air_conditioning", "name": "seat comfort", "keywords": ("seat", "seat", "uncomfortable")},
    "odor_issue": {"parent_category": "air_conditioning", "name": "cabin odor", "keywords": ("odor", "smell", "odor")},
    "cabin_space": {"parent_category": "air_conditioning", "name": "cabin space issue", "keywords": ("space", "space", "cramped")},
    "service_no_response": {"parent_category": "customer_service", "name": "No Customer Service Response", "keywords": ("never replied", "no response", "does not reply", "ignored")},
    "service_slow_response": {"parent_category": "customer_service", "name": "Slow Customer Service Response", "keywords": ("slow response", "slow handling")},
    "service_attitude": {"parent_category": "customer_service", "name": "Poor Customer Service Attitude", "keywords": ("poor attitude", "rude customer service")},
    "service_inconsistent": {"parent_category": "customer_service", "name": "inconsistent customer service information", "keywords": ("inconsistent", "inconsistent statements", "contradictory")},
    "complaint_handling": {"parent_category": "customer_service", "name": "Complaint Handling Issue", "keywords": ("complaint", "poor complaint handling")},
    "repair_delay": {"parent_category": "repair_maintenance", "name": "Long Repair Wait", "keywords": ("repair delay", "slow repair", "waiting for parts")},
    "repair_quality": {"parent_category": "repair_maintenance", "name": "issue remains after repair", "keywords": ("fixed nothing", "not fixed", "issue unresolved")},
    "warranty_dispute": {"parent_category": "repair_maintenance", "name": "warranty dispute", "keywords": ("warranty", "warranty", "warranty")},
    "spare_parts_delay": {"parent_category": "repair_maintenance", "name": "long wait for parts", "keywords": ("spare parts", "parts", "spare parts")},
    "maintenance_cost": {"parent_category": "repair_maintenance", "name": "High Repair or Maintenance Cost", "keywords": ("maintenance cost", "repair cost", "high cost")},
    "service_booking_issue": {"parent_category": "repair_maintenance", "name": "difficulty booking after-sales service", "keywords": ("booking", "appointment", "unable to book")},
    "delivery_delay": {"parent_category": "delivery_experience", "name": "Delivery Delay", "keywords": ("delivery delay", "delayed delivery", "waiting for delivery", "delayed")},
    "delivery_process": {"parent_category": "delivery_experience", "name": "confusing delivery process", "keywords": ("delivery process", "delivery process", "disorganized process")},
    "vehicle_condition": {"parent_category": "delivery_experience", "name": "Vehicle Condition at Delivery", "keywords": ("vehicle condition", "vehicle delivery condition", "scratches", "defects")},
    "document_issue": {"parent_category": "delivery_experience", "name": "delivery documents or paperwork issue", "keywords": ("document", "documents", "paperwork", "invoice")},
    "pickup_experience": {"parent_category": "delivery_experience", "name": "vehicle pickup experience", "keywords": ("pickup", "vehicle pickup", "vehicle inspection")},
    "test_drive_booking": {"parent_category": "test_drive", "name": "Test Drive Booking Issue", "keywords": ("test drive booking", "test drive appointment")},
    "test_drive_availability": {"parent_category": "test_drive", "name": "Insufficient Test Vehicles", "keywords": ("test drive availability", "test vehicle", "no vehicle available")},
    "test_drive_route": {"parent_category": "test_drive", "name": "Poor Test Drive Route", "keywords": ("test route", "test drive route")},
    "sales_during_test_drive": {"parent_category": "test_drive", "name": "Sales Explanation During Test Drive", "keywords": ("sales explanation", "explanation", "sales presentation")},
    "test_drive_vehicle_issue": {"parent_category": "test_drive", "name": "Test Vehicle Condition Issue", "keywords": ("test vehicle", "test vehicle failure")},
    "price_too_high": {"parent_category": "price_competition", "name": "price too high", "keywords": ("too expensive", "too expensive", "high price")},
    "price_cut_complaint": {"parent_category": "price_competition", "name": "price cut complaint", "keywords": ("price cut", "price cut", "felt betrayed")},
    "promotion_confusion": {"parent_category": "price_competition", "name": "unclear promotional terms", "keywords": ("promotion", "discount", "unclear policy")},
    "resale_value": {"parent_category": "price_competition", "name": "resale value concern", "keywords": ("resale", "resale value", "used vehicle")},
    "competitor_price": {"parent_category": "price_competition", "name": "price comparison with competitors", "keywords": ("competitor price", "competitors", "comparison")},
    "brand_trust": {"parent_category": "brand_reputation", "name": "Brand Trust", "keywords": ("brand trust", "trustworthy", "reliable brand")},
    "brand_image": {"parent_category": "brand_reputation", "name": "brand image", "keywords": ("brand image", "brand image")},
    "public_opinion": {"parent_category": "brand_reputation", "name": "Public Discussion", "keywords": ("public opinion", "public discussion", "reputation")},
    "word_of_mouth": {"parent_category": "brand_reputation", "name": "Word of Mouth", "keywords": ("word of mouth", "reputation", "recommendation")},
    "brand_expectation": {"parent_category": "brand_reputation", "name": "Brand Expectations", "keywords": ("expectation", "anticipation", "brand hopes")},
    "brake_noise": {"parent_category": "safety_recall", "name": "Brake Noise", "keywords": ("brake noise", "brakes squeak", "unusual noise")},
    "brake_failure": {"parent_category": "safety_recall", "name": "Brake Failure", "keywords": ("brake failure", "cannot stop")},
    "airbag_issue": {"parent_category": "safety_recall", "name": "Airbag Issue", "keywords": ("airbag", "airbag safety issue")},
    "recall_notice": {"parent_category": "safety_recall", "name": "Recall Notice Issue", "keywords": ("recall notice", "recall")},
    "safety_warning": {"parent_category": "safety_recall", "name": "Safety Warning", "keywords": ("safety warning", "phantom braking", "unexpected road hazard", "hard braking", "unintended braking", "driver assistance braking unexpectedly")},
    "battery_safety": {"parent_category": "safety_recall", "name": "Battery Safety Hazard", "keywords": ("battery safety", "spontaneous combustion", "fire")},
    "sales_attitude": {"parent_category": "sales_experience", "name": "Sales Attitude", "keywords": ("sales attitude", "rude salesperson")},
    "sales_misleading": {"parent_category": "sales_experience", "name": "Misleading Sales", "keywords": ("misleading", "false advertising")},
    "contract_issue": {"parent_category": "sales_experience", "name": "Contract Issue", "keywords": ("contract", "contract problem")},
    "order_process": {"parent_category": "sales_experience", "name": "order placement process issue", "keywords": ("order process", "placing an order", "order")},
    "sales_follow_up": {"parent_category": "sales_experience", "name": "sales follow-up issue", "keywords": ("follow up", "follow-up", "sales does not respond")},
    "body_quality": {"parent_category": "vehicle_quality", "name": "body quality issue", "keywords": ("body quality", "bodywork", "sheet metal")},
    "paint_defect": {"parent_category": "vehicle_quality", "name": "paint issue", "keywords": ("paint", "paintwork", "paint peeling")},
    "abnormal_noise": {"parent_category": "vehicle_quality", "name": "Unusual Noise Issue", "keywords": ("abnormal noise", "unusual noise", "noise")},
    "water_leak": {"parent_category": "vehicle_quality", "name": "water leak issue", "keywords": ("water leak", "water leak")},
    "door_window_issue": {"parent_category": "vehicle_quality", "name": "door or window issue", "keywords": ("door", "window", "door", "window")},
    "component_failure": {"parent_category": "vehicle_quality", "name": "component failure", "keywords": ("component failure", "failure", "broken")},
    "screen_lag": {"parent_category": "infotainment", "name": "infotainment lag", "keywords": ("screen lag", "infotainment lag", "screen lag")},
    "navigation_issue": {"parent_category": "infotainment", "name": "navigation issue", "keywords": ("navigation", "navigation")},
    "voice_assistant_issue": {"parent_category": "infotainment", "name": "voice assistant issue", "keywords": ("voice assistant", "voice assistant", "voice control")},
    "bluetooth_issue": {"parent_category": "infotainment", "name": "Bluetooth connection issue", "keywords": ("bluetooth", "Bluetooth")},
    "media_playback_issue": {"parent_category": "infotainment", "name": "music or media playback issue", "keywords": ("media playback", "music", "media")},
    "carplay_androidauto": {"parent_category": "infotainment", "name": "CarPlay/Android Auto issue", "keywords": ("carplay", "android auto")},
    "unclear_feedback": {"parent_category": "other", "name": "unclear feedback", "keywords": ("unclear", "unclear feedback")},
    "general_complaint": {"parent_category": "other", "name": "General Complaint", "keywords": ("complaint", "negative feedback")},
    "general_praise": {"parent_category": "other", "name": "General Praise", "keywords": ("praise", "satisfied", "great experience")},
    "non_vehicle_topic": {"parent_category": "other", "name": "Non-Vehicle Topic", "keywords": ("unrelated", "unrelated topic")},
    "other_unclassified": {"parent_category": "other", "name": "Other Unclassified Issue", "keywords": ("other", "unclassified issue")},
}

RECALL_KEYWORDS = (
    "safety recall", "recall notice", "recall letter", "recall campaign", "recall repair",
    "being recalled", "got recalled", "my car recalled", "under recall", "outstanding recall",
    "voluntary recall", "mandatory recall", "should be recalled", "needs a recall",
    "why no recall", "why isn't this recalled",
    "manufacturing defect", "factory defect", "safety defect", "dangerous defect", "known defect",
    "mass recall", "recall all", "faulty batch", "defective batch",
    "death trap", "dangerous to drive", "not roadworthy",
    "total brake failure", "complete brake loss", "lost all brakes",
    "car caught fire", "battery caught fire", "burst into flames",
    "steering locked up", "steering failed", "lost steering",
    "engine cut out while driving", "lost all power on motorway", "lost all power on highway",
    "airbag didn't deploy", "airbag failed to deploy",
    "wheels came off", "wheel fell off",
    "DVSA recall", "KBA recall", "Rapex alert", "EU safety alert",
)
RIGHTS_KEYWORDS = (
    "contacted my lawyer", "spoke to a lawyer", "getting a lawyer", "my lawyer said",
    "my solicitor said", "seeking legal advice", "legal action", "taking legal action",
    "lawsuit", "class action", "class action lawsuit", "group litigation",
    "collective action", "group claim", "join a claim",
    "sue them", "suing them", "going to sue", "take them to court",
    "small claims court", "file a claim", "claim compensation", "demand compensation",
    "full refund", "get my money back", "reject the car", "rejecting the car",
    "consumer rights", "not fit for purpose", "breach of contract",
    "trading standards", "motor ombudsman", "ombudsman complaint",
    "formal complaint", "escalate this",
    "mis-sold", "missold", "false advertising", "not as advertised", "not as described",
    "sign the petition", "make this go viral",
    "anyone else experiencing this", "common problem", "widespread issue",
)

POSITIVE_EMOTIONS = {"joy", "happiness", "satisfaction", "excitement", "moved", "affection", "trust", "anticipation", "curiosity"}
NEUTRAL_EMOTIONS = {"calm", "indifference", "surprise"}
MILD_NEGATIVE_EMOTIONS = {
    "anxiety", "worry", "nervousness", "fear", "sadness", "disappointment", "frustration", "anger",
    "disgust", "complaint", "shame", "guilt", "jealousy", "envy", "contempt", "confusion",
}
HIGH_RISK_NEGATIVE_EMOTIONS = set()
NEGATIVE_EMOTIONS = MILD_NEGATIVE_EMOTIONS | HIGH_RISK_NEGATIVE_EMOTIONS
SENTIMENT_LABELS = {"positive", "neutral", "negative", "mixed"}
DEFAULT_SENTIMENT_SPEC_BY_LABEL = {
    "positive": "satisfaction",
    "neutral": "calm",
    "negative": "complaint",
    "mixed": "satisfaction",
    "unknown": "indifference",
}

TOPIC_KEYWORDS = {
    "safety_recall": ("safety", "recall", "brake", "airbag", "dangerous", "brakes", "braking", "phantom braking", "unexpected road hazard", "hard braking", "unintended braking", "driver assistance braking unexpectedly"),
    "charging": ("charging", "charger", "charge", "charging", "charger", "recharging"),
    "battery_range": ("range", "battery", "mileage", "winter range", "kwh", "state of charge", "battery drains", "energy consumption"),
    "air_conditioning": ("air conditioning", "climate", "temperature", "preheat", "pre-cool", "a/c", "cabin", "cooling", "heating", "odor"),
    "app_software": ("app", "application", "login", "notification", "dark mode", "phone app", "login", "notification", "push notification", "remote control"),
    "ota_software": ("ota", "software update", "firmware", "update failed", "upgrade", "software", "upgrade", "update", "version"),
    "customer_service": ("customer service", "support", "warranty", "dealer never replied", "after-sales", "does not reply", "complaint handling"),
    "repair_maintenance": ("repair", "maintenance", "service interval", "workshop", "fixed nothing", "repair", "maintenance", "warranty", "not fixed", "parts"),
    "delivery_experience": ("delivery", "delayed", "arrived", "handover", "pickup", "vehicle pickup", "waiting for delivery", "delivery delay"),
    "test_drive": ("test drive", "demo drive", "test drive"),
    "price_competition": ("price", "expensive", "cheap", "competitor", "residual", "price", "too expensive", "price cut", "discount", "resale value"),
    "brand_reputation": ("trust", "brand", "reputation", "reliability survey", "brand", "reputation", "trust", "recommendation"),
    "sales_experience": ("sales", "dealer", "salesperson", "quote", "sales", "contract", "placing an order", "order"),
    "vehicle_quality": ("broken", "quality", "dead", "crash", "reliability", "fault", "quality", "failure", "broken", "water leak", "paintwork", "door", "window"),
    "infotainment": ("infotainment", "screen", "display", "carplay", "android auto", "cockpit", "infotainment", "screen", "navigation", "Bluetooth", "voice assistant"),
}


def normalized_for_match(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace(",", "")
        .replace(".", "")
    )


def infer_business_context(text: str) -> tuple[str, str, str]:
    lower_text = normalized_for_match(text)
    matched_topics = [
        topic for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in lower_text for keyword in keywords)
    ]
    if not matched_topics:
        return "general", "other", "full_journey"

    topic = matched_topics[0]
    if topic in {
        "app_software", "ota_software", "battery_range", "charging",
        "air_conditioning", "customer_service", "repair_maintenance",
        "safety_recall", "vehicle_quality", "infotainment",
    }:
        stage = "after_sales"
    elif topic in {"delivery_experience", "test_drive", "price_competition", "sales_experience"}:
        stage = "sales"
    elif topic == "brand_reputation":
        stage = "pre_sales"
    else:
        stage = "full_journey"
    return "automotive", topic, stage


def risk_for(label: str, domain: str, topic: str) -> str:
    if label not in {"negative", "mixed"} or domain != "automotive":
        return "low"
    if topic == "safety_recall":
        return "high"
    if topic in {
        "app_software", "ota_software", "battery_range", "charging",
        "air_conditioning", "customer_service", "repair_maintenance",
        "vehicle_quality", "infotainment",
    }:
        return "medium"
    return "low"


def higher_risk(current: str, minimum: str) -> str:
    order = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    return current if order.get(current, 0) >= order.get(minimum, 0) else minimum


def standard_sentiment_score(label: str) -> float:
    if label == "positive":
        return 1.0
    if label == "negative":
        return -1.0
    return 0.0


def standard_sentiment_strength(label: str, topic: str = "other") -> int:
    if label in {"neutral", "unknown"}:
        return 1
    if topic == "safety_recall":
        return 4
    return 3 if label in {"positive", "negative", "mixed"} else 4


def raw_sentiment_specs(raw_spec: Any = "") -> list[str]:
    if isinstance(raw_spec, list):
        values = raw_spec
    else:
        values = [raw_spec]
    specs: list[str] = []
    for item in values:
        if isinstance(item, dict):
            item = item.get("name", "")
        text = str(item or "").strip()
        if text and text not in specs:
            specs.append(text)
    return specs


def standard_mixed_sentiment_specs(raw_spec: Any = "") -> list[str]:
    specs = raw_sentiment_specs(raw_spec)
    positive = next((spec for spec in specs if spec in POSITIVE_EMOTIONS), "satisfaction")
    negative = next((spec for spec in specs if spec in NEGATIVE_EMOTIONS), "complaint")
    return [positive, negative]


def standard_sentiment_spec(label: str, raw_spec: Any = "") -> str | list[str]:
    text = str(raw_spec or "").strip()
    if label == "mixed":
        return standard_mixed_sentiment_specs(raw_spec)
    if label == "negative" and text in POSITIVE_EMOTIONS | NEUTRAL_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    if label == "positive" and text not in POSITIVE_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    if label == "neutral" and text not in NEUTRAL_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    if label == "negative" and text not in NEGATIVE_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    return text or DEFAULT_SENTIMENT_SPEC_BY_LABEL.get(label, "indifference")


def clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(-1.0, min(1.0, score))


def get_taxonomy() -> dict[str, Any]:
    global _TAXONOMY
    if _TAXONOMY is None:
        if not _TAXONOMY_PATH.exists():
            _TAXONOMY = {}
        else:
            with _TAXONOMY_PATH.open("r", encoding="utf-8") as stream:
                _TAXONOMY = json.load(stream)
    return _TAXONOMY


def taxonomy_prompt_summary() -> str:
    taxonomy = get_taxonomy().get("taxonomy", {})
    if not isinstance(taxonomy, dict) or not taxonomy:
        return ""
    part_count = symptom_count = 0
    labels: list[str] = []
    for category, data in taxonomy.items():
        if not isinstance(data, dict):
            continue
        labels.append(str(data.get("label") or CATEGORY_LABELS.get(category, category)))
        part_count += len(data.get("parts", []) if isinstance(data.get("parts"), list) else [])
        symptom_count += len(data.get("symptoms", []) if isinstance(data.get("symptoms"), list) else [])
    return (
        "\n\nEntity extraction guidance: prefer standard English snake_case names from the local NER taxonomy for parts and symptoms; "
        f"the taxonomy covers {len(labels)} business categories, {part_count} components, and {symptom_count} symptoms. "
        "Do not use an alias as the standardized name. Preserve the original only when no standardized name is available."
    )


def build_alias_map() -> dict[tuple[str, str], dict[str, str]]:
    global _ALIAS_MAP
    if _ALIAS_MAP is not None:
        return _ALIAS_MAP

    mapping: dict[tuple[str, str], dict[str, str]] = {}
    taxonomy = get_taxonomy().get("taxonomy", {})
    if not isinstance(taxonomy, dict):
        _ALIAS_MAP = mapping
        return mapping

    for category, data in taxonomy.items():
        if not isinstance(data, dict):
            continue
        label = str(data.get("label") or CATEGORY_LABELS.get(category, category))
        for kind, entity_type in (("parts", "part"), ("symptoms", "symptom")):
            raw_items = data.get(kind, [])
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                canonical = str(item.get("name") or "").strip()
                if not canonical:
                    continue
                info = {"name": canonical, "category": str(category), "label": label}
                names = [canonical] + [
                    str(alias).strip()
                    for alias in item.get("aliases", [])
                    if str(alias).strip()
                ]
                for alias in names:
                    mapping.setdefault((entity_type, alias.lower()), info)

    _ALIAS_MAP = mapping
    return mapping


def normalize_entity_with_taxonomy(entity_type: str, raw_name: str) -> dict[str, str] | None:
    if entity_type not in {"part", "symptom"}:
        return None
    return build_alias_map().get((entity_type, str(raw_name or "").strip().lower()))


def _taxonomy_alias_entries() -> list[tuple[str, str, str]]:
    global _ALIAS_ENTRIES
    if _ALIAS_ENTRIES is not None:
        return _ALIAS_ENTRIES

    entries: list[tuple[str, str, str]] = []
    taxonomy = get_taxonomy().get("taxonomy", {})
    if isinstance(taxonomy, dict):
        for data in taxonomy.values():
            if not isinstance(data, dict):
                continue
            for kind, entity_type in (("parts", "part"), ("symptoms", "symptom")):
                raw_items = data.get(kind, [])
                if not isinstance(raw_items, list):
                    continue
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    canonical = str(item.get("name") or "").strip()
                    if not canonical:
                        continue
                    aliases = [canonical] + [
                        str(alias).strip()
                        for alias in item.get("aliases", [])
                        if str(alias).strip()
                    ]
                    for alias in aliases:
                        alias_lower = alias.lower()
                        if len(alias_lower) >= 3:
                            entries.append((entity_type, canonical, alias_lower))

    _ALIAS_ENTRIES = sorted(set(entries), key=lambda item: len(item[2]), reverse=True)
    return _ALIAS_ENTRIES


def _alias_in_text(alias: str, lower_text: str) -> bool:
    if alias not in lower_text:
        return False
    if re.fullmatch(r"[a-z0-9 ]+", alias):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        return re.search(pattern, lower_text) is not None
    return True


def entity_key(entity_type: str, normalized_name: str) -> tuple[str, str]:
    return entity_type, re.sub(r"[\W_]+", "", normalized_name.lower())


def add_entity_once(
    entities: list[dict[str, Any]],
    entity_type: str,
    name: str,
    normalized_name: str,
    sentiment_score: Any,
) -> None:
    if not name:
        return
    key = entity_key(entity_type, normalized_name)
    for entity in entities:
        existing_key = entity_key(
            str(entity.get("type", "")),
            str(entity.get("normalized_name", "")),
        )
        if existing_key == key:
            return
    entities.append({
        "type": entity_type,
        "name": name,
        "normalized_name": normalized_name,
        "sentiment_score": clamp_score(sentiment_score),
    })


def enrich_entities_from_text(
    entities: list[dict[str, Any]], source_text: str, sentiment_score: Any
) -> None:
    lower_text = source_text.lower()
    compact_text = re.sub(r"[\s_\-]+", "", lower_text)
    for name, normalized_name, marker in (
        ("Model Y", "model_y", "modely"),
        ("Model 3", "model_3", "model3"),
        ("Model S", "model_s", "models"),
        ("Model X", "model_x", "modelx"),
    ):
        if marker in compact_text:
            add_entity_once(entities, "vehicle_model", name, normalized_name, sentiment_score)

    for name, normalized_name, keywords in (
        ("phantom braking", "ghost_brake", ("phantom braking", "unintended braking", "unexpected road hazard", "phantom brake", "phantom braking", "ghost brake")),
        ("hard braking", "sudden_brake", ("hard braking", "sudden braking", "sudden brake", "hard brake")),
    ):
        if any(keyword in lower_text for keyword in keywords):
            add_entity_once(entities, "symptom", name, normalized_name, -1.0)

    for entity_type, canonical, alias in _taxonomy_alias_entries():
        if _alias_in_text(alias, lower_text):
            add_entity_once(entities, entity_type, canonical, canonical, sentiment_score)
