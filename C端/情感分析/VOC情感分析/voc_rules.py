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
    "app_software": "App/软件体验",
    "ota_software": "OTA/软件升级",
    "battery_range": "续航电池",
    "charging": "充电体验",
    "air_conditioning": "空调/座舱",
    "customer_service": "客服服务",
    "repair_maintenance": "售后维修",
    "delivery_experience": "交付体验",
    "test_drive": "试驾体验",
    "price_competition": "价格竞争",
    "brand_reputation": "品牌口碑",
    "safety_recall": "安全/召回",
    "sales_experience": "销售体验",
    "vehicle_quality": "车辆质量",
    "infotainment": "车机娱乐",
    "other": "其他问题",
}

TOPIC_DEFINITIONS = {
    "app_login_issue": {"parent_category": "app_software", "name": "App 登录问题", "keywords": ("login", "sign in", "登录", "登陆", "无法登录")},
    "app_crash": {"parent_category": "app_software", "name": "App 崩溃/闪退", "keywords": ("app crash", "crash", "崩溃", "闪退")},
    "app_slow_response": {"parent_category": "app_software", "name": "App 响应慢", "keywords": ("slow app", "lag", "卡顿", "反应慢")},
    "app_remote_control": {"parent_category": "app_software", "name": "远程控制失败", "keywords": ("remote control", "远程控制", "远程开锁", "远程启动")},
    "app_notification_delay": {"parent_category": "app_software", "name": "消息通知延迟", "keywords": ("notification", "通知", "推送", "延迟")},
    "app_ui_usability": {"parent_category": "app_software", "name": "界面不好用", "keywords": ("ui", "interface", "界面", "不好用")},
    "ota_update_failure": {"parent_category": "ota_software", "name": "OTA 升级失败", "keywords": ("ota failed", "update failed", "升级失败", "更新失败")},
    "ota_slow_download": {"parent_category": "ota_software", "name": "升级下载慢", "keywords": ("download slow", "下载慢", "升级慢")},
    "ota_bug_after_update": {"parent_category": "ota_software", "name": "升级后出现新问题", "keywords": ("after update", "升级后", "更新后", "new bug")},
    "ota_feature_missing": {"parent_category": "ota_software", "name": "期待功能未更新", "keywords": ("feature missing", "功能没给", "没有更新")},
    "ota_version_rollout": {"parent_category": "ota_software", "name": "版本推送不一致", "keywords": ("version rollout", "版本", "推送", "分批推送")},
    "range_lower_than_claimed": {"parent_category": "battery_range", "name": "实际续航低于宣传", "keywords": ("lower than advertised", "续航虚标", "达不到", "range")},
    "winter_range_drop": {"parent_category": "battery_range", "name": "冬季续航下降", "keywords": ("winter range", "冬季续航", "低温", "掉电")},
    "battery_degradation": {"parent_category": "battery_range", "name": "电池衰减", "keywords": ("battery degradation", "电池衰减", "容量下降")},
    "range_display_inaccurate": {"parent_category": "battery_range", "name": "续航显示不准", "keywords": ("range display", "续航显示", "表显")},
    "high_energy_consumption": {"parent_category": "battery_range", "name": "能耗过高", "keywords": ("energy consumption", "能耗", "耗电")},
    "slow_charging": {"parent_category": "charging", "name": "充电速度慢", "keywords": ("slow charging", "充电慢", "充得慢")},
    "charging_failure": {"parent_category": "charging", "name": "无法充电", "keywords": ("charging failure", "无法充电", "充不上电", "charge failed")},
    "charger_compatibility": {"parent_category": "charging", "name": "充电桩兼容问题", "keywords": ("compatibility", "兼容", "充电桩")},
    "charging_app_issue": {"parent_category": "charging", "name": "充电扫码/App 问题", "keywords": ("charging app", "扫码", "充电app")},
    "charging_cost": {"parent_category": "charging", "name": "充电费用问题", "keywords": ("charging cost", "充电费", "费用")},
    "charging_network": {"parent_category": "charging", "name": "充电站覆盖不足", "keywords": ("charging network", "充电站", "桩少", "覆盖不足")},
    "ac_cooling_issue": {"parent_category": "air_conditioning", "name": "空调制冷问题", "keywords": ("cooling", "制冷", "不凉")},
    "ac_heating_issue": {"parent_category": "air_conditioning", "name": "空调制热问题", "keywords": ("heating", "制热", "不热")},
    "cabin_noise": {"parent_category": "air_conditioning", "name": "座舱噪音", "keywords": ("cabin noise", "风噪", "噪音")},
    "seat_comfort": {"parent_category": "air_conditioning", "name": "座椅舒适性", "keywords": ("seat", "座椅", "不舒服")},
    "odor_issue": {"parent_category": "air_conditioning", "name": "车内异味", "keywords": ("odor", "smell", "异味")},
    "cabin_space": {"parent_category": "air_conditioning", "name": "座舱空间问题", "keywords": ("space", "空间", "拥挤")},
    "service_no_response": {"parent_category": "customer_service", "name": "客服不回复", "keywords": ("never replied", "no response", "不回复", "没人理")},
    "service_slow_response": {"parent_category": "customer_service", "name": "客服响应慢", "keywords": ("slow response", "响应慢", "处理慢")},
    "service_attitude": {"parent_category": "customer_service", "name": "客服态度差", "keywords": ("attitude", "态度差", "态度")},
    "service_inconsistent": {"parent_category": "customer_service", "name": "客服说法不一致", "keywords": ("inconsistent", "说法不一", "前后不一")},
    "complaint_handling": {"parent_category": "customer_service", "name": "投诉处理问题", "keywords": ("complaint", "投诉", "处理")},
    "repair_delay": {"parent_category": "repair_maintenance", "name": "维修等待时间长", "keywords": ("repair delay", "维修慢", "等配件")},
    "repair_quality": {"parent_category": "repair_maintenance", "name": "维修后问题没解决", "keywords": ("fixed nothing", "没修好", "问题没解决")},
    "warranty_dispute": {"parent_category": "repair_maintenance", "name": "质保争议", "keywords": ("warranty", "质保", "保修")},
    "spare_parts_delay": {"parent_category": "repair_maintenance", "name": "配件等待时间长", "keywords": ("spare parts", "配件", "备件")},
    "maintenance_cost": {"parent_category": "repair_maintenance", "name": "维修/保养费用高", "keywords": ("maintenance cost", "维修费", "保养费", "费用高")},
    "service_booking_issue": {"parent_category": "repair_maintenance", "name": "售后预约困难", "keywords": ("booking", "预约", "约不上")},
    "delivery_delay": {"parent_category": "delivery_experience", "name": "交付延期", "keywords": ("delivery delay", "延期交付", "等车", "delayed")},
    "delivery_process": {"parent_category": "delivery_experience", "name": "交付流程混乱", "keywords": ("delivery process", "交付流程", "流程混乱")},
    "vehicle_condition": {"parent_category": "delivery_experience", "name": "交付车辆状态问题", "keywords": ("vehicle condition", "交车状态", "划痕", "瑕疵")},
    "document_issue": {"parent_category": "delivery_experience", "name": "交付资料/手续问题", "keywords": ("document", "资料", "手续", "发票")},
    "pickup_experience": {"parent_category": "delivery_experience", "name": "提车体验问题", "keywords": ("pickup", "提车", "验车")},
    "test_drive_booking": {"parent_category": "test_drive", "name": "试驾预约问题", "keywords": ("test drive booking", "试驾预约")},
    "test_drive_availability": {"parent_category": "test_drive", "name": "试驾车不足", "keywords": ("test drive availability", "试驾车", "没车")},
    "test_drive_route": {"parent_category": "test_drive", "name": "试驾路线不合理", "keywords": ("test route", "试驾路线")},
    "sales_during_test_drive": {"parent_category": "test_drive", "name": "试驾销售讲解问题", "keywords": ("sales explanation", "讲解", "销售介绍")},
    "test_drive_vehicle_issue": {"parent_category": "test_drive", "name": "试驾车状态有问题", "keywords": ("test vehicle", "试驾车故障")},
    "price_too_high": {"parent_category": "price_competition", "name": "价格过高", "keywords": ("too expensive", "太贵", "价格高")},
    "price_cut_complaint": {"parent_category": "price_competition", "name": "降价引发不满", "keywords": ("price cut", "降价", "背刺")},
    "promotion_confusion": {"parent_category": "price_competition", "name": "优惠政策不清楚", "keywords": ("promotion", "优惠", "政策不清")},
    "resale_value": {"parent_category": "price_competition", "name": "保值率问题", "keywords": ("resale", "保值", "二手")},
    "competitor_price": {"parent_category": "price_competition", "name": "与竞品价格对比", "keywords": ("competitor price", "竞品", "对比")},
    "brand_trust": {"parent_category": "brand_reputation", "name": "品牌信任", "keywords": ("brand trust", "信任", "靠谱")},
    "brand_image": {"parent_category": "brand_reputation", "name": "品牌形象", "keywords": ("brand image", "品牌形象")},
    "public_opinion": {"parent_category": "brand_reputation", "name": "舆论讨论", "keywords": ("public opinion", "舆论", "口碑")},
    "word_of_mouth": {"parent_category": "brand_reputation", "name": "口碑传播", "keywords": ("word of mouth", "口碑", "推荐")},
    "brand_expectation": {"parent_category": "brand_reputation", "name": "对品牌期待", "keywords": ("expectation", "期待", "希望")},
    "brake_noise": {"parent_category": "safety_recall", "name": "制动异响", "keywords": ("brake noise", "brake", "刹车异响", "制动异响", "刹车响", "异响")},
    "brake_failure": {"parent_category": "safety_recall", "name": "制动失效", "keywords": ("brake failure", "刹不住", "制动失效")},
    "airbag_issue": {"parent_category": "safety_recall", "name": "安全气囊问题", "keywords": ("airbag", "安全气囊")},
    "recall_notice": {"parent_category": "safety_recall", "name": "召回通知问题", "keywords": ("recall notice", "召回通知", "召回")},
    "safety_warning": {"parent_category": "safety_recall", "name": "安全警告", "keywords": ("safety warning", "安全警告", "幽灵刹车", "鬼探头", "急刹", "误刹", "辅助驾驶")},
    "battery_safety": {"parent_category": "safety_recall", "name": "电池安全隐患", "keywords": ("battery safety", "电池安全", "自燃", "起火")},
    "sales_attitude": {"parent_category": "sales_experience", "name": "销售态度", "keywords": ("sales attitude", "销售态度")},
    "sales_misleading": {"parent_category": "sales_experience", "name": "销售误导", "keywords": ("misleading", "误导", "虚假宣传")},
    "contract_issue": {"parent_category": "sales_experience", "name": "合同问题", "keywords": ("contract", "合同")},
    "order_process": {"parent_category": "sales_experience", "name": "下订流程问题", "keywords": ("order process", "下订", "订单")},
    "sales_follow_up": {"parent_category": "sales_experience", "name": "销售跟进问题", "keywords": ("follow up", "跟进", "销售不回")},
    "body_quality": {"parent_category": "vehicle_quality", "name": "车身质量问题", "keywords": ("body quality", "车身", "钣金")},
    "paint_defect": {"parent_category": "vehicle_quality", "name": "车漆问题", "keywords": ("paint", "车漆", "掉漆")},
    "abnormal_noise": {"parent_category": "vehicle_quality", "name": "异响问题", "keywords": ("abnormal noise", "异响", "噪音")},
    "water_leak": {"parent_category": "vehicle_quality", "name": "漏水问题", "keywords": ("water leak", "漏水")},
    "door_window_issue": {"parent_category": "vehicle_quality", "name": "车门/车窗问题", "keywords": ("door", "window", "车门", "车窗")},
    "component_failure": {"parent_category": "vehicle_quality", "name": "零部件故障", "keywords": ("component failure", "故障", "坏了")},
    "screen_lag": {"parent_category": "infotainment", "name": "车机卡顿", "keywords": ("screen lag", "车机卡顿", "屏幕卡")},
    "navigation_issue": {"parent_category": "infotainment", "name": "导航问题", "keywords": ("navigation", "导航")},
    "voice_assistant_issue": {"parent_category": "infotainment", "name": "语音助手问题", "keywords": ("voice assistant", "语音助手", "语音")},
    "bluetooth_issue": {"parent_category": "infotainment", "name": "蓝牙连接问题", "keywords": ("bluetooth", "蓝牙")},
    "media_playback_issue": {"parent_category": "infotainment", "name": "音乐/媒体播放问题", "keywords": ("media playback", "音乐", "媒体")},
    "carplay_androidauto": {"parent_category": "infotainment", "name": "CarPlay/Android Auto 问题", "keywords": ("carplay", "android auto")},
    "unclear_feedback": {"parent_category": "other", "name": "表达不清", "keywords": ("unclear", "表达不清")},
    "general_complaint": {"parent_category": "other", "name": "泛化抱怨", "keywords": ("complaint", "抱怨", "吐槽")},
    "general_praise": {"parent_category": "other", "name": "泛化表扬", "keywords": ("praise", "表扬", "满意")},
    "non_vehicle_topic": {"parent_category": "other", "name": "非车辆相关", "keywords": ("unrelated", "无关")},
    "other_unclassified": {"parent_category": "other", "name": "其他未分类", "keywords": ("other", "其他")},
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

POSITIVE_EMOTIONS = {"喜悦", "高兴", "满足", "兴奋", "感动", "爱慕", "信任", "期待", "好奇"}
NEUTRAL_EMOTIONS = {"平静", "无感", "惊讶"}
MILD_NEGATIVE_EMOTIONS = {
    "焦虑", "担忧", "紧张", "恐惧", "悲伤", "失望", "沮丧", "愤怒",
    "厌恶", "抱怨", "羞愧", "内疚", "嫉妒", "羡慕", "鄙视", "困惑",
}
HIGH_RISK_NEGATIVE_EMOTIONS = set()
NEGATIVE_EMOTIONS = MILD_NEGATIVE_EMOTIONS | HIGH_RISK_NEGATIVE_EMOTIONS
SENTIMENT_LABELS = {"正面情感", "中性情感", "负面情感", "混合"}
DEFAULT_SENTIMENT_SPEC_BY_LABEL = {
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

TOPIC_KEYWORDS = {
    "safety_recall": ("safety", "recall", "brake", "airbag", "dangerous", "安全", "召回", "刹车", "制动", "气囊", "危险", "幽灵刹车", "鬼探头", "急刹", "误刹", "辅助驾驶"),
    "charging": ("charging", "charger", "charge", "充电", "充电桩", "补能"),
    "battery_range": ("range", "battery", "mileage", "winter range", "kwh", "state of charge", "续航", "电池", "里程", "掉电", "能耗"),
    "air_conditioning": ("air conditioning", "climate", "temperature", "preheat", "pre-cool", "a/c", " ac ", "空调", "座舱", "制冷", "制热", "异味"),
    "app_software": ("app", "application", "login", "notification", "dark mode", "phone app", "登录", "通知", "推送", "远程控制"),
    "ota_software": ("ota", "software update", "firmware", "update failed", "upgrade", "软件", "升级", "更新", "版本"),
    "customer_service": ("customer service", "support", "warranty", "dealer never replied", "客服", "售后", "不回复", "投诉处理"),
    "repair_maintenance": ("repair", "maintenance", "service interval", "workshop", "fixed nothing", "维修", "保养", "质保", "没修好", "配件"),
    "delivery_experience": ("delivery", "delayed", "arrived", "handover", "pickup", "交付", "提车", "等车", "延期"),
    "test_drive": ("test drive", "demo drive", "试驾"),
    "price_competition": ("price", "expensive", "cheap", "competitor", "residual", "价格", "太贵", "降价", "优惠", "保值"),
    "brand_reputation": ("trust", "brand", "reputation", "reliability survey", "品牌", "口碑", "信任", "推荐"),
    "sales_experience": ("sales", "dealer", "salesperson", "quote", "销售", "合同", "下订", "订单"),
    "vehicle_quality": ("broken", "quality", "dead", "crash", "reliability", "fault", "质量", "故障", "坏了", "漏水", "车漆", "车门", "车窗"),
    "infotainment": ("infotainment", "screen", "display", "carplay", "android auto", "cockpit", "车机", "屏幕", "导航", "蓝牙", "语音助手"),
}


def normalized_for_match(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace("，", "")
        .replace("。", "")
        .replace("、", "")
        .replace("；", "")
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
    if label in {"positive", "正面情感"}:
        return 1.0
    if label in {"negative", "负面情感", "轻度负面情感", "高危负面情感"}:
        return -1.0
    return 0.0


def standard_sentiment_strength(label: str, topic: str = "other") -> int:
    if label in {"neutral", "unknown", "中性情感"}:
        return 1
    if topic == "safety_recall":
        return 4
    return 3 if label in {"positive", "正面情感", "negative", "负面情感", "轻度负面情感", "mixed", "混合"} else 4


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
    positive = next((spec for spec in specs if spec in POSITIVE_EMOTIONS), "满足")
    negative = next((spec for spec in specs if spec in NEGATIVE_EMOTIONS), "抱怨")
    return [positive, negative]


def standard_sentiment_spec(label: str, raw_spec: Any = "") -> str | list[str]:
    text = str(raw_spec or "").strip()
    if label in {"mixed", "混合"}:
        return standard_mixed_sentiment_specs(raw_spec)
    if label in {"negative", "负面情感", "轻度负面情感", "高危负面情感"} and text in POSITIVE_EMOTIONS | NEUTRAL_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    if label in {"positive", "正面情感"} and text not in POSITIVE_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    if label in {"neutral", "中性情感"} and text not in NEUTRAL_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    if label in {"负面情感", "轻度负面情感", "高危负面情感"} and text not in NEGATIVE_EMOTIONS:
        return DEFAULT_SENTIMENT_SPEC_BY_LABEL[label]
    return text or DEFAULT_SENTIMENT_SPEC_BY_LABEL.get(label, "无感")


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
        "\n\n实体抽取补充：part/symptom 优先使用本地 NER 词库的标准英文 snake_case 名称；"
        f"词库覆盖 {len(labels)} 个业务类、{part_count} 个部件、{symptom_count} 个症状。"
        "不要输出 alias 原词作为标准名；找不到标准名时再保留原文。"
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
        ("幽灵刹车", "ghost_brake", ("幽灵刹车", "误刹", "鬼探头", "phantom brake", "phantom braking", "ghost brake")),
        ("急刹", "sudden_brake", ("急刹", "突然刹车", "sudden brake", "hard brake")),
    ):
        if any(keyword in lower_text for keyword in keywords):
            add_entity_once(entities, "symptom", name, normalized_name, -1.0)

    for entity_type, canonical, alias in _taxonomy_alias_entries():
        if _alias_in_text(alias, lower_text):
            add_entity_once(entities, entity_type, canonical, canonical, sentiment_score)
