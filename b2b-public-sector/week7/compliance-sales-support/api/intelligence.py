# -*- coding: utf-8 -*-
"""Intelligence feed API for RSS fetching, paginated queries, saved searches, and fetch logs."""
from fastapi import APIRouter, Query, Depends, HTTPException, Response
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from db import get_session
from models import IntelligenceItem, FetchLog, SavedIntelligenceSearch
from sqlalchemy import desc, or_
from sqlalchemy.exc import IntegrityError
from auth_service import current_identity, require_permission
from rss_scheduler import run_fetch, scheduler_status
from rag_event_service import deliver_event, enqueue_and_deliver
from api.rag import intelligence_event_payload

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence Feed"])
VALID_ALERT_FREQUENCIES = {"daily": 1, "weekly": 7, "monthly": 30}


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    keyword: str = Field(default="", max_length=200)
    country: str = Field(default="", max_length=80)
    source: str = Field(default="", max_length=100)
    frequency: str = "daily"
    enabled: bool = True


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    keyword: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=100)
    frequency: str | None = None
    enabled: bool | None = None


def _clean_saved_search(data: SavedSearchCreate | SavedSearchUpdate, partial: bool = False) -> dict:
    values = data.model_dump(exclude_unset=partial) if hasattr(data, "model_dump") else data.dict(exclude_unset=partial)
    for field in ("name", "keyword", "country", "source", "frequency"):
        if field in values and values[field] is not None:
            values[field] = values[field].strip()
    frequency = values.get("frequency")
    if frequency is not None and frequency not in VALID_ALERT_FREQUENCIES:
        raise HTTPException(422, "Alert frequency must be daily, weekly, or monthly")
    if not partial and not any(values.get(field) for field in ("keyword", "country", "source")):
        raise HTTPException(422, "Enter at least one of the following: keyword, country, or source")
    return values


def _serialize_saved_search(item: SavedIntelligenceSearch) -> dict:
    data = item.to_dict()
    if item.enabled:
        base = item.last_notified_at or item.updated_at or item.created_at or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        data["next_alert_at"] = (base + timedelta(days=VALID_ALERT_FREQUENCIES[item.frequency])).isoformat()
    else:
        data["next_alert_at"] = None
    data["frequency_label"] = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}[item.frequency]
    return data


@router.get("")
def list_intelligence(
    source: str = Query(""),
    keyword: str = Query("", max_length=200),
    offset: int = Query(0),
    limit: int = Query(50),
    review_status: str = Query(""),
):
    with get_session() as s:
        q = s.query(IntelligenceItem)
        if source: q = q.filter(IntelligenceItem.source == source)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            q = q.filter(or_(IntelligenceItem.title.ilike(pattern), IntelligenceItem.summary.ilike(pattern)))
        if review_status: q = q.filter(IntelligenceItem.review_status == review_status)
        total = q.count()
        rows = q.order_by(desc(IntelligenceItem.published_at), desc(IntelligenceItem.fetched_at)).offset(offset).limit(limit).all()
        return {"items": [r.to_dict() for r in rows], "total": total, "offset": offset, "limit": limit}


@router.get("/saved-searches")
def list_saved_searches(identity=Depends(current_identity)):
    _, principal = identity
    with get_session() as session:
        rows = session.query(SavedIntelligenceSearch).filter(
            SavedIntelligenceSearch.organization_id == principal.organization_id,
        ).order_by(desc(SavedIntelligenceSearch.enabled), desc(SavedIntelligenceSearch.updated_at)).all()
        return [_serialize_saved_search(row) for row in rows]


@router.post("/saved-searches", status_code=201)
def create_saved_search(data: SavedSearchCreate, identity=Depends(current_identity)):
    user, principal = identity
    values = _clean_saved_search(data)
    with get_session() as session:
        item = SavedIntelligenceSearch(
            organization_id=principal.organization_id,
            user_id=user.id,
            **values,
        )
        session.add(item)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "A saved search with this name already exists for your organization")
        result = _serialize_saved_search(item)
        session.commit()
        return result


@router.patch("/saved-searches/{search_id}")
def update_saved_search(search_id: int, data: SavedSearchUpdate, identity=Depends(current_identity)):
    _, principal = identity
    values = _clean_saved_search(data, partial=True)
    with get_session() as session:
        item = session.get(SavedIntelligenceSearch, search_id)
        if not item or item.organization_id != principal.organization_id:
            raise HTTPException(404, "Saved search not found")
        for field, value in values.items():
            setattr(item, field, value)
        if not any(getattr(item, field) for field in ("keyword", "country", "source")):
            raise HTTPException(422, "At least one of keyword, country, or source is required")
        item.updated_at = datetime.now(timezone.utc)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "A saved search with this name already exists for your organization")
        result = _serialize_saved_search(item)
        session.commit()
        return result


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: int, identity=Depends(current_identity)):
    _, principal = identity
    with get_session() as session:
        item = session.get(SavedIntelligenceSearch, search_id)
        if not item or item.organization_id != principal.organization_id:
            raise HTTPException(404, "Saved search not found")
        session.delete(item)
        session.commit()
    return Response(status_code=204)


@router.get("/sources")
def list_sources():
    with get_session() as s:
        rows = s.query(IntelligenceItem.source).distinct().order_by(IntelligenceItem.source).all()
        return [r[0] for r in rows]


@router.get("/stats")
def intelligence_stats():
    with get_session() as s:
        total = s.query(IntelligenceItem).count()
        sources = {}
        for src in s.query(IntelligenceItem.source).distinct().all():
            name = src[0]
            sources[name] = s.query(IntelligenceItem).filter(IntelligenceItem.source == name).count()
        last_log = s.query(FetchLog).order_by(desc(FetchLog.run_at)).first()
        last_fetch_str = None
        if last_log and last_log.run_at:
            last_fetch_str = last_log.run_at.strftime("%Y-%m-%dT%H:%M:%SZ")  # Append Z to indicate UTC.
        return {
            "total": total, "sources": sources,
            "last_fetch": last_fetch_str,
            "last_new": last_log.new_count if last_log else 0,
            "last_dup": last_log.duplicate_count if last_log else 0,
        }


@router.post("/fetch")
def trigger_fetch(_=Depends(require_permission("intelligence.fetch"))):
    """Run an RSS fetch and record its execution time and item count (synchronous, about 10–30 seconds)."""
    return run_fetch("manual")


@router.get("/scheduler")
def get_scheduler_status():
    """Return public scheduling status without credentials or internal process details."""
    return scheduler_status()


@router.post("/{item_id}/publish")
def publish_intelligence(
    item_id: int,
    region: str = Query(..., min_length=2, description="Region confirmed by a human, such as DE, EU, or UK"),
    _=Depends(require_permission("intelligence.fetch")),
):
    with get_session() as session:
        item = session.get(IntelligenceItem, item_id)
        if not item: raise HTTPException(404, "Intelligence item not found")
        item.version_no = (item.version_no or 0) + (1 if item.review_status == "published" else 0)
        item.review_status = "published"
        item.review_region = region.strip().upper()
        item.reviewed_at = datetime.now(timezone.utc)
        item.published_at_rag = datetime.now(timezone.utc)
        event_id = enqueue_and_deliver(session, intelligence_event_payload(item))
        version_no = item.version_no
        session.commit()
    return {"status": "published", "id": item_id, "version_no": f"v{version_no}", "rag_event": deliver_event(event_id)}


@router.post("/{item_id}/archive")
def archive_intelligence(item_id: int, _=Depends(require_permission("intelligence.fetch"))):
    with get_session() as session:
        item = session.get(IntelligenceItem, item_id)
        if not item: raise HTTPException(404, "Intelligence item not found")
        item.version_no = (item.version_no or 0) + 1
        item.review_status = "archived"
        item.reviewed_at = datetime.now(timezone.utc)
        event_id = enqueue_and_deliver(session, intelligence_event_payload(item, "archive"))
        version_no = item.version_no
        session.commit()
    return {"status": "archived", "id": item_id, "version_no": f"v{version_no}", "rag_event": deliver_event(event_id)}
