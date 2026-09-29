# -*- coding: utf-8 -*-
"""可解释的企业档案 → 项目七维匹配引擎。"""
from __future__ import annotations

MATCH_DIMS = [
    ("资格与准入", 15), ("需求与产品匹配", 20), ("技术与方案匹配", 15),
    ("合规与材料准备度", 15), ("本地化与交付能力", 15),
    ("商业吸引力", 10), ("时间与执行可行性", 10),
]
RULE_VERSION = "enterprise-match/1.2"

COUNTRY_ALIASES = {
    "德国": "DE", "法国": "FR", "英国": "UK", "意大利": "IT", "西班牙": "ES",
    "丹麦": "DK", "克罗地亚": "HR", "北马其顿": "MK", "荷兰": "NL",
}


def _dim(name, result, detail, score, maximum, evidence):
    return {"name": name, "result": result, "detail": detail, "score": score,
            "max": maximum, "evidence": evidence}


def _vehicle_result(vehicles: list[str], project_type: str):
    if not vehicles:
        return "unconfirmed", "车型信息未填写"
    if any(scene in project_type for scene in ("公交", "公共交通", "机场交通")):
        return ("matched", "电动客车车型与公交场景匹配") if any("客" in v or "公交" in v for v in vehicles) else ("gap", "缺少公交适配车型")
    if "充电" in project_type:
        return "partial", "车型不构成门槛，仍需核实充电系统集成能力"
    return "matched", "已配置可参与该场景的产品能力"


REQUIREMENT_DEFINITIONS = {
    "资格与准入": {
        "requirement": "项目指定准入认证与投标资格",
        "required_evidence": "强制认证、投标主体资格及有效期证明（以招标原文为准）",
        "action": "逐条核对招标资格条款，补充缺失认证或确认可接受的联合体路径",
    },
    "需求与产品匹配": {
        "requirement": "与采购场景匹配的产品或车型能力",
        "required_evidence": "产品目录、车型参数、同类场景适配说明",
        "action": "确认目标产品覆盖范围；不匹配时调整投标角色或停止投入",
    },
    "技术与方案匹配": {
        "requirement": "充电、软件与系统集成技术方案",
        "required_evidence": "技术方案、接口说明、测试记录及集成案例",
        "action": "补齐技术方案证据并安排技术负责人复核项目接口要求",
    },
    "合规与材料准备度": {
        "requirement": "可提交且在有效期内的合规材料",
        "required_evidence": "项目适用法规对应的证书、报告和声明文件",
        "action": "按项目法规清单盘点材料，明确责任部门和预计完成时间",
    },
    "本地化与交付能力": {
        "requirement": "目标国售后、备件、运维与交付网络",
        "required_evidence": "本地实体、团队、服务网点、仓储或合作伙伴证明",
        "action": "确定缺失的本地能力类型，并启动伙伴核验或服务网络建设",
    },
    "商业吸引力": {
        "requirement": "项目规模与企业商业边界匹配",
        "required_evidence": "可接受合同规模、预算边界和内部审批口径",
        "action": "补充商业边界并完成投入产出初判",
    },
    "时间与执行可行性": {
        "requirement": "投标截止、认证周期与交付周期可行",
        "required_evidence": "招标时间表、内部准备周期和交付计划",
        "action": "由项目负责人确认关键日期，并对无法压缩的周期设置升级条件",
    },
}


def _gap_severity(dimension: str, status: str) -> str:
    if status == "satisfied":
        return ""
    rules = {
        "资格与准入": {"missing": "P0", "unverified": "P0", "partial": "P1"},
        "需求与产品匹配": {"missing": "P0", "unverified": "P1", "partial": "P1"},
        "技术与方案匹配": {"missing": "P0", "unverified": "P1", "partial": "P1"},
        "合规与材料准备度": {"missing": "P0", "unverified": "P1", "partial": "P1"},
        "本地化与交付能力": {"missing": "P1", "unverified": "P1", "partial": "P2"},
        "商业吸引力": {"missing": "P2", "unverified": "P2", "partial": "P2"},
        "时间与执行可行性": {"missing": "P1", "unverified": "P1", "partial": "P2"},
    }
    return rules.get(dimension, {}).get(status, "P2")


def _requirement_gap_matrix(dimensions: list[dict], project: dict) -> list[dict]:
    """把七维判断转换为可审计的要求—证据—状态—缺口矩阵。"""
    status_map = {
        "matched": "satisfied", "partial": "partial",
        "gap": "missing", "unconfirmed": "unverified",
    }
    rows = []
    for index, dimension in enumerate(dimensions, 1):
        definition = REQUIREMENT_DEFINITIONS[dimension["name"]]
        status = status_map[dimension["result"]]
        severity = _gap_severity(dimension["name"], status)
        rows.append({
            "code": f"REQ-{index:02d}",
            "category": dimension["name"],
            "requirement": definition["requirement"],
            "required_evidence": definition["required_evidence"],
            "enterprise_evidence": dimension.get("evidence") or [],
            "status": status,
            "severity": severity,
            "assessment": dimension["detail"],
            "source_type": "项目公告 + 企业档案",
            "source_url": project.get("source_url") or "",
            "action": "无需补充，投标前复核证据有效期" if status == "satisfied" else definition["action"],
            "requires_human_review": status != "satisfied" or dimension["name"] in {"资格与准入", "时间与执行可行性"},
        })
    return rows


def _admission_decision(total_score: int, confidence_level: str,
                        matrix: list[dict]) -> tuple[str, str, list[str], list[dict]]:
    """评分用于排序，准入结论由硬门槛、证据完整度和评分共同决定。"""
    hard_gates = []
    for row in matrix:
        if row["severity"] != "P0" or row["status"] not in {"missing", "unverified"}:
            continue
        impact = "no_go" if row["category"] == "需求与产品匹配" and row["status"] == "missing" else "hold"
        hard_gates.append({
            "code": row["code"], "requirement": row["requirement"],
            "status": row["status"], "severity": row["severity"],
            "impact": impact, "reason": row["assessment"], "action": row["action"],
        })

    reasons = []
    if any(gate["impact"] == "no_go" for gate in hard_gates):
        decision = "no_go"
        reasons.append("核心产品与采购场景不匹配，当前投标角色不可行")
    elif total_score < 45 and any(row["status"] == "missing" for row in matrix):
        decision = "no_go"
        reasons.append("综合适配度过低且存在实质能力缺口")
    elif hard_gates or total_score < 70 or confidence_level == "低":
        decision = "hold"
        if hard_gates:
            reasons.append(f"存在 {len(hard_gates)} 项 P0 资格或证据门槛未关闭")
        if total_score < 70:
            reasons.append(f"综合适配度 {total_score}/100，尚未达到建议投入线")
        if confidence_level == "低":
            reasons.append("企业档案或项目信息不足，结论可信度偏低")
    else:
        decision = "go"
        reasons.append("未发现未关闭的 P0 门槛，综合适配度达到建议投入线")

    labels = {"go": "Go 建议推进", "hold": "Hold 补缺口后复核", "no_go": "No-Go 暂不投入"}
    return decision, labels[decision], reasons, hard_gates


def match_project(profile: dict, project: dict, regulations: list | None = None) -> dict:
    """输出七维评分、准入结论、证据缺口、可信度与建议动作。"""
    dims, advantages, partial_items, gaps, unconfirmed, actions = [], [], [], [], [], []
    project_type, country = project.get("project_type", ""), project.get("country", "")

    certs = profile.get("existing_certs") or []
    strong_certs = [c for c in certs if "WVTA" in c or "CSMS" in c]
    if len(strong_certs) >= 2:
        dims.append(_dim("资格与准入", "matched", "WVTA 与 CSMS 均已具备", 15, 15, strong_certs))
        advantages.append("资格准入：WVTA 与 CSMS 认证较完整")
    elif strong_certs:
        dims.append(_dim("资格与准入", "partial", "仅覆盖部分关键认证", 8, 15, strong_certs))
        partial_items.append("资格准入：仍需核实项目要求的其他强制认证")
        actions.append("核对招标文件强制认证并补充缺失证据")
    elif certs:
        dims.append(_dim("资格与准入", "gap", "现有认证不包含 WVTA/CSMS", 2, 15, certs))
        gaps.append({"dim": "资格与准入", "desc": "缺少 WVTA 或 CSMS 关键认证", "severity": "P0", "reason": "企业档案认证与欧洲车辆准入要求不匹配"})
        actions.append("制定 WVTA/CSMS 认证补齐计划")
    else:
        dims.append(_dim("资格与准入", "unconfirmed", "认证信息未填写", 4, 15, []))
        unconfirmed.append("现有认证未填写，无法判断准入资格")

    vehicle_state, vehicle_detail = _vehicle_result(profile.get("vehicle_types") or [], project_type)
    vehicle_score = {"matched": 20, "partial": 12, "gap": 3, "unconfirmed": 6}[vehicle_state]
    dims.append(_dim("需求与产品匹配", vehicle_state, vehicle_detail, vehicle_score, 20, profile.get("vehicle_types") or []))
    if vehicle_state == "matched": advantages.append("产品能力：" + vehicle_detail)
    elif vehicle_state == "partial": partial_items.append("产品能力：" + vehicle_detail)
    elif vehicle_state == "gap": gaps.append({"dim": "需求与产品匹配", "desc": vehicle_detail, "severity": "P1", "reason": "项目类型与企业车型不匹配"})
    else: unconfirmed.append(vehicle_detail)

    charging = profile.get("charging_capability", "")
    software = profile.get("software_capability", "")
    if charging and software:
        dims.append(_dim("技术与方案匹配", "matched", "充电与软件能力均有记录", 15, 15, [charging, software]))
        advantages.append("技术方案：具备充电与软件集成能力")
    elif charging or software:
        dims.append(_dim("技术与方案匹配", "partial", "技术能力仅覆盖部分方案", 9, 15, [charging or software]))
        partial_items.append("技术方案：需补充充电或软件能力证据")
    else:
        dims.append(_dim("技术与方案匹配", "unconfirmed", "技术能力未填写", 4, 15, []))
        unconfirmed.append("充电、软件与数据能力未填写")

    materials = profile.get("available_materials") or []
    if len(materials) >= 3:
        dims.append(_dim("合规与材料准备度", "matched", f"已登记 {len(materials)} 项材料", 15, 15, materials))
        advantages.append("合规材料：已有多项可用证据")
    elif materials:
        dims.append(_dim("合规与材料准备度", "partial", f"仅登记 {len(materials)} 项材料", 8, 15, materials))
        partial_items.append("合规材料：材料覆盖不完整")
        actions.append("根据项目法规清单补充 P0/P1 材料")
    else:
        dims.append(_dim("合规与材料准备度", "unconfirmed", "可提供材料未填写", 4, 15, []))
        unconfirmed.append("企业可提供的合规材料未填写")

    local = profile.get("local_after_sales") or []
    country_code = COUNTRY_ALIASES.get(country, country)
    target = profile.get("target_countries") or []
    covers_country = country in local or country_code in local
    targets_country = country in target or country_code in target
    has_entity = str(profile.get("has_eu_entity", "")).startswith("是")
    if covers_country:
        dims.append(_dim("本地化与交付能力", "matched", f"已覆盖 {country} 售后服务", 15, 15, local))
        advantages.append(f"本地化：{country} 已有售后或服务覆盖")
    elif has_entity or targets_country:
        dims.append(_dim("本地化与交付能力", "partial", f"面向 {country}，但当地服务网络待落实", 8, 15, local + target))
        partial_items.append(f"本地化：{country} 服务与备件网络待落实")
        actions.append(f"在伙伴库寻找 {country} 本地运维与售后伙伴")
    else:
        dims.append(_dim("本地化与交付能力", "gap", f"未覆盖 {country} 且无欧洲实体", 2, 15, []))
        gaps.append({"dim": "本地化与交付能力", "desc": f"在 {country} 无本地实体、售后或伙伴", "severity": "P1", "reason": "企业档案本地化能力不足"})
        actions.append(f"优先建立 {country} 本地服务合作网络")

    scale = profile.get("acceptable_scale", "")
    if scale:
        dims.append(_dim("商业吸引力", "matched", "已设置可接受项目规模", 8, 10, [scale]))
        advantages.append("商业约束：已明确可接受项目规模")
    else:
        dims.append(_dim("商业吸引力", "unconfirmed", "项目规模偏好未填写", 3, 10, []))
        unconfirmed.append("可接受项目规模区间未填写")

    delivery = profile.get("delivery_cycle", "")
    if delivery:
        dims.append(_dim("时间与执行可行性", "partial", "已填写交付周期，需结合截止日人工确认", 7, 10, [delivery, project.get("deadline", "")]))
        partial_items.append("时间可行性：需比较交付周期与项目截止时间")
    else:
        dims.append(_dim("时间与执行可行性", "unconfirmed", "交付周期未填写", 3, 10, []))
        unconfirmed.append("交付周期未填写，无法评估时间可行性")

    completeness = int(profile.get("completeness") or 0)
    project_fields = [project.get(k) for k in ("project_name", "country", "project_type", "contracting_authority", "description", "deadline")]
    project_completeness = round(sum(bool(v) for v in project_fields) / len(project_fields) * 100)
    confidence_score = round((completeness + project_completeness) / 2)
    confidence_level = "高" if confidence_score >= 80 else "中" if confidence_score >= 60 else "低"
    if confidence_level != "高":
        actions.insert(0, "先补充企业档案或项目要求，提高匹配可信度")

    total_score = sum(d["score"] for d in dims)
    requirement_gap_matrix = _requirement_gap_matrix(dims, project)
    decision, decision_label, decision_reasons, hard_gates = _admission_decision(
        total_score, confidence_level, requirement_gap_matrix
    )
    for gate in hard_gates:
        actions.insert(0, gate["action"])

    return {
        "total_score": total_score, "max_score": 100,
        "rule_version": RULE_VERSION, "profile_id": profile.get("id"),
        "profile_name": profile.get("org_name", ""), "profile_version": profile.get("version", 1),
        "profile_completeness": completeness, "project_completeness": project_completeness,
        "confidence_score": confidence_score, "confidence_level": confidence_level,
        "dimensions": dims, "advantages": advantages, "partial_items": partial_items,
        "gaps": gaps, "unconfirmed": unconfirmed, "recommended_actions": list(dict.fromkeys(actions)),
        "decision": decision, "decision_label": decision_label,
        "decision_reason": "；".join(decision_reasons), "decision_reasons": decision_reasons,
        "hard_gates": hard_gates, "requirement_gap_matrix": requirement_gap_matrix,
    }
