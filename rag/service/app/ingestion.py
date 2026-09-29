import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import IngestionEvent, KnowledgeRecord, RagSyncTask, RiskEpisode, RiskObject, RiskTrendPoint, utc_now
from .retrieval_text import encoding_corruption, generate_retrieval_text
from .schemas import B_RECORD_TYPES, C_RECORD_TYPES, KOL_RECORD_TYPES, RISK_RECORD_TYPES, IngestionEnvelope
from .text_quality import TextQualityError, validate_text_quality


class IngestionError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalized_request(envelope: IngestionEnvelope) -> dict[str, Any]:
    data = envelope.model_dump(mode="json")
    data.pop("push_id", None)
    for name in ("effective_at", "source_updated_at"):
        data[name] = envelope.__getattribute__(name).astimezone(timezone.utc).isoformat()
    return data


def validate_endpoint_and_event(envelope: IngestionEnvelope, endpoint: str) -> None:
    expected = {"c": "C", "b": "B", "kol": "KOL"}[endpoint]
    if envelope.source_system != expected:
        raise IngestionError(422, "source_system_mismatch", "source_system does not match endpoint")
    allowed_types = C_RECORD_TYPES if expected == "C" else B_RECORD_TYPES if expected == "B" else KOL_RECORD_TYPES
    if envelope.record_type not in allowed_types:
        raise IngestionError(422, "record_type_mismatch", "record_type does not match endpoint")
    if envelope.event_type == "create_snapshot" and expected != "C":
        raise IngestionError(422, "invalid_event", "create_snapshot is only valid for C")
    if envelope.event_type == "risk_recovery" and (expected != "C" or envelope.record_type not in RISK_RECORD_TYPES):
        raise IngestionError(422, "invalid_event", "risk_recovery is only valid for C risk records")


def business_identity(envelope: IngestionEnvelope, payload: dict[str, Any]) -> tuple[str, str, str, Any]:
    if envelope.source_system == "C":
        mode = "snapshot" if envelope.event_type == "create_snapshot" else "current"
        key = f"{payload['scope_id']}|{payload['dimension']}"
        business_date = date.fromisoformat(payload["business_date"]) if mode == "snapshot" else None
        if business_date:
            key = f"{key}|{business_date}"
        target = "c_history" if mode == "snapshot" else "c_current"
        return key, mode, target, business_date
    if envelope.source_system == "B":
        return payload["entry_id"], "current", "b_business", None
    key_name = "kol_id" if envelope.record_type == "kol_current_assessment" else "cooperation_id"
    return payload[key_name], "current", "kol", None


def latest_sync_status(db: Session, record_id: str | None) -> str | None:
    if not record_id:
        return None
    task = db.scalar(
        select(RagSyncTask).where(RagSyncTask.record_id == record_id).order_by(RagSyncTask.created_at.desc(), RagSyncTask.id.desc())
    )
    return task.status if task else None


def _create_event(envelope: IngestionEnvelope, payload_hash: str, request_json: dict[str, Any]) -> IngestionEvent:
    return IngestionEvent(
        push_id=envelope.push_id,
        payload_hash=payload_hash,
        source_system=envelope.source_system,
        source_record_id=envelope.source_record_id,
        source_version=envelope.source_version,
        decision="processing",
        request_json=request_json,
    )


def _finish_error(db: Session, event: IngestionEvent, code: str, message: str) -> None:
    event.decision = code
    event.error_code = code
    event.error_message = message
    event.completed_at = utc_now()
    db.commit()


def _update_risk(db: Session, envelope: IngestionEnvelope, record: KnowledgeRecord, payload: dict[str, Any]) -> None:
    result = payload["result"]
    risk_object = db.scalar(
        select(RiskObject).where(
            RiskObject.vehicle_model == payload["vehicle_model"],
            RiskObject.part == result["part"],
            RiskObject.region == payload["region"],
            RiskObject.risk_type == result["risk_type"],
        )
    )
    if risk_object is None and (envelope.event_type == "risk_recovery" or not result["threshold_exceeded"]):
        return
    if risk_object is None:
        risk_object = RiskObject(
            vehicle_model=payload["vehicle_model"], part=result["part"], region=payload["region"],
            risk_type=result["risk_type"], brand=payload["brand"],
        )
        db.add(risk_object)
        db.flush()
    risk_object.brand = payload["brand"]
    open_episode = db.scalar(select(RiskEpisode).where(RiskEpisode.risk_object_id == risk_object.id, RiskEpisode.status == "open"))
    if envelope.event_type == "risk_recovery":
        if open_episode:
            open_episode.status = "recovered"
            open_episode.recovered_at = envelope.effective_at.astimezone(timezone.utc)
        return
    if not result["threshold_exceeded"]:
        return
    if open_episode is None:
        open_episode = RiskEpisode(
            risk_object_id=risk_object.id, status="open",
            started_at=envelope.effective_at.astimezone(timezone.utc),
            current_value=result["hit_count"], threshold=result["threshold"],
        )
        db.add(open_episode)
        db.flush()
    else:
        open_episode.current_value = result["hit_count"]
        open_episode.threshold = result["threshold"]
    exists = db.scalar(
        select(RiskTrendPoint.id).where(
            RiskTrendPoint.episode_id == open_episode.id,
            RiskTrendPoint.business_time == envelope.effective_at.astimezone(timezone.utc),
            RiskTrendPoint.source_version == envelope.source_version,
        )
    )
    if not exists:
        db.add(RiskTrendPoint(
            episode_id=open_episode.id, business_time=envelope.effective_at.astimezone(timezone.utc),
            hit_value=result["hit_count"], threshold=result["threshold"],
            source_record_id=record.id, source_version=envelope.source_version,
        ))


def _ingest_once(db: Session, envelope: IngestionEnvelope, endpoint: str) -> tuple[dict[str, Any], int]:
    validate_endpoint_and_event(envelope, endpoint)
    try:
        payload_model = envelope.validated_payload()
    except (ValidationError, ValueError) as exc:
        raise IngestionError(422, "invalid_payload", str(exc)) from exc
    if envelope.event_type == "risk_recovery" and payload_model.result.threshold_exceeded:
        raise IngestionError(422, "invalid_risk_recovery", "risk_recovery requires threshold_exceeded=false")
    payload_data = payload_model.model_dump(mode="python")
    if envelope.source_system == "C":
        payload_data["result"] = payload_model.result.model_dump(mode="python", exclude_none=True)
    payload = normalize_json_value(payload_data)
    try:
        # Validate before adding the event/record.  Committing an event after
        # constructing a corrupted record would leave that record in SQLite
        # even though its sync task never reaches MaxKB.
        validate_text_quality(payload)
    except TextQualityError as exc:
        raise IngestionError(422, "text_quality_invalid", str(exc)) from exc
    request_json = envelope.model_dump(mode="json")
    stable_request = normalized_request(envelope)
    stable_request["payload"] = payload
    payload_hash = sha256(stable_request)
    content_hash = sha256(payload)

    previous_event = db.scalar(select(IngestionEvent).where(IngestionEvent.push_id == envelope.push_id))
    if previous_event:
        if previous_event.payload_hash != payload_hash:
            previous_event.conflict_count += 1
            previous_event.last_conflict_at = utc_now()
            db.commit()
            raise IngestionError(409, "push_id_conflict", "push_id was already used with different content")
        if previous_event.error_code:
            raise IngestionError(409, previous_event.error_code, previous_event.error_message or previous_event.error_code)
        return {
            "decision": previous_event.decision,
            "record_id": previous_event.record_id,
            "source_version": previous_event.source_version,
            "sync_status": latest_sync_status(db, previous_event.record_id),
        }, 200

    event = _create_event(envelope, payload_hash, request_json)
    db.add(event)
    key, mode, target, business_date = business_identity(envelope, payload)
    record = db.scalar(select(KnowledgeRecord).where(
        KnowledgeRecord.source_system == envelope.source_system,
        KnowledgeRecord.record_type == envelope.record_type,
        KnowledgeRecord.business_key == key,
        KnowledgeRecord.record_mode == mode,
    ))

    if record and record.source_record_id != envelope.source_record_id:
        _finish_error(db, event, "source_record_conflict", "business key is already mapped to a different source_record_id")
        raise IngestionError(409, "source_record_conflict", "business key is already mapped to a different source_record_id")

    if record and envelope.source_version < record.source_version:
        event.decision = "ignored_older_version"
        event.record_id = record.id
        event.completed_at = utc_now()
        db.commit()
        return {"decision": event.decision, "record_id": record.id, "source_version": envelope.source_version,
                "sync_status": latest_sync_status(db, record.id)}, 200
    if record and envelope.source_version == record.source_version:
        if content_hash != record.content_hash:
            _finish_error(db, event, "version_conflict", "same source_version has different content")
            raise IngestionError(409, "version_conflict", "same source_version has different content")
        event.decision = "duplicate"
        event.record_id = record.id
        event.completed_at = utc_now()
        db.commit()
        return {"decision": "duplicate", "record_id": record.id, "source_version": envelope.source_version,
                "sync_status": latest_sync_status(db, record.id)}, 200

    if envelope.event_type in {"archive", "restore", "risk_recovery"} and record is None:
        _finish_error(db, event, "invalid_transition", "the target record does not exist")
        raise IngestionError(409, "invalid_transition", "the target record does not exist")
    if envelope.event_type == "restore" and record.status != "archived":
        _finish_error(db, event, "invalid_transition", "only an archived record can be restored")
        raise IngestionError(409, "invalid_transition", "only an archived record can be restored")
    if record and record.status == "archived" and envelope.event_type in {"update_current", "create_snapshot", "risk_recovery"}:
        _finish_error(db, event, "invalid_transition", "archived records require a restore event before becoming active")
        raise IngestionError(409, "invalid_transition", "archived records require a restore event before becoming active")

    created = record is None
    if created:
        record = KnowledgeRecord(
            source_system=envelope.source_system, source_record_id=envelope.source_record_id,
            record_type=envelope.record_type, record_mode=mode, business_key=key,
            source_version=envelope.source_version, status="active",
            effective_at=envelope.effective_at.astimezone(timezone.utc),
            source_updated_at=envelope.source_updated_at.astimezone(timezone.utc),
            source_url=str(envelope.source_url) if envelope.source_url else None,
            business_date=business_date, is_mock=envelope.is_mock, payload_json=payload,
            content_hash=content_hash, target_knowledge_base=target,
        )
        db.add(record)
        db.flush()
    else:
        record.source_record_id = envelope.source_record_id
        record.source_version = envelope.source_version
        record.effective_at = envelope.effective_at.astimezone(timezone.utc)
        record.source_updated_at = envelope.source_updated_at.astimezone(timezone.utc)
        record.source_url = str(envelope.source_url) if envelope.source_url else None
        record.is_mock = envelope.is_mock
        if envelope.event_type != "archive":
            record.payload_json = payload
            record.content_hash = content_hash

    operation = "upsert"
    if envelope.event_type == "archive":
        record.status = "archived"
        operation = "archive"
        decision = "archived"
    elif envelope.event_type == "restore":
        record.status = "active"
        operation = "restore"
        decision = "restored"
    elif envelope.event_type == "risk_recovery":
        record.status = "active"
        decision = "risk_recovered"
    else:
        record.status = "active"
        decision = "created" if created else "updated"

    try:
        record.retrieval_text = generate_retrieval_text(record)
    except TextQualityError as exc:
        # The event and record are still in the current transaction.  Raising
        # here (instead of committing an error event) rolls both back, so a
        # rejected value cannot remain in the primary store or be synced.
        raise IngestionError(422, "text_quality_invalid", str(exc)) from exc
    if encoding_corruption(record.retrieval_text):
        raise IngestionError(
            422,
            "text_quality_invalid",
            "retrieval text contains obvious encoding corruption",
        )
    if envelope.record_type in RISK_RECORD_TYPES and mode == "current" and envelope.event_type != "archive":
        _update_risk(db, envelope, record, payload)
    task = RagSyncTask(record_id=record.id, source_version=record.source_version, operation=operation)
    db.add(task)
    event.decision = decision
    event.record_id = record.id
    event.completed_at = utc_now()
    db.commit()
    return {"decision": decision, "record_id": record.id, "source_version": envelope.source_version, "sync_status": task.status}, 201 if created else 200


def ingest(db: Session, envelope: IngestionEnvelope, endpoint: str) -> tuple[dict[str, Any], int]:
    try:
        return _ingest_once(db, envelope, endpoint)
    except IntegrityError:
        # A concurrent request may win a database uniqueness race after our
        # initial reads. Re-run the normal decision flow against committed state.
        db.rollback()
        try:
            return _ingest_once(db, envelope, endpoint)
        except IntegrityError as exc:
            db.rollback()
            raise IngestionError(409, "concurrent_write_conflict", "Concurrent write could not be resolved") from exc
