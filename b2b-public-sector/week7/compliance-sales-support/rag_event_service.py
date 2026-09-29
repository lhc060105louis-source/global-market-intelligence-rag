# -*- coding: utf-8 -*-
"""Reliably notify the RAG Hub of business events without calling MaxKB directly."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from db import get_session
from models import RagEventOutbox

RAG_HUB_BASE_URL = os.getenv("RAG_HUB_BASE_URL", "").rstrip("/")
RAG_HUB_API_KEY = os.getenv("RAG_HUB_API_KEY", "")
B_END_PUBLIC_URL = os.getenv("B_END_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
RAG_PUSH_ENABLED = os.getenv("RAG_PUSH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def iso(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value).strip()
    if text.endswith("Z"):
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    else:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"Invalid time format: {text}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def absolute_detail_url(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{B_END_PUBLIC_URL}/{path.lstrip('/')}"


RECORD_TYPES = {
    "policy": "business_policy", "procurement": "business_procurement",
    "market": "business_market", "customer_partner": "business_customer_partner",
}


def make_payload(*, event_type: str, upstream_id: str, upstream_version: int,
                 status: str, title: str, summary: str, content: str,
                 entry_type: str, countries: list[str], tags: list[str],
                 evidence: list[dict], detail_url: str, published_at,
                 related_entities: list[dict] | None = None, business_impact: str = "",
                 recommended_action: str = "", is_mock: bool = True) -> dict:
    if event_type not in {"upsert", "archive"}:
        raise ValueError("event_type must be 'upsert' or 'archive'")
    if status not in {"published", "archived"}:
        raise ValueError("Only published or archived content can enter RAG")
    if entry_type not in RECORD_TYPES:
        raise ValueError(f"Unsupported B2B business type: {entry_type}")
    if not isinstance(upstream_version, int) or upstream_version < 1:
        raise ValueError("source_version must be an integer greater than or equal to 1")
    if not countries:
        raise ValueError("At least one region is required; add it manually before publishing the RSS item")
    now = datetime.now(timezone.utc)
    published = iso(published_at or now)
    return {
        "source_system": "B", "source_record_id": upstream_id,
        "record_type": RECORD_TYPES[entry_type],
        "event_type": "update_current" if event_type == "upsert" else "archive",
        "source_version": upstream_version, "effective_at": published,
        "source_updated_at": iso(now), "source_url": absolute_detail_url(detail_url),
        "push_id": "", "is_mock": is_mock,
        "payload": {
            "entry_id": upstream_id, "entry_type": entry_type, "title": title,
            "published_summary": summary or content or title, "regions": countries,
            "tags": tags, "related_entities": related_entities or [],
            "business_impact": business_impact or None,
            "recommended_action": recommended_action or None,
            # publication_status determines whether content is eligible for the Hub:
            # only content that was formally published may enter. The top-level
            # event_type=archive field represents the final archival action.
            "external_sources": evidence, "publication_status": "published",
            "published_at": published,
        },
    }


def enqueue(session: Session, payload: dict) -> RagEventOutbox:
    event_id = f"b-end-{uuid.uuid4()}"
    payload["push_id"] = event_id
    event = RagEventOutbox(
        event_id=event_id, upstream_id=payload["source_record_id"],
        upstream_version=str(payload["source_version"]), event_type=payload["event_type"],
        payload=json.dumps(payload, ensure_ascii=False), delivery_status="pending",
    )
    session.add(event)
    return event


def _send(event: RagEventOutbox) -> None:
    if not RAG_PUSH_ENABLED or not RAG_HUB_BASE_URL:
        raise RuntimeError("RAG push is disabled or RAG_HUB_BASE_URL is not configured")
    headers = {"Content-Type": "application/json"}
    if RAG_HUB_API_KEY:
        headers["X-API-Key"] = RAG_HUB_API_KEY
    request = Request(
        f"{RAG_HUB_BASE_URL}/api/v1/ingestion/b",
        data=event.payload.encode("utf-8"), headers=headers, method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"RAG Hub Back HTTP {response.status}")


def deliver_event(event_id: str) -> dict:
    with get_session() as session:
        event = session.query(RagEventOutbox).filter(RagEventOutbox.event_id == event_id).first()
        if not event:
            return {"event_id": event_id, "status": "missing"}
        if event.delivery_status == "delivered":
            return {"event_id": event_id, "status": "delivered"}
        event.attempt_count += 1
        try:
            _send(event)
            event.delivery_status = "delivered"
            event.delivered_at = datetime.now(timezone.utc)
            event.last_error = ""
            event.next_retry_at = None
        except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as error:
            event.delivery_status = "pending" if RAG_PUSH_ENABLED else "disabled"
            event.last_error = str(error)[:1000]
            event.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=min(60, 2 ** min(event.attempt_count, 5)))
        session.commit()
        return {"event_id": event.event_id, "status": event.delivery_status, "attempt_count": event.attempt_count}


def deliver_pending(limit: int = 50) -> dict:
    with get_session() as session:
        ids = [row.event_id for row in session.query(RagEventOutbox).filter(
            RagEventOutbox.delivery_status.in_(["pending", "disabled"])
        ).order_by(RagEventOutbox.created_at).limit(limit).all()]
    results = [deliver_event(event_id) for event_id in ids]
    return {"processed": len(results), "results": results}


def enqueue_and_deliver(session: Session, payload: dict) -> str:
    """The caller must commit afterward; return the ID, then call deliver_event after committing."""
    return enqueue(session, payload).event_id
