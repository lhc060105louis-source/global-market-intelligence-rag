# -*- coding: utf-8 -*-
"""客户支持业务服务 —— 客户场景→法规联动匹配 + 销售支持包生成。
纯 Python,不依赖 Streamlit。"""
import data_clients as C
from db import load_regulations, load_material_status

PRIO_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def get_client(key_or_type: str) -> dict | None:
    for c in C.CLIENTS:
        if c.get("client_key") == key_or_type or c["client_type"] == key_or_type:
            return c
    return None


def match_compliance_gaps(client: dict) -> list[dict]:
    """给定客户画像,返回该场景适用的法规材料清单(含实时缺口状态)。"""
    regs = {r["regulation_id"]: r for r in load_regulations()}
    ms_all = load_material_status()
    linked_ids = client.get("link_regulations", [])
    rows = []
    for rid in linked_ids:
        r = regs.get(rid)
        if not r:
            continue
        for mname, prio in r["provide"]:
            mkey = f"{rid}||{mname}"
            ms = ms_all.get(mkey, {})
            status = ms.get("status", "待确认")
            is_gap = prio == "P0" and status not in {"已准备", "不适用"}
            rows.append({
                "优先级": prio, "所需材料": mname, "对应法规": r["name"],
                "企业状态": status, "_gap": is_gap,
            })
    rows.sort(key=lambda x: (PRIO_ORDER.get(x["优先级"], 9), not x["_gap"]))
    return rows


def count_client_p0_gaps(client: dict) -> int:
    return sum(1 for r in match_compliance_gaps(client) if r["_gap"])


def build_sales_pack(client: dict) -> str:
    """生成客户专属销售支持包(Markdown)。"""
    lines = [
        f"# 销售支持包 · {client['client_type']}", "",
        f"**客户示例:** {client.get('sample_name','')}　|　**区域:** {client.get('region','')}　|　**场景:** {client.get('scenario','')}", "",
        f"> {client['portrait']}", "",
        "## 一、客户需求分析",
        "**主要痛点:** " + "；".join(client.get("painpoints", [])),
        "**采购关注点:** " + "、".join(client.get("focus", [])), "",
        "## 二、产品服务方案",
        "- 产品方向:" + "；".join(client.get("product", [])),
        "- 技术方案:" + "；".join(client.get("tech", [])),
        "- 服务方案:" + "；".join(client.get("service", [])), "",
        "## 三、销售案例与佐证",
    ]
    for case in client.get("cases", []):
        flag = "✅ 可靠来源" if case.get("verified") else "◻ 方向·待补真实来源"
        lines.append(f"- **{case['title']}** [{flag}]:{case.get('detail','')}(来源:{case.get('source','')})")
    lines += [
        "**佐证材料:** " + "、".join(client.get("evidence", [])), "",
        f"**核心沟通重点:** {client.get('talking_points','')}", "",
        "## 四、合规材料清单(P0-P3,实时状态)",
    ]
    gaps = match_compliance_gaps(client)
    for g in gaps:
        mark = "🔴" if g["_gap"] else "　"
        lines.append(f"- {mark} [{g['优先级']}] {g['所需材料']}（{g['对应法规']}）— 状态:{g['企业状态']}")
    lines += ["", "---", "*本支持包为规则辅助生成,合规结论以授权人员确认为准。*"]
    return "\n".join(lines)
