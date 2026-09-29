# -*- coding: utf-8 -*-
"""Week7 项目准入与缺口驱动伙伴的固定演示案例。"""
from __future__ import annotations


CASE_VERSION = "admission-case/1.0"


def get_admission_demo_case() -> dict:
    """返回可独立演示的一页式案例；模拟信息与公开事实明确分层。"""
    matrix = [
        {"code": "QUAL-01", "category": "企业注册证明", "requirement": "德国工商注册（Handelsregister）",
         "evidence": "模拟企业已提供德国子公司注册文件", "status": "satisfied", "gap_level": "",
         "action": "投标前复核登记状态和授权签字人"},
        {"code": "QUAL-02", "category": "财务能力证明", "requirement": "近3年审计财报及母公司担保函",
         "evidence": "模拟企业声明可由母公司提供", "status": "partial", "gap_level": "P1",
         "action": "取得正式担保函并核对招标文件的财务门槛"},
        {"code": "QUAL-03", "category": "产品认证", "requirement": "VDE测试、CE及ISO 15118合规证据",
         "evidence": "仅有CE，缺少VDE测试和ISO 15118合规证据", "status": "missing", "gap_level": "P0",
         "action": "由VDE等机构评估测试范围、周期和可赶工节点"},
        {"code": "QUAL-04", "category": "计量认证", "requirement": "MID／德国Eichrecht计量合规",
         "evidence": "模拟企业未提供计量认证文件", "status": "missing", "gap_level": "P1",
         "action": "确认设备计费模式并完成计量法规适用性判断"},
        {"code": "QUAL-05", "category": "项目经验", "requirement": "至少2个同类公交充电项目案例",
         "evidence": "仅有2个工商业储能项目，无公共交通项目", "status": "missing", "gap_level": "P0",
         "action": "评估联合体或分包角色，借助具备公交案例的伙伴补位"},
        {"code": "QUAL-06", "category": "技术方案", "requirement": "插电式与受电弓式公交充电方案",
         "evidence": "具备直流充电能力，受电弓和调度集成证据不足", "status": "partial", "gap_level": "P2",
         "action": "补充受电弓、功率分配和车队调度接口方案"},
        {"code": "QUAL-07", "category": "投标文件", "requirement": "完整德语投标文件及声明",
         "evidence": "模拟企业尚未准备德语标书", "status": "missing", "gap_level": "P1",
         "action": "建立德语文件清单并安排本地法律及采购语言复核"},
        {"code": "QUAL-08", "category": "运维方案", "requirement": "德国本地运维、响应SLA和备件计划",
         "evidence": "法兰克福有18人团队，但无公交场景O&M方案", "status": "missing", "gap_level": "P1",
         "action": "核验本地运维伙伴的公交场景能力并形成书面SLA"},
    ]
    partners = [
        {
            "id": "vde", "name": "VDE Testing and Certification Institute", "partner_type": "认证与测试机构",
            "solves_gap_codes": ["QUAL-03", "QUAL-04"], "confidence": "high", "confidence_label": "高",
            "role": "完成充电设备测试、ISO 15118及计量合规路径确认",
            "evidence": "公开提供车辆、部件与充电基础设施测试认证服务。",
            "evidence_url": "https://www.vde.com/tic-en/industries/automotive-and-e-mobility",
            "risk": "具体标准、证书接受范围、测试周期和费用必须向机构询证。",
            "manual_verification": "无需中间引荐；需要技术团队直接询证并取得书面范围确认。",
        },
        {
            "id": "kempower", "name": "Kempower", "partner_type": "公交充电方案商",
            "solves_gap_codes": ["QUAL-05", "QUAL-06"], "confidence": "medium", "confidence_label": "中",
            "role": "以德国公交充电案例和受电弓方案补足项目经验与技术方案",
            "evidence": "公开展示德国Karlsruhe公交充电项目及受电弓产品方案。",
            "evidence_url": "https://kempower.com/news/modern-charging-infrastructure-for-electric-buses-in-karlsruhe-vbk-opts-for-kempower-solution/",
            "risk": "可能存在直接竞争关系，合作意愿、投标角色和案例授权均未确认。",
            "manual_verification": "需要人工接洽或引荐，确认是否接受联合体或系统合作。",
        },
        {
            "id": "wattif", "name": "Wattif EV", "partner_type": "充电运营与维护服务商",
            "solves_gap_codes": ["QUAL-08"], "confidence": "medium", "confidence_label": "中",
            "role": "补充德国本地充电运营、维护与客户支持能力",
            "evidence": "公开披露其在德国等欧洲市场提供充电基础设施管理与维护服务。",
            "evidence_url": "https://wattifev.com/",
            "risk": "公开案例以目的地充电为主，公交高功率充电与调度集成经验待核验。",
            "manual_verification": "需要人工核验公交场景案例、响应SLA及德国服务覆盖。",
        },
    ]
    return {
        "case_id": "BVG-EBUS-2026-DEMO",
        "case_version": CASE_VERSION,
        "data_as_of": "2026-08-14",
        "labels": ["商分提供案例", "模拟企业", "方法演示", "项目已截止"],
        "project": {
            "name": "BVG 106辆纯电动公交运营服务项目",
            "buyer": "Berliner Verkehrsbetriebe（BVG）",
            "country": "德国",
            "budget": "约 €721M",
            "deadline": "2026-06-15",
            "status": "closed",
            "status_label": "已截止",
            "scope": "约106辆纯电动公交及相关运营、充电能力，分为5个标段，合同计划覆盖2030—2045年。",
            "source_url": "https://ted.europa.eu/en/notice/164370-2026/pdf",
            "source_label": "TED 164370-2026",
            "official_context_url": "https://www.bvg.de/de/unternehmen/medienportal/pressemitteilungen/20260511-pm-subunternehmen-e-busse",
        },
        "enterprise": {
            "name": "EnPower新能源科技（欧洲）有限公司",
            "simulation_label": "完全模拟，不代表真实企业",
            "type": "中国储能／充电系统集成商的德国子公司",
            "location": "法兰克福", "founded": "2022年", "team_size": "18人",
            "capabilities": ["储能系统", "直流充电桩", "光储充一体化"],
            "certifications": ["CE", "ISO 9001", "ISO 14001"],
            "experience": "2个德国工商业储能项目，合计约5MWh；无公共交通政企项目经验",
            "target_role": "充电基础设施分包商或系统供应商",
        },
        "current_decision": {
            "decision": "no_go", "label": "No-Go 当前不可投",
            "reason": "截至案例数据日期，项目投标截止日已过；平台不应把历史项目展示为可继续投标。",
        },
        "method_decision": {
            "decision": "hold", "label": "Hold 补缺口后复核",
            "reason": "若在有效投标期内评估，仍有产品认证和同类项目经验两项P0缺口，不建议直接投入完整投标资源。",
            "hard_gate_codes": ["QUAL-03", "QUAL-05"],
        },
        "qualification_matrix": matrix,
        "partner_rules": [
            "候选必须对应至少一个未关闭缺口，不做泛行业推荐。",
            "每个候选必须有公开来源、可信度、风险和人工核验要求。",
            "公开能力不等于已确认资质、合作意愿或可被本项目接受。",
            "可能构成竞争关系的设备商必须显式标注，不自动建议引荐。",
        ],
        "partners": partners,
        "next_actions": [
            "停止把本项目作为在投机会投入资源，仅保留为德国公交市场方法样本。",
            "针对VDE／ISO 15118与MID／Eichrecht启动认证范围和周期预评估。",
            "向Kempower核验联合体或系统合作意愿，并取得公交案例授权边界。",
            "向Wattif核验公交高功率充电运维经验、德国覆盖和响应SLA。",
            "将已补齐的认证、案例与运维能力复用到下一条仍开放的德国项目。",
        ],
        "disclaimer": "本案例用于展示平台方法。企业档案为模拟数据；伙伴仅为公开信息候选；资格要求必须以采购文件原文及专业复核为准。",
    }
