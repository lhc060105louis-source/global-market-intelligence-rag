# -*- coding: utf-8 -*-
"""面向中国新能源企业的产品定位、用户画像与关键场景。"""
from __future__ import annotations


POSITIONING_VERSION = "product-positioning/1.0"


def get_product_positioning() -> dict:
    return {
        "version": POSITIONING_VERSION,
        "statement": "面向中国新能源企业的欧洲项目决策与落地平台",
        "value_proposition": "不止发现项目，更判断能不能投、缺什么材料和本地能力，以及下一步找谁补、怎么推进。",
        "personas": [
            {
                "id": "strategy", "role": "欧洲业务／战略负责人", "short_role": "业务与战略",
                "goal": "决定进入哪个市场、哪些项目值得投入",
                "pain": "信息分散，难以判断市场优先级和需要预先建设的本地能力",
                "current_method": "人工查找公告、依赖代理和个人经验",
                "outcome": "市场机会、企业适配度和本地能力缺口形成同一决策视图",
                "route": {"page": "information", "tab": "feed"}, "cta": "查看市场与法规",
            },
            {
                "id": "bid", "role": "投标／项目负责人", "short_role": "投标与项目",
                "goal": "判断具体项目是否值得投并组织推进",
                "pain": "资格、竞争和资源投入判断依赖Excel与个人经验",
                "current_method": "手工评分后凭经验作Go／No-Go决定",
                "outcome": "七维评分、硬门槛和Go／Hold／No-Go形成可解释结论",
                "route": {"page": "ecosystem", "tab": "profile"}, "cta": "生成准入诊断",
            },
            {
                "id": "compliance", "role": "合规／材料负责人", "short_role": "合规与材料",
                "goal": "备齐投标所需认证、声明和证据",
                "pain": "法规原文复杂，材料容易遗漏且责任和周期不清楚",
                "current_method": "逐条查法规并反复咨询第三方",
                "outcome": "P0—P3缺口、材料状态、责任角色和整改任务可追踪",
                "route": {"page": "information", "tab": "regulations"}, "cta": "检查材料缺口",
            },
        ],
        "scenarios": [
            {
                "id": "can_bid", "question": "这个项目能不能投？", "icon": "01",
                "generic_limit": "通用平台通常只提供相关性或泛化的bid/no-bid建议。",
                "solution": "结合企业档案检查七维适配度和P0硬门槛，输出Go／Hold／No-Go。",
                "next_step": "生成企业级准入诊断", "route": {"page": "ecosystem", "tab": "profile"},
                "paid_reason": "专业版解锁完整判断依据和缺口矩阵",
            },
            {
                "id": "missing_materials", "question": "具体缺什么材料？", "icon": "02",
                "generic_limit": "公告检索无法自动转换成中国新能源企业的材料责任清单。",
                "solution": "将法规和项目要求转成P0—P3材料缺口，并生成可跟踪任务。",
                "next_step": "查看法规与材料", "route": {"page": "information", "tab": "regulations"},
                "paid_reason": "专业版提供完整缺口、责任和导出能力",
            },
            {
                "id": "local_capability", "question": "缺哪类本地能力，怎么补？", "icon": "03",
                "generic_limit": "通用项目库通常不理解本地售后、备件、认证和运维能力缺口。",
                "solution": "先识别本地化缺口，再推荐有公开证据、风险和核验要求的候选伙伴。",
                "next_step": "诊断并生成补位伙伴", "route": {"page": "ecosystem", "tab": "profile"},
                "paid_reason": "企业版和专项服务覆盖伙伴核验与人工落地",
            },
        ],
        "differentiators": [
            {"title": "从找项目到能不能投", "description": "七维评分、硬门槛和Go／Hold／No-Go。"},
            {"title": "合规缺口可视化", "description": "将欧洲要求转成P0—P3材料和行动清单。"},
            {"title": "本地缺口与伙伴补位", "description": "候选伙伴关联具体缺口、证据、风险和核验边界。"},
            {"title": "中国新能源出海语境", "description": "覆盖车辆、充电、储能、认证和欧洲本地化能力。"},
            {"title": "平台自动＋分析师人工", "description": "日常自查自动化，重点项目通过专项服务人工闭环。"},
        ],
        "comparison": [
            {"pain": "找到项目但不知道是否够资格", "generic_limit": "只做相关性判断",
             "solution": "企业级准入诊断", "paid_reason": "为可解释的投入决策付费"},
            {"pain": "不清楚欧洲材料要求", "generic_limit": "不映射企业证据",
             "solution": "P0—P3缺口矩阵", "paid_reason": "为减少漏项和返工付费"},
            {"pain": "缺少当地交付能力", "generic_limit": "无本地能力模型",
             "solution": "本地化缺口诊断", "paid_reason": "为企业个性化判断付费"},
            {"pain": "不知道找谁补位", "generic_limit": "不关联缺口推荐伙伴",
             "solution": "证据化伙伴候选", "paid_reason": "为核验效率和落地路径付费"},
            {"pain": "分析与执行之间断层", "generic_limit": "仅提供自动结果",
             "solution": "14天分析师冲刺", "paid_reason": "为锁定人工资源和强SLA付费"},
        ],
    }
