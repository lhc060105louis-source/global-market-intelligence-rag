# -*- coding: utf-8 -*-
"""Regulation query, filtering, sorting, and gap calculations, without a UI dependency.

This module can be imported directly if the application later switches to FastAPI.
"""
from models import Regulation, MaterialStatus
from db import get_session, load_material_status

IMPACT_ORDER = {"High": 3, "Medium": 2, "Low": 1}
PRIO_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
STATUS_READY = {"Ready", "Not Applicable"}


def list_regulations(
    scope: str = "", reg_type: str = "", impact: str = "", kw: str = "",
    sort_by: str = "Impact ↓",
) -> list[dict]:
    """Filter and sort regulations across multiple dimensions."""
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

    if sort_by == "Impact ↓":
        rows.sort(key=lambda r: -IMPACT_ORDER.get(r["impact_level"], 0))
    elif sort_by == "Updated ↓":
        rows.sort(key=lambda r: r.get("last_verified_at", ""), reverse=True)
    elif sort_by == "Updated ↑":
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
    """Count P0 gaps for one regulation; unprepared materials count as gaps."""
    ms_all = load_material_status()
    return sum(
        1 for m, p in reg["provide"] if p == "P0"
        and ms_all.get(f"{reg['regulation_id']}||{m}", {}).get("status") not in STATUS_READY
    )


def gap_stats() -> tuple[int, int, int]:
    """Return (p0_total, p0_gap, total_gap), following PRD sections 8.4 and 8.5."""
    ms_all = load_material_status()
    p0_total = p0_gap = total_gap = 0
    for m in ms_all.values():
        if m["priority"] == "P0":
            p0_total += 1
            if m["status"] not in STATUS_READY:
                p0_gap += 1
        if m["status"] not in STATUS_READY and m.get("status") != "Under Review":
            total_gap += 1
    return p0_total, p0_gap, total_gap


def p0_gap_list() -> list[dict]:
    """Return the P0 gap list for the dashboard and report center."""
    from db import load_regulations
    regs = {r["regulation_id"]: r["name"] for r in load_regulations()}
    ms_all = load_material_status()
    rows = []
    for m in ms_all.values():
        if m["priority"] == "P0" and m["status"] not in STATUS_READY:
            rows.append({
                "Regulation": regs.get(m["regulation_id"], m["regulation_id"]),
                "Missing Material": m["material_name"], "Priority": m["priority"],
                "Current Status": m["status"], "Owner": m["owner"] or "—",
            })
    return rows
