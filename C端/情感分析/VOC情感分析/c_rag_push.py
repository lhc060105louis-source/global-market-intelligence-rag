"""将共享六维聚合结果推送到 Global RAG Hub。

本模块是六维聚合层的下游适配器。它只处理：

* 桶级六维结果到 RAG ingestion envelope 的映射；
* source version、幂等、风险恢复状态；
* HTTP 发送、失败入队和有限重试。

分桶、时间窗口、情感比例、投诉、NPS 和风险计算全部由
``six_dimension_service.py`` 负责。
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RAG_INGESTION_PATH = "/api/v1/ingestion/c"
RISK_RECORD_TYPES = {"consumer_recall_risk", "consumer_legal_risk"}
DIMENSION_RECORD_TYPES = (
    ("consumer_journey_sentiment", "journey_sentiment"),
    ("consumer_nps_prediction", "nps_prediction"),
    ("consumer_key_complaints", "key_complaints"),
    ("consumer_brand_attitude", "brand_attitude"),
    ("consumer_recall_risk", "recall_risk"),
    ("consumer_legal_risk", "legal_risk"),
)
SNAPSHOT_MODES = {"off", "historical", "always", "explicit"}
STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS c_rag_push_state (
    source_record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    last_source_version INTEGER NOT NULL,
    last_threshold_exceeded INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
)
"""
QUEUE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS c_rag_push_queue (
    push_id TEXT PRIMARY KEY,
    job_id INTEGER NOT NULL,
    record_type TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    envelope_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

Sender = Callable[[str, str, dict[str, Any], float], dict[str, Any]]


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    return _truthy(os.getenv("C_RAG_PUSH_ENABLED"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_state_table(conn) -> None:
    conn.execute(STATE_TABLE_SQL)
    conn.commit()


def _ensure_queue_table(conn) -> None:
    conn.execute(QUEUE_TABLE_SQL)
    conn.commit()


def _last_threshold_exceeded(conn, source_record_id: str) -> bool:
    _ensure_state_table(conn)
    row = conn.execute(
        "SELECT last_threshold_exceeded FROM c_rag_push_state WHERE source_record_id = ?",
        (source_record_id,),
    ).fetchone()
    return bool(row and int(row["last_threshold_exceeded"]))


def _retry_delay(attempt_count: int) -> int:
    base = max(1, int(os.getenv("C_RAG_RETRY_INTERVAL_SECONDS", "60")))
    max_delay = max(base, int(os.getenv("C_RAG_RETRY_MAX_INTERVAL_SECONDS", "900")))
    return min(max_delay, base * (2 ** max(0, attempt_count - 1)))


def _source_record_id(bucket: dict[str, Any], dimension: str) -> str:
    return f"{bucket['scope_id']}:{dimension}"


def _bucket_business_date(bucket: dict[str, Any]) -> date | None:
    value = bucket.get("business_date")
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _should_create_snapshot(
    bucket: dict[str, Any], *, mode: str, cutoff_date: date | None = None,
) -> bool:
    if mode == "off":
        return False
    if mode == "explicit":
        return bucket.get("create_snapshot") is True
    business_date = _bucket_business_date(bucket)
    if business_date is None:
        return False
    if mode == "always":
        return True
    # A completed bucket whose business date is before the local business day
    # is eligible for a historical copy.  The current record is still sent as
    # well; this is a second, date-keyed snapshot rather than a move.
    resolved_cutoff = cutoff_date or datetime.now(timezone(timedelta(hours=8))).date()
    return business_date < resolved_cutoff


def _envelope(
    *,
    conn,
    bucket: dict[str, Any],
    record_type: str,
    dimension: str,
    event_type: str | None = None,
) -> dict[str, Any]:
    """把一个桶的一个已计算维度映射成 RAG Hub contract。"""
    payload = bucket["dimensions"][dimension]
    source_record_id = _source_record_id(bucket, dimension)
    resolved_event_type = event_type or "update_current"
    if resolved_event_type == "update_current" and record_type in RISK_RECORD_TYPES:
        exceeded = bool((payload.get("result") or {}).get("threshold_exceeded"))
        if not exceeded and _last_threshold_exceeded(conn, source_record_id):
            resolved_event_type = "risk_recovery"

    source_version = int(bucket["source_version"])
    push_id = f"c-voc-rag:{source_record_id}:v{source_version}"
    if resolved_event_type == "create_snapshot":
        snapshot_date = _bucket_business_date(bucket)
        if snapshot_date is None:
            raise ValueError(f"bucket {bucket.get('scope_id', '<unknown>')} has no valid business_date for snapshot")
        # The event type and date are part of the identity.  A current update
        # and its historical snapshot must never collide on push_id.
        push_id = f"c-voc-rag:{source_record_id}:snapshot:{snapshot_date.isoformat()}:v{source_version}"
    return {
        "source_system": "C",
        "source_record_id": source_record_id,
        "record_type": record_type,
        "event_type": resolved_event_type,
        "source_version": source_version,
        "effective_at": bucket["period_end"],
        "source_updated_at": bucket["source_updated_at"],
        "source_url": bucket.get("source_url"),
        "push_id": push_id,
        "is_mock": False,
        "payload": payload,
    }


def build_c_rag_envelopes(
    conn,
    bucket_results: list[dict[str, Any]],
    *,
    snapshot_mode: str = "off",
    snapshot_cutoff_date: date | None = None,
) -> list[dict[str, Any]]:
    """只消费桶级六维结果，生成当前 envelope 和可选历史快照 envelope。

    注意：这里没有 ``analysis_events``、SQL 查询、分桶或六维公式。
    """
    if snapshot_mode not in SNAPSHOT_MODES:
        raise ValueError(f"unsupported snapshot_mode: {snapshot_mode}")
    envelopes: list[dict[str, Any]] = []
    for bucket in bucket_results:
        dimensions = bucket.get("dimensions") or {}
        missing = [dimension for _, dimension in DIMENSION_RECORD_TYPES if dimension not in dimensions]
        if missing:
            raise ValueError(f"bucket {bucket.get('scope_id', '<unknown>')} is missing dimensions: {', '.join(missing)}")
        for record_type, dimension in DIMENSION_RECORD_TYPES:
            envelopes.append(
                _envelope(
                    conn=conn,
                    bucket=bucket,
                    record_type=record_type,
                    dimension=dimension,
                )
            )
            if _should_create_snapshot(
                bucket, mode=snapshot_mode, cutoff_date=snapshot_cutoff_date,
            ):
                envelopes.append(
                    _envelope(
                        conn=conn,
                        bucket=bucket,
                        record_type=record_type,
                        dimension=dimension,
                        event_type="create_snapshot",
                    )
                )
    return envelopes


def _post_json(base_url: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        base_url.rstrip("/") + RAG_INGESTION_PATH,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            return {"status_code": response.status, "body": body}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"RAG Hub HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"RAG Hub connection failed: {exc}") from exc


def _record_success(conn, envelope: dict[str, Any]) -> None:
    # Snapshot risk rows are historical evidence only.  They must not change
    # the current risk state used to decide whether a future recovery event is
    # needed.
    if envelope["event_type"] == "create_snapshot":
        return
    if envelope["record_type"] not in RISK_RECORD_TYPES:
        return
    _ensure_state_table(conn)
    threshold_exceeded = bool(envelope["payload"]["result"].get("threshold_exceeded"))
    if envelope["event_type"] == "risk_recovery":
        threshold_exceeded = False
    conn.execute(
        """
        INSERT INTO c_rag_push_state(
            source_record_id, record_type, last_source_version,
            last_threshold_exceeded, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_record_id) DO UPDATE SET
            record_type = excluded.record_type,
            last_source_version = excluded.last_source_version,
            last_threshold_exceeded = excluded.last_threshold_exceeded,
            updated_at = excluded.updated_at
        """,
        (
            envelope["source_record_id"],
            envelope["record_type"],
            int(envelope["source_version"]),
            1 if threshold_exceeded else 0,
            _now_iso(),
        ),
    )
    conn.commit()


def _enqueue_retry(conn, job_id: int, envelope: dict[str, Any], error: str) -> None:
    _ensure_queue_table(conn)
    now = _now_iso()
    next_attempt_at = (
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=_retry_delay(1))
    ).isoformat()
    conn.execute(
        """
        INSERT INTO c_rag_push_queue(
            push_id, job_id, record_type, source_record_id, source_version,
            envelope_json, status, attempt_count, next_attempt_at,
            last_error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
        ON CONFLICT(push_id) DO UPDATE SET
            envelope_json = excluded.envelope_json,
            status = 'pending',
            next_attempt_at = excluded.next_attempt_at,
            last_error = excluded.last_error,
            updated_at = excluded.updated_at
        """,
        (
            envelope["push_id"],
            job_id,
            envelope["record_type"],
            envelope["source_record_id"],
            int(envelope["source_version"]),
            json.dumps(envelope, ensure_ascii=False),
            next_attempt_at,
            error,
            now,
            now,
        ),
    )
    conn.commit()


def _mark_retry_success(conn, push_id: str) -> None:
    _ensure_queue_table(conn)
    conn.execute(
        "UPDATE c_rag_push_queue SET status = 'completed', last_error = NULL, updated_at = ? WHERE push_id = ?",
        (_now_iso(), push_id),
    )
    conn.commit()


def _mark_retry_failure(conn, push_id: str, attempt_count: int, error: str) -> None:
    _ensure_queue_table(conn)
    next_attempt_at = (
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=_retry_delay(attempt_count + 1))
    ).isoformat()
    conn.execute(
        """
        UPDATE c_rag_push_queue
        SET status = 'pending', attempt_count = ?, next_attempt_at = ?,
            last_error = ?, updated_at = ?
        WHERE push_id = ?
        """,
        (attempt_count + 1, next_attempt_at, error, _now_iso(), push_id),
    )
    conn.commit()


def push_bucket_results_to_rag(
    conn,
    bucket_results: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
    timeout: float = 15.0,
    sender: Sender | None = None,
    snapshot_mode: str = "off",
    snapshot_cutoff_date: date | None = None,
) -> dict[str, Any]:
    """发送已经完成六维聚合的桶结果及可选历史快照。"""
    if not base_url:
        raise ValueError("RAG_HUB_URL is required when C_RAG_PUSH_ENABLED=true")
    if not api_key:
        raise ValueError("RAG_HUB_API_KEY is required when C_RAG_PUSH_ENABLED=true")
    sender = sender or _post_json
    job_ids = {int(bucket["job_id"]) for bucket in bucket_results if bucket.get("job_id") is not None}
    job_id = next(iter(job_ids), 0) if len(job_ids) == 1 else 0
    envelopes = build_c_rag_envelopes(
        conn,
        bucket_results,
        snapshot_mode=snapshot_mode,
        snapshot_cutoff_date=snapshot_cutoff_date,
    )
    summary: dict[str, Any] = {"job_id": job_id, "total": len(envelopes), "succeeded": 0, "failed": 0, "items": []}
    for envelope in envelopes:
        item = {
            "record_type": envelope["record_type"],
            "source_record_id": envelope["source_record_id"],
            "event_type": envelope["event_type"],
            "source_version": envelope["source_version"],
        }
        try:
            response = sender(base_url, api_key, envelope, timeout)
            item["status"] = "completed"
            item["response"] = response
            _record_success(conn, envelope)
            summary["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001 - best-effort integration boundary
            item["status"] = "failed"
            item["error"] = str(exc)
            _enqueue_retry(conn, int(envelope.get("job_id") or job_id), envelope, str(exc))
            summary["failed"] += 1
        summary["items"].append(item)
    return summary


def process_pending_rag_retries(
    conn,
    *,
    base_url: str,
    api_key: str,
    timeout: float = 15.0,
    limit: int = 20,
    sender: Sender | None = None,
) -> dict[str, Any]:
    if not base_url:
        raise ValueError("RAG_HUB_URL is required when C_RAG_PUSH_ENABLED=true")
    if not api_key:
        raise ValueError("RAG_HUB_API_KEY is required when C_RAG_PUSH_ENABLED=true")
    _ensure_queue_table(conn)
    sender = sender or _post_json
    rows = conn.execute(
        """
        SELECT * FROM c_rag_push_queue
        WHERE status = 'pending' AND next_attempt_at <= ?
        ORDER BY next_attempt_at, created_at
        LIMIT ?
        """,
        (_now_iso(), max(1, limit)),
    ).fetchall()
    summary: dict[str, Any] = {"total": len(rows), "succeeded": 0, "failed": 0, "items": []}
    for row in rows:
        envelope = json.loads(row["envelope_json"])
        item = {
            "job_id": int(row["job_id"]),
            "push_id": row["push_id"],
            "record_type": row["record_type"],
            "attempt_count": int(row["attempt_count"]) + 1,
        }
        try:
            response = sender(base_url, api_key, envelope, timeout)
            _record_success(conn, envelope)
            _mark_retry_success(conn, row["push_id"])
            item["status"] = "completed"
            item["response"] = response
            summary["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001 - keep retry loop alive
            _mark_retry_failure(conn, row["push_id"], int(row["attempt_count"]), str(exc))
            item["status"] = "failed"
            item["error"] = str(exc)
            summary["failed"] += 1
        summary["items"].append(item)
    return summary


def process_pending_rag_retries_from_env(conn, *, limit: int | None = None) -> dict[str, Any]:
    return process_pending_rag_retries(
        conn,
        base_url=os.getenv("RAG_HUB_URL", "http://127.0.0.1:8000").rstrip("/"),
        api_key=os.getenv("RAG_HUB_API_KEY", ""),
        timeout=float(os.getenv("C_RAG_PUSH_TIMEOUT_SECONDS", "15")),
        limit=limit or int(os.getenv("C_RAG_RETRY_BATCH_SIZE", "20")),
    )


def push_bucket_results_to_rag_from_env(
    conn,
    bucket_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return push_bucket_results_to_rag(
        conn,
        bucket_results,
        base_url=os.getenv("RAG_HUB_URL", "http://127.0.0.1:8000").rstrip("/"),
        api_key=os.getenv("RAG_HUB_API_KEY", ""),
        timeout=float(os.getenv("C_RAG_PUSH_TIMEOUT_SECONDS", "15")),
        snapshot_mode=(os.getenv("C_RAG_SNAPSHOT_MODE", "historical") or "historical").strip().lower(),
    )
