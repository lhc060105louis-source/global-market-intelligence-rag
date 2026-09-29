# -*- coding: utf-8 -*-
"""Week7 商业套餐、专项服务边界与14天冲刺说明。"""
from __future__ import annotations


CATALOG_VERSION = "commercial-offers/1.0"
PRICING_NOTE = "所有付费价格均为待验证报价假设，不构成正式报价或要约。"


OFFERS = [
    {
        "id": "free", "name": "免费版", "product_type": "subscription",
        "price_eur": 0, "price_label": "免费", "price_unit": "试用／自查",
        "quote_status": "free", "positioning": "用公开信息完成欧洲项目初步调研。",
        "audience": "初步调研、试水欧洲市场的新人或初级投标人员",
        "included": ["公开项目基础信息", "基础准入规则AI初筛", "通用材料缺口清单", "基础自动化工具"],
        "excluded": ["无人工分析师", "无本地化缺口诊断", "无伙伴推荐和引荐", "无正式诊断报告", "无加急服务"],
        "cta": "开始免费体验", "demo_mode": "visitor", "upgrade_to": "professional",
        "upgrade_path": "免费版 → 专业版：解锁精细准入判断和完整机器自查报告",
    },
    {
        "id": "professional", "name": "专业版", "product_type": "subscription",
        "price_eur": 499, "price_label": "€499", "price_unit": "每组织／月",
        "quote_status": "hypothesis", "positioning": "高频项目初筛和单项目深度自查。",
        "audience": "投标专员、项目负责人",
        "included": ["免费版全部能力", "Go/Hold/No-Go精细判断", "分维度材料缺口扫描", "机器生成单项目自查报告", "月度准入趋势与禁投风险"],
        "excluded": ["无分析师定制梳理", "无伙伴人工引荐", "不负责真实缺口落地", "不支持加急投标冲刺"],
        "cta": "切换专业版演示", "demo_mode": "professional", "upgrade_to": "enterprise",
        "upgrade_path": "专业版 → 企业版：增加团队协作、企业档案和本地化能力诊断",
    },
    {
        "id": "enterprise", "name": "企业版", "product_type": "subscription",
        "price_eur": 1499, "price_label": "€1,499", "price_unit": "每组织／月",
        "quote_status": "hypothesis", "positioning": "部门级团队的长期项目与合规风控。",
        "audience": "欧洲业务负责人、合规负责人、部门级出海团队",
        "included": ["专业版全部能力", "企业档案与资质库长期管理", "多成员权限与协作看板", "高精度本地化缺口判断", "批量准入筛查与合规预警"],
        "excluded": ["无人工深度定制", "无伙伴合作结果承诺", "不保证材料补齐", "无14天紧急闭环交付"],
        "cta": "切换企业版演示", "demo_mode": "enterprise", "upgrade_to": "standard_service",
        "upgrade_path": "企业版 → 标准专项／14天冲刺：由分析师推动单项目落地",
    },
    {
        "id": "standard_service", "name": "标准专项服务", "product_type": "service",
        "price_eur": 7500, "price_label": "€7,500起", "price_unit": "单项目",
        "quote_status": "hypothesis", "positioning": "非紧急重点项目的常规缺口补位服务。",
        "audience": "中长期布局、尚未临近截标的重点项目",
        "included": ["分析师复核准入判定", "P0—P3完整缺口梳理", "本地化能力诊断", "标准伙伴候选清单", "正式内部汇报报告", "整改和行动清单"],
        "excluded": ["无14天加急闭环", "不优先锁定分析师排期", "不做逐日进度管控", "不适用于临近截标救急"],
        "cta": "查看服务边界", "demo_mode": "", "upgrade_to": "sprint_14d",
        "upgrade_path": "标准专项 → 14天冲刺：适用于截标临近、需要锁定资源的项目",
    },
    {
        "id": "sprint_14d", "name": "14天冲刺专项", "product_type": "service",
        "price_eur": 12000, "price_label": "€12,000起", "price_unit": "单项目／14天",
        "quote_status": "hypothesis", "positioning": "临近截标项目的最高优先级加急服务。",
        "audience": "截标近、项目价值高、缺口大且内部难以独立落地的核心项目",
        "included": ["锁定专属分析师14天", "逐日进度与固定SLA", "P0优先级重排", "紧急材料补全指导", "伙伴筛选和风险核验", "最终准入结论与落地清单"],
        "excluded": ["不承诺100%中标", "不承诺伙伴一定接洽成功", "不承诺客户材料一定补齐", "不承担客户内部延误"],
        "cta": "申请14天冲刺", "demo_mode": "", "upgrade_to": "",
        "upgrade_path": "提交申请 → 范围确认 → 锁定排期 → Day 1—14交付",
    },
]


SPRINT = {
    "application_materials": [
        "企业现有资质与欧盟过往投标记录", "目标项目公告全文及附件",
        "现有欧洲团队和本地合作资源说明", "截标时间、内部负责人和可投入资源",
    ],
    "scope": [
        "只锁定一个目标项目", "范围包含准入判断、缺口分级、补位路径和伙伴推荐",
        "启动前书面确认服务边界，新增项目或需求需走变更",
    ],
    "timeline": [
        {"days": "Day 1", "title": "规则拆解", "output": "项目全量规则拆解与初步Go/No-Go"},
        {"days": "Day 2—3", "title": "缺口清单", "output": "P0／P1／P2／P3完整缺口表"},
        {"days": "Day 4—6", "title": "本地化诊断", "output": "本地能力短板与等级"},
        {"days": "Day 7—9", "title": "伙伴筛选", "output": "候选、证据、置信度和风险"},
        {"days": "Day 10—12", "title": "补位方案", "output": "整改优先级与落地步骤"},
        {"days": "Day 13", "title": "人工终审", "output": "风险汇总与最终准入结论"},
        {"days": "Day 14", "title": "打包交付", "output": "交付复盘与下一步行动"},
    ],
    "deliverables": [
        "项目准入最终判定报告", "P0—P3四级缺口总表", "材料缺失整改清单",
        "本地化能力补位方案", "伙伴候选表（风险、证据和缺口关系）", "14天落地执行台账",
    ],
    "sla": ["范围与资料齐备后确认Day 1", "14个自然日逐阶段交付", "客户需在24小时内反馈关键资料和决策"],
    "client_cooperation": ["24小时内响应必要资料", "及时确认范围且不临时扩项", "内部阻塞和决策变化及时同步"],
    "change_rules": [
        "客户迟交资料：交付时间顺延，不构成退款理由",
        "增加项目或范围：重新确认报价、差价和排期",
        "平台方延期：提供额外一次答疑复盘或约定的SLA补偿",
    ],
    "why_premium": ["锁定稀缺分析师排期", "14天逐日强SLA", "临近截标容错率低", "直接影响高价值项目投入决策"],
    "not_promised": ["不承诺中标", "不承诺伙伴接洽成功", "不承诺客户整改全部完成", "不承担材料造假、违规或客户延误风险"],
}


AUTOMATION_VS_ANALYST = {
    "platform": ["项目抓取、规则匹配和初筛评分", "自动材料缺口清单", "资质与本地化基础对照", "报表、台账、权限和流程自动化"],
    "analyst": ["校验机器误判和本地隐性门槛", "人工定级致命与可放弃缺口", "复核伙伴可信度与合作风险", "干预逐日排期并定制落地策略", "输出可供内部审批的正式结论"],
}


FAQ = [
    {"question": "免费版和付费版最大区别？", "answer": "免费版用于公开信息试用；订阅版提供完整资格判断和缺口路径；专项服务加入分析师人工闭环。"},
    {"question": "企业版能替代专项服务吗？", "answer": "不能。企业版是持续自查和团队协作工具，专项服务是围绕单个项目的人工交付。"},
    {"question": "14天冲刺为什么更贵？", "answer": "价格差异来自锁定分析师排期、逐日SLA、紧急风险判断和高强度交付，并非简单增加几个页面。"},
    {"question": "购买后是否一定能投或中标？", "answer": "不承诺。服务提供经复核的判断和行动路径，结果仍取决于采购规则、客户材料与执行以及外部伙伴。"},
    {"question": "专项服务可以叠加订阅吗？", "answer": "可以。订阅负责日常监控和自查，专项服务负责重点项目的人工落地。"},
]


def get_commercial_catalog() -> dict:
    return {
        "version": CATALOG_VERSION,
        "currency": "EUR",
        "pricing_note": PRICING_NOTE,
        "offers": OFFERS,
        "sprint": SPRINT,
        "automation_vs_analyst": AUTOMATION_VS_ANALYST,
        "faq": FAQ,
        "upgrade_path": ["free", "professional", "enterprise", "standard_service", "sprint_14d"],
    }
