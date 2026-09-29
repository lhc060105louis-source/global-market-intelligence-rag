from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KnowledgeRecord, RagSyncTask
from .retrieval_text import generate_retrieval_text


def ensure_resync_task(db: Session, record: KnowledgeRecord) -> tuple[RagSyncTask, bool]:
    operation = "archive" if record.status == "archived" else "upsert"
    task = db.scalar(select(RagSyncTask).where(
        RagSyncTask.record_id == record.id,
        RagSyncTask.source_version == record.source_version,
        RagSyncTask.operation == operation,
    ))
    if task:
        if task.status in {"completed", "failed", "timed_out"}:
            task.status = "pending"
            task.error_code = None
            task.error_message = None
            task.completed_at = None
            task.next_attempt_at = None
        return task, False
    task = RagSyncTask(record_id=record.id, source_version=record.source_version, operation=operation)
    db.add(task)
    return task, True


def rebuild_records(
    db: Session,
    *,
    source_system: str | None = None,
    target_knowledge_base: str | None = None,
) -> dict[str, int]:
    query = select(KnowledgeRecord)
    if source_system:
        query = query.where(KnowledgeRecord.source_system == source_system)
    if target_knowledge_base:
        query = query.where(KnowledgeRecord.target_knowledge_base == target_knowledge_base)
    records = db.scalars(query).all()
    created = 0
    queued = 0
    for record in records:
        record.retrieval_text = generate_retrieval_text(record)
        task, was_created = ensure_resync_task(db, record)
        created += int(was_created)
        queued += int(task.status == "pending")
    return {"records_rebuilt": len(records), "tasks_created": created, "tasks_queued": queued}
