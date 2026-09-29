# -*- coding: utf-8 -*-
"""法规业务服务 —— 查询/筛选/排序/缺口引擎。纯 Python,不依赖 Streamlit 或任何 UI。
以后换 FastAPI 时,本模块一行不改,直接 import。"""
from models import Regulation, MaterialStatus
from db import get_session, load_material_status

IMPACT_ORDER = {"高": 3, "中": 2, "低": 1}
PRIO_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
STATUS_READY = {"已准备", "不适用"}


def list_regulations(
    scope: str = "", reg_type: str = "", impact: str = "", kw: str = "",
    sort_by: str = "影响程度↓",
) -> list[dict]:
    """多维筛选 + 排序,返回匹配的法规列表(dict)。"""
    with get_session() as s:
        q = s.query(Regulation)
        if scope:
            q = q.filter(Regulation.scope == scope)
        if reg_type:
            q = q.filter(Regulation.type == reg_type)
        if impact:
            q = q.filter(Regulation.impact_level == impact)
        rows = [r.to_dict() for r in q.all()]

    if kw:
        kw_lower = kw.lower()
        rows = [r for r in rows if kw_lower in (r["name"] + r.get("official_number","") + r["core_requirement"]).lower()]

    if sort_by == "影响程度↓":
        rows.sort(key=lambda r: -IMPACT_ORDER.get(r["impact_level"], 0))
    elif sort_by == "更新时间↓":
        rows.sort(key=lambda r: r.get("last_verified_at", ""), reverse=True)
    elif sort_by == "更新时间↑":
        rows.sort(key=lambda r: r.get("last_verified_at", ""))
    else:
        rows.sort(key=lambda r: r["name"])
    return rows


def get_regulation(rid: str) -> dict | None:
    from db import get_regulation as _get
    return _get(rid)


def upsert_regulation(data: dict) -> None:
    from db import upsert_regulation as _upsert
    _upsert(data)


def count_p0_gap(reg: dict) -> int:
    """计算单条法规的 P0 缺口数(材料未准备=缺口)。"""
    ms_all = load_material_status()
    return sum(
        1 for m, p in reg["provide"] if p == "P0"
        and ms_all.get(f"{reg['regulation_id']}||{m}", {}).get("status") not in STATUS_READY
    )


def gap_stats() -> tuple[int, int, int]:
    """返回 (p0_total, p0_gap, total_gap)。对齐 PRD 8.4/8.5 颜色规则。"""
    ms_all = load_material_status()
    p0_total = p0_gap = total_gap = 0
    for m in ms_all.values():
        if m["priority"] == "P0":
            p0_total += 1
            if m["status"] not in STATUS_READY:
                p0_gap += 1
        if m["status"] not in STATUS_READY and m.get("status") != "审核中":
            total_gap += 1
    return p0_total, p0_gap, total_gap


def p0_gap_list() -> list[dict]:
    """P0 缺口清单,供 Dashboard 和报告中心使用。"""
    from db import load_regulations
    regs = {r["regulation_id"]: r["name"] for r in load_regulations()}
    ms_all = load_material_status()
    rows = []
    for m in ms_all.values():
        if m["priority"] == "P0" and m["status"] not in STATUS_READY:
            rows.append({
                "法规": regs.get(m["regulation_id"], m["regulation_id"]),
                "缺失材料": m["material_name"], "优先级": m["priority"],
                "当前状态": m["status"], "负责人": m["owner"] or "—",
            })
    return rows
