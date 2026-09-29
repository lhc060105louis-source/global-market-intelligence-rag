"""Persistence helpers for the scenario-neutral coordination foundation."""
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AssociationCandidate, CaseDomainImpact, CoordinationAuditEvent, CoordinationCase,
    CoordinationTask, DomainEvent, DomainEventRevision, ExecutionResult, IngestionEvent,
    KnowledgeRecord, utc_now,
)


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_hash = stable_hash


def audit(db: Session, *, aggregate_type: str, aggregate_id: str, action: str, actor_type: str,
          case_id: str | None = None,
          actor_id: str | None = None, from_state: str | None = None, to_state: str | None = None,
          object_version: int | None = None, request_id: str | None = None, reason: str | None = None,
          payload: dict[str, Any] | None = None) -> CoordinationAuditEvent:
    item = CoordinationAuditEvent(
        aggregate_type=aggregate_type, aggregate_id=aggregate_id, action=action,
        case_id=case_id,
        actor_type=actor_type, actor_id=actor_id, from_state=from_state, to_state=to_state,
        execution_mode="demo" if actor_type == "demo_driver" else None,
        object_version=object_version, request_id=request_id, reason=reason,
        payload_summary_json=payload or {},
    )
    db.add(item)
    return item


def validate_evidence(db: Session, refs: list[dict[str, Any]]) -> None:
    for ref in refs:
        record = db.get(KnowledgeRecord, ref["record_id"])
        if record is None:
            raise ValueError("evidence_unresolved")
        payload = None
        if record.source_version == ref["source_version"]:
            payload = record.payload_json
        else:
            historical_event = db.scalar(select(IngestionEvent).where(
                IngestionEvent.record_id == record.id,
                IngestionEvent.source_version == ref["source_version"],
                IngestionEvent.error_code.is_(None),
            ).order_by(IngestionEvent.received_at.desc(), IngestionEvent.id.desc()))
            if historical_event:
                payload = (historical_event.request_json or {}).get("payload")
        if not isinstance(payload, dict):
            raise ValueError("evidence_unresolved")
        field_path = ref["field_path"].split(".")
        value: Any = {"payload": payload}
        try:
            for part in field_path:
                value = value[part]
        except (KeyError, TypeError):
            raise ValueError("evidence_unresolved")
        if stable_hash(value) != ref["excerpt_hash"]:
            raise ValueError("evidence_unresolved")


def event_revision_payload(body: Any) -> dict[str, Any]:
    return {
        "event_version": 1,
        "event_action": "create",
        "execution_mode": body.execution_mode,
        "is_simulated": body.is_simulated,
        "source_record_version": body.source_record_version,
        "subject": body.subject,
        "severity": body.severity,
        "occurred_at": body.occurred_at,
        "professional_status": body.professional_status,
        "related_record_ids": body.related_record_ids,
        "evidence_refs": [item.model_dump(mode="json") for item in body.evidence_refs],
        "payload_hash": _hash(body.model_dump(mode="json")),
        "created_by": body.created_by,
    }


def next_sequence(db: Session, model: Any, where: Any, column: Any) -> int:
    current = db.scalar(select(column).where(where).order_by(column.desc()).limit(1))
    return int(current or 0) + 1


def claim_coordination_push(
    db: Session,
    *,
    push_id: str,
    payload: dict[str, Any],
    source_system: str,
    source_record_id: str,
    source_version: int,
    ingestion_kind: str,
    target_object_type: str,
) -> IngestionEvent | None:
    """Return an existing idempotent receipt or reserve a new one.

    This deliberately reuses the knowledge-ingestion ledger. ``None`` means
    the caller may create the target object; an existing receipt with the same
    hash is returned so the caller can replay its original response.
    """
    payload_hash = stable_hash(payload)
    existing = db.scalar(select(IngestionEvent).where(IngestionEvent.push_id == push_id))
    if existing:
        if existing.payload_hash != payload_hash:
            raise ValueError("push_id_conflict")
        if existing.ingestion_kind != ingestion_kind or existing.target_object_type != target_object_type:
            raise ValueError("push_id_conflict")
        return existing
    receipt = IngestionEvent(
        push_id=push_id, payload_hash=payload_hash, source_system=source_system,
        source_record_id=source_record_id, source_version=source_version,
        decision="processing", request_json=payload, ingestion_kind=ingestion_kind,
        target_object_type=target_object_type,
    )
    db.add(receipt)
    db.flush()
    return None
