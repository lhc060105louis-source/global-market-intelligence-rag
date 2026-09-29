from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import logging
import threading
from typing import Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .adapters.base import AdapterResult, RAGAdapter
from .models import KnowledgeRecord, RagDocumentMapping, RagSyncTask, utc_now


SessionFactory = Callable[[], Session]
AdapterFactory = Callable[[], RAGAdapter]

_RUN_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def _complete_upsert(db: Session, task: RagSyncTask, record: KnowledgeRecord, external_document_id: str | None) -> None:
    mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == record.id))
    if mapping is None:
        mapping = RagDocumentMapping(
            record_id=record.id,
            target_knowledge_base=record.target_knowledge_base,
            mapped_source_version=record.source_version,
        )
        db.add(mapping)
    mapping.external_document_id = external_document_id or mapping.external_document_id
    mapping.mapped_source_version = task.source_version
    mapping.external_is_active = record.status == "active"
    task.status = "completed"
    task.completed_at = utc_now()
    task.next_attempt_at = None


def _process_task_group(
    *,
    session_factory: SessionFactory,
    adapter_factory: AdapterFactory,
    task_ids: list[str],
    poll_interval_seconds: float,
    max_attempts: int,
) -> dict[str, int]:
    adapter = adapter_factory()
    counts = {"processed": 0, "completed": 0, "processing": 0, "failed": 0, "timed_out": 0}
    with session_factory() as db:
        for task_id in task_ids:
            task = db.get(RagSyncTask, task_id)
            if task is None or task.status not in {"pending", "processing"}:
                continue
            record = db.get(KnowledgeRecord, task.record_id)
            if record is None:
                task.status = "failed"
                task.error_code = "record_missing"
                task.error_message = "Knowledge record no longer exists"
                task.completed_at = utc_now()
                task.next_attempt_at = None
                counts["failed"] += 1
                continue
            if task.source_version < record.source_version:
                task.status = "completed"
                task.completed_at = utc_now()
                task.next_attempt_at = None
                counts["processed"] += 1
                counts["completed"] += 1
                continue
            task.attempt_count += 1
            task.started_at = task.started_at or utc_now()
            counts["processed"] += 1
            if task.external_task_id:
                result = adapter.get_index_status(
                    external_task_id=task.external_task_id,
                    target=record.target_knowledge_base,
                )
            elif task.operation == "archive":
                mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == record.id))
                if mapping is None or mapping.external_document_id is None:
                    task.status = "completed"
                    task.completed_at = utc_now()
                    task.next_attempt_at = None
                    counts["completed"] += 1
                    continue
                result = adapter.set_document_active(
                    external_document_id=mapping.external_document_id,
                    active=False,
                    target=record.target_knowledge_base,
                )
            else:
                result = adapter.upsert_document(
                    target=record.target_knowledge_base,
                    record_id=record.id,
                    source_version=task.source_version,
                    text=record.retrieval_text,
                )
            if result.external_task_id:
                task.external_task_id = result.external_task_id
            if result.status == "failed":
                task.status = "failed"
                task.error_code = result.error_code
                task.error_message = result.error_message
                task.completed_at = utc_now()
                task.next_attempt_at = None
                counts["failed"] += 1
            elif result.status == "processing":
                if result.external_document_id:
                    mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == record.id))
                    if mapping is None:
                        mapping = RagDocumentMapping(
                            record_id=record.id,
                            target_knowledge_base=record.target_knowledge_base,
                            mapped_source_version=task.source_version,
                        )
                        db.add(mapping)
                    mapping.external_document_id = result.external_document_id
                    mapping.external_is_active = record.status == "active"
                if task.attempt_count >= max_attempts:
                    task.status = "timed_out"
                    task.error_code = "adapter_timeout"
                    task.error_message = f"Adapter remained in processing state after {max_attempts} attempts"
                    task.completed_at = utc_now()
                    task.next_attempt_at = None
                    counts["timed_out"] += 1
                else:
                    task.status = "processing"
                    task.next_attempt_at = utc_now() + timedelta(seconds=poll_interval_seconds)
                    counts["processing"] += 1
            elif task.operation == "archive":
                mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == record.id))
                if mapping is not None:
                    mapping.external_is_active = False
                    mapping.mapped_source_version = task.source_version
                task.status = "completed"
                task.completed_at = utc_now()
                task.next_attempt_at = None
                counts["completed"] += 1
            else:
                _complete_upsert(db, task, record, result.external_document_id)
                counts["completed"] += 1
        db.commit()
    return counts


def process_pending_tasks(
    session_factory: SessionFactory,
    adapter_factory: AdapterFactory,
    *,
    max_workers: int,
    batch_size: int,
    poll_interval_seconds: float,
    max_attempts: int,
) -> dict[str, int]:
    with _RUN_LOCK:
        now = utc_now()
        with session_factory() as db:
            rows = db.execute(
                select(RagSyncTask.id, RagSyncTask.record_id)
                .where(RagSyncTask.status.in_(["pending", "processing"]))
                .where(or_(RagSyncTask.next_attempt_at.is_(None), RagSyncTask.next_attempt_at <= now))
                .order_by(RagSyncTask.created_at, RagSyncTask.id)
                .limit(batch_size)
            ).all()
        if not rows:
            return {"processed": 0, "completed": 0, "processing": 0, "failed": 0, "timed_out": 0}

        grouped: dict[str, list[str]] = defaultdict(list)
        for task_id, record_id in rows:
            grouped[str(record_id)].append(str(task_id))

        counts = {"processed": 0, "completed": 0, "processing": 0, "failed": 0, "timed_out": 0}
        worker_total = max(1, min(max_workers, len(grouped)))
        items = list(grouped.values())
        if worker_total == 1:
            results = []
            for task_ids in items:
                try:
                    results.append(
                        _process_task_group(
                            session_factory=session_factory,
                            adapter_factory=adapter_factory,
                            task_ids=task_ids,
                            poll_interval_seconds=poll_interval_seconds,
                            max_attempts=max_attempts,
                        )
                    )
                except Exception:  # pragma: no cover - defensive logging for single-worker sweeps
                    logger.exception("sync task group failed")
        else:
            results = []
            with ThreadPoolExecutor(max_workers=worker_total, thread_name_prefix="rag-sync-task") as executor:
                futures = [
                    executor.submit(
                        _process_task_group,
                        session_factory=session_factory,
                        adapter_factory=adapter_factory,
                        task_ids=task_ids,
                        poll_interval_seconds=poll_interval_seconds,
                        max_attempts=max_attempts,
                    )
                    for task_ids in items
                ]
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception:  # pragma: no cover - defensive logging for individual task groups
                        logger.exception("sync task group failed")
        for result in results:
            for key in counts:
                counts[key] += result[key]
        return counts


def recover_timed_out_tasks(session_factory: SessionFactory) -> int:
    """Requeue active current upserts after a service restart.

    A timed-out task means the adapter was still processing when the local
    polling budget ended. It is not the same as a confirmed external failure.
    Only active/current upserts are recovered automatically; archive tasks and
    historical snapshots remain terminal until an explicit maintenance action.
    """
    with session_factory() as db:
        tasks = db.scalars(
            select(RagSyncTask)
            .join(KnowledgeRecord, KnowledgeRecord.id == RagSyncTask.record_id)
            .where(
                RagSyncTask.status == "timed_out",
                RagSyncTask.operation == "upsert",
                KnowledgeRecord.status == "active",
                KnowledgeRecord.record_mode == "current",
            )
        ).all()
        for task in tasks:
            task.status = "processing"
            task.attempt_count = 0
            task.error_code = None
            task.error_message = None
            task.completed_at = None
            task.next_attempt_at = None
        db.commit()
        return len(tasks)


def queue_has_work(session_factory: SessionFactory) -> bool:
    with session_factory() as db:
        return bool(db.scalar(
            select(func.count(RagSyncTask.id)).where(RagSyncTask.status.in_(["pending", "processing"]))
        ))


def sync_summary(db: Session) -> dict[str, dict[str, int]]:
    targets = ["c_current", "c_history", "b_business", "kol"]
    result = {target: {status: 0 for status in ["pending", "processing", "completed", "failed", "timed_out"]} for target in targets}
    rows = db.execute(
        select(KnowledgeRecord.target_knowledge_base, RagSyncTask.status, func.count(RagSyncTask.id))
        .join(RagSyncTask, RagSyncTask.record_id == KnowledgeRecord.id)
        .group_by(KnowledgeRecord.target_knowledge_base, RagSyncTask.status)
    ).all()
    for target, status, count in rows:
        result[target][status] = count
    return result
