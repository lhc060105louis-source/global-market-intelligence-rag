# -*- coding: utf-8 -*-
"""法规 API —— 查询 / 详情 / 材料状态 / CRUD"""
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

router = APIRouter(prefix="/api/regulations", tags=["法规"])


@router.get("")
def list_regulations(
    scope: str = Query("", description="适用范围(EU全域/成员国:德国等)"),
    type: str = Query("", description="法规类型(电池合规/网络安全/数据与AI等)"),
    impact: str = Query("", description="影响程度(高/中/低)"),
    kw: str = Query("", description="关键词搜索"),
    sort: str = Query("影响程度↓", description="排序方式"),
    identity=Depends(optional_identity),
):
    """多维筛选法规列表。"""
    rows = rs.list_regulations(scope=scope, reg_type=type, impact=impact, kw=kw, sort_by=sort)
    if not identity or not can(identity[1], "project.view_exact"):
        for row in rows:
            row["official_source"] = ""
            row["last_verified_at"] = ""
    return rows


@router.get("/{regulation_id}")
def regulation_detail(regulation_id: str, identity=Depends(optional_identity)):
    """法规详情,含材料清单和缺口。"""
    r = get_regulation(regulation_id)
    if not r:
        raise HTTPException(404, f"法规 {regulation_id} 不存在")
    p0_gap = rs.count_p0_gap(r)
    if not identity or not can(identity[1], "project.view_exact"):
        r["official_source"] = ""
        r["last_verified_at"] = ""
    # 详情页需要一次拿到法规和材料状态。此前这里只返回法规主体，
    # 前端读取 response.materials 时得到空数组，导致材料清单始终显示 0 项。
    materials = regulation_materials(regulation_id)["materials"]
    return {"regulation": r, "materials": materials, "p0_gap_count": p0_gap}


@router.get("/{regulation_id}/materials")
def regulation_materials(regulation_id: str):
    """某法规的材料清单(含实时状态)。"""
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
            "status": ms.get("status", "待确认"), "owner": ms.get("owner", ""),
            "due_date": ms.get("due_date", ""),
        })
    return {"regulation_id": regulation_id, "materials": items}


@router.patch("/materials/{mkey}")
def update_material_status(
    mkey: str,
    status: str = Query(..., description="待确认/已准备/缺失/待更新/审核中/已过期/不适用"),
    owner: str = Query(""),
    _=Depends(require_permission("material.update")),
):
    """更新单条材料准备状态(对齐 PRD 8.4 七种状态)。"""
    valid = {"待确认", "已准备", "缺失", "待更新", "审核中", "已过期", "不适用"}
    if status not in valid:
        raise HTTPException(422, f"无效状态,允许:{valid}")
    set_material_status(mkey, status, owner)
    return {"mkey": mkey, "status": status, "owner": owner}


@router.post("")
def create_regulation(data: dict, _=Depends(require_permission("regulation.manage"))):
    """新增/更新法规(upsert)。"""
    if not data.get("regulation_id") or not data.get("name"):
        raise HTTPException(422, "regulation_id 和 name 为必填")
    with get_session() as session:
        regulation = session.get(Regulation, data["regulation_id"])
        was_published = bool(regulation and regulation.rag_status == "published")
        if regulation:
            for key, value in data.items():
                if hasattr(regulation, key): setattr(regulation, key, value)
        else:
            regulation = Regulation(**data)
            session.add(regulation)
        should_publish = data.get("status") == "已审核"
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
    """P0 缺口统计 + 缺口清单。"""
    p0_total, p0_gap, total = rs.gap_stats()
    return {"p0_total": p0_total, "p0_gap": p0_gap, "total_gap": total, "gap_list": rs.p0_gap_list()}
