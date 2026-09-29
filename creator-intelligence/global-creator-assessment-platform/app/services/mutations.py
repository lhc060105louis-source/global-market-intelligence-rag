from typing import Literal

from sqlalchemy.orm import Session

from app.sync.outbox import record_mutation


def persist_mutation(
    session: Session,
    entity,
    operation: Literal["upsert", "delete"] = "upsert",
):
    session.add(entity)
    session.flush()
    entity.version = int(getattr(entity, "version", 0) or 0) + (
        0 if entity.version == 1 else 1
    )
    return record_mutation(session, entity, operation)
