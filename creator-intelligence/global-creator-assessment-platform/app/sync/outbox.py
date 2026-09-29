from datetime import date, datetime
from enum import Enum
from typing import Literal

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import SyncEvent


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_entity(entity) -> dict:
    mapper = inspect(entity).mapper
    return {
        column.key: _json_value(getattr(entity, column.key))
        for column in mapper.column_attrs
        if column.key not in {"id"}
    }


def record_mutation(
    session: Session,
    entity,
    operation: Literal["upsert", "delete"],
) -> SyncEvent:
    sync_id = getattr(entity, "sync_id")
    event = SyncEvent(
        entity_type=entity.__tablename__.rstrip("s"),
        entity_id=sync_id,
        operation=operation,
        version=getattr(entity, "version", 1),
        changed_by_device=getattr(entity, "updated_by_device"),
        payload=serialize_entity(entity),
    )
    session.add(event)
    return event
