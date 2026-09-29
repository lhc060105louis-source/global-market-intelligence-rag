# -*- coding: utf-8 -*-
"""Regulation API: list, detail, material status, and CRUD operations."""
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, timezone

import regulations_service as rs
from db import load_regulations, get_regulation, get_session
from db import load_material_status, set_material_status
from auth_service import optional_identity, require_permission
from permissions import can
from models import Regulation
from rag_event_service import deliver_event, enqueue_and_deliver
from api.rag import regulation_event_payload

router = APIRouter(prefix="/api/regulations", tags=["Regulation"])


@router.get("")
def list_regulations(
    scope: str = Query("", description="Applicable scope (EU-wide or a member state such as Germany)"),
    type: str = Query("", description="Regulation type, such as battery compliance, cybersecurity, or data and AI"),
    impact: str = Query("", description="Impact level (High/Medium/Low)"),
    kw: str = Query("", description="KeywordsSearch"),
    sort: str = Query("Impact ↓", description="Sort order"),
    identity=Depends(optional_identity),
):
    """Filter and return regulations."""
    rows = rs.list_regulations(scope=scope, reg_type=type, impact=impact, kw=kw, sort_by=sort)
    if not identity or not can(identity[1], "project.view_exact"):
        for row in rows:
            row["official_source"] = ""
            row["last_verified_at"] = ""
    return rows


@router.get("/{regulation_id}")
def regulation_detail(regulation_id: str, identity=Depends(optional_identity)):
    """Return regulation details, including the materials checklist and gaps."""
    r = get_regulation(regulation_id)
    if not r:
        raise HTTPException(404, f"Regulation {regulation_id} was not found")
    p0_gap = rs.count_p0_gap(r)
    if not identity or not can(identity[1], "project.view_exact"):
        r["official_source"] = ""
        r["last_verified_at"] = ""
    # Return the regulation and material statuses together for the detail view.
    # Previously, only the regulation was returned, leaving response.materials empty.
    materials = regulation_materials(regulation_id)["materials"]
    return {"regulation": r, "materials": materials, "p0_gap_count": p0_gap}


@router.get("/{regulation_id}/materials")
def regulation_materials(regulation_id: str):
    """Return a regulation's materials checklist with current statuses."""
    r = get_regulation(regulation_id)
    if not r:
        raise HTTPException(404)
    ms_all = load_material_status()
    items = []
    for mname, prio in r["provide"]:
        mkey = f"{regulation_id}||{mname}"
        ms = ms_all.get(mkey, {})
        items.append({
            "name": mname, "priority": prio,
            "status": ms.get("status", "Unconfirmed"), "owner": ms.get("owner", ""),
            "due_date": ms.get("due_date", ""),
        })
    return {"regulation_id": regulation_id, "materials": items}


@router.patch("/materials/{mkey}")
def update_material_status(
    mkey: str,
    status: str = Query(..., description="Unconfirmed/Ready/Missing/Needs Update/Under Review/Expired/Not Applicable"),
    owner: str = Query(""),
    _=Depends(require_permission("material.update")),
):
    """Update one material's preparation status using the seven PRD 8.4 values."""
    valid = {"Unconfirmed", "Ready", "Missing", "Needs Update", "Under Review", "Expired", "Not Applicable"}
    if status not in valid:
        raise HTTPException(422, f"Invalid status. Allowed values: {valid}")
    set_material_status(mkey, status, owner)
    return {"mkey": mkey, "status": status, "owner": owner}


@router.post("")
def create_regulation(data: dict, _=Depends(require_permission("regulation.manage"))):
    """Create or update a regulation."""
    if not data.get("regulation_id") or not data.get("name"):
        raise HTTPException(422, "regulation_id and name are required")
    with get_session() as session:
        regulation = session.get(Regulation, data["regulation_id"])
        was_published = bool(regulation and regulation.rag_status == "published")
        if regulation:
            for key, value in data.items():
                if hasattr(regulation, key): setattr(regulation, key, value)
        else:
            regulation = Regulation(**data)
            session.add(regulation)
        should_publish = data.get("status") == "Approved"
        event_id = None
        if should_publish:
            regulation.rag_version = (regulation.rag_version or 1) + 1 if was_published else 1
            regulation.rag_status = "published"
            regulation.published_at = datetime.now(timezone.utc)
            event_id = enqueue_and_deliver(session, regulation_event_payload(regulation))
        else:
            regulation.rag_status = "draft"
        session.commit()
    delivery = deliver_event(event_id) if event_id else None
    return {"status": "ok", "regulation_id": data["regulation_id"], "rag_event": delivery}


@router.delete("/{regulation_id}")
def remove_regulation(regulation_id: str, _=Depends(require_permission("regulation.manage"))):
    with get_session() as session:
        regulation = session.get(Regulation, regulation_id)
        if not regulation: raise HTTPException(404)
        regulation.rag_status = "archived"
        regulation.rag_version = (regulation.rag_version or 0) + 1
        event_id = enqueue_and_deliver(session, regulation_event_payload(regulation, "archive"))
        session.commit()
    delivery = deliver_event(event_id)
    return {"status": "archived", "regulation_id": regulation_id, "rag_event": delivery}


@router.get("/stats/gaps")
def gap_summary():
    """Return P0 gap statistics and the gap list."""
    p0_total, p0_gap, total = rs.gap_stats()
    return {"p0_total": p0_total, "p0_gap": p0_gap, "total_gap": total, "gap_list": rs.p0_gap_list()}
