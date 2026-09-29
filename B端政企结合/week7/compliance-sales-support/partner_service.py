# -*- coding: utf-8 -*-
"""基于项目准入缺口的可解释伙伴候选推荐。"""
from __future__ import annotations

from datetime import date


RULE_VERSION = "gap-partner/1.0"
EVIDENCE_CHECKED_AT = date(2026, 8, 14).isoformat()


# 演示目录只收录具有官方公开证据的机构。它用于候选发现，不代表合作关系已建立。
PARTNER_CATALOG = [
    {
        "id": "partner-vde-tic",
        "name": "VDE Testing and Certification Institute",
        "country": "德国",
        "region_scope": ["欧洲", "德国"],
        "partner_type": "认证与测试机构",
        "capability_categories": ["资格与准入", "合规与材料准备度", "技术与方案匹配"],
        "recommended_role": "认证测试、型式批准与准入证据补齐候选",
        "evidence": [{
            "title": "VDE 汽车与电动出行测试认证服务",
            "url": "https://www.vde.com/tic-en/industries/automotive-and-e-mobility",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "官方页面公开其车辆、部件、充电基础设施测试认证及技术服务能力。",
        }],
        "risk": "具体招标是否接受其证书、测试范围、周期与费用仍需逐条确认。",
        "introduction_required": False,
    },
    {
        "id": "partner-tuv-rheinland",
        "name": "TÜV Rheinland",
        "country": "德国",
        "region_scope": ["欧洲", "德国"],
        "partner_type": "认证与测试机构",
        "capability_categories": ["资格与准入", "合规与材料准备度", "技术与方案匹配"],
        "recommended_role": "充电设施合规测试与市场准入证据补齐候选",
        "evidence": [{
            "title": "TÜV Rheinland 充电站产品测试服务",
            "url": "https://www.tuv.com/world/en/charging-stations-product-testing.html",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "官方页面公开充电设施安全、标准符合性测试和市场准入服务。",
        }],
        "risk": "公开能力不等于自动满足本项目资格条款，必须先完成标准和报告类型映射。",
        "introduction_required": False,
    },
    {
        "id": "partner-kempower",
        "name": "Kempower",
        "country": "芬兰",
        "region_scope": ["欧洲", "芬兰"],
        "partner_type": "充电方案与系统集成商",
        "capability_categories": ["需求与产品匹配", "技术与方案匹配", "本地化与交付能力"],
        "recommended_role": "公交及重载充电方案、车队充电管理补位候选",
        "evidence": [{
            "title": "Kempower 充电解决方案",
            "url": "https://kempower.com/charging-solutions/",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "官方页面公开直流快充、公交场站、受电弓及车队充电管理方案。",
        }],
        "risk": "需核验目标国交付覆盖、类似项目业绩和合作意愿，也需排查潜在竞争关系。",
        "introduction_required": True,
    },
    {
        "id": "partner-bosch-aftermarket",
        "name": "Bosch Mobility Aftermarket",
        "country": "德国",
        "region_scope": ["欧洲", "德国", "英国", "丹麦", "意大利", "罗马尼亚", "克罗地亚"],
        "partner_type": "售后、诊断与备件网络",
        "capability_categories": ["技术与方案匹配", "本地化与交付能力"],
        "recommended_role": "本地售后、诊断设备与备件支持能力补位候选",
        "evidence": [{
            "title": "Bosch Mobility Aftermarket 欧洲业务页面",
            "url": "https://www.boschaftermarket.com/xc/en/",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "官方页面公开乘用车及商用车诊断、维修设备、备件和欧洲区域服务信息。",
        }],
        "risk": "公开服务网络不能替代项目专属授权，服务范围、响应承诺和合作意愿需商务核验。",
        "introduction_required": True,
    },
    {
        "id": "partner-wattif-ev",
        "name": "Wattif EV",
        "country": "挪威",
        "region_scope": ["欧洲", "德国", "英国"],
        "partner_type": "充电运营与维护服务商",
        "capability_categories": ["本地化与交付能力"],
        "recommended_role": "充电设施运营、维护和本地客户支持补位候选",
        "evidence": [{
            "title": "Wattif EV 充电解决方案",
            "url": "https://wattifev.com/",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "官方页面公开其在德国等欧洲市场提供充电设施建设、管理与维护服务。",
        }],
        "risk": "公开案例以目的地充电为主，公交高功率充电、调度集成和项目SLA需专项核验。",
        "introduction_required": True,
    },
]


def _gap_view(row: dict) -> dict:
    return {
        "code": row["code"],
        "category": row["category"],
        "severity": row["severity"],
        "status": row["status"],
        "requirement": row["requirement"],
        "assessment": row["assessment"],
        "action": row["action"],
    }


def recommend_partners(admission: dict, project: dict) -> dict:
    """按未关闭缺口匹配候选伙伴，并保留证据、风险和人工核验边界。"""
    unresolved = [
        _gap_view(row) for row in admission.get("requirement_gap_matrix", [])
        if row.get("status") != "satisfied"
    ]
    project_country = project.get("country", "")
    candidates = []

    for partner in PARTNER_CATALOG:
        solved = [gap for gap in unresolved if gap["category"] in partner["capability_categories"]]
        if not solved:
            continue
        exact_country = project_country in partner["region_scope"]
        urgent = sum(gap["severity"] == "P0" for gap in solved)
        score = min(96, 42 + min(len(solved), 3) * 11 + urgent * 4 + (15 if exact_country else 7))
        confidence = "high" if exact_country else "medium"
        confidence_label = "高" if exact_country else "中"
        solved_names = "、".join(dict.fromkeys(gap["category"] for gap in solved))
        candidates.append({
            "id": partner["id"],
            "name": partner["name"],
            "country": partner["country"],
            "region_scope": partner["region_scope"],
            "partner_type": partner["partner_type"],
            "capability_categories": partner["capability_categories"],
            "recommended_role": partner["recommended_role"],
            "solves_gaps": solved,
            "match_score": score,
            "confidence": confidence,
            "confidence_label": confidence_label,
            "recommendation_reason": f"公开能力可对应 {solved_names} 缺口；{'目标国存在明确公开覆盖' if exact_country else '具备欧洲区域能力，目标国覆盖仍需确认'}。",
            "evidence": partner["evidence"],
            "risk": partner["risk"],
            "verification_status": "public_evidence_only",
            "verification_status_label": "公开证据已核验·商务关系待确认",
            "manual_verification_required": True,
            "introduction_required": partner["introduction_required"],
            "data_label": "公开候选·待商务核验",
        })

    candidates.sort(key=lambda item: (-item["match_score"], item["name"]))
    covered_codes = {gap["code"] for candidate in candidates for gap in candidate["solves_gaps"]}
    uncovered = [gap for gap in unresolved if gap["code"] not in covered_codes]
    return {
        "rule_version": RULE_VERSION,
        "project_id": project.get("id"),
        "profile_id": admission.get("profile_id"),
        "admission_decision": admission.get("decision"),
        "admission_decision_label": admission.get("decision_label"),
        "gap_summary": unresolved,
        "uncovered_gaps": uncovered,
        "coverage": {
            "gap_count": len(unresolved),
            "covered_gap_count": len(covered_codes),
            "candidate_count": len(candidates),
        },
        "candidates": candidates,
        "disclaimer": "推荐仅用于候选发现，不代表伙伴已确认资质、合作意愿或可满足本项目条款；投标前必须人工核验并取得书面确认。",
    }
