#!/usr/bin/env python
"""Real-source collection pipeline for the VOC analyzer."""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from voc_analyzer import analyze_voc_rows, read_csv_rows, read_xlsx_rows


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "work" / "voc_pipeline.sqlite3"

JOB_TYPES = {"file_import", "online_crawl"}
JOB_STATUSES = {"queued", "running", "completed", "partial_failed", "failed"}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS collection_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL DEFAULT 'online_crawl',
    source TEXT NOT NULL DEFAULT 'unknown',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    sources TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    total_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    raw_inserted INTEGER NOT NULL DEFAULT 0,
    raw_duplicates INTEGER NOT NULL DEFAULT 0,
    cleaned_count INTEGER NOT NULL DEFAULT 0,
    analyzed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    error_message TEXT,
    last_run_at TEXT,
    next_run_at TEXT
);

CREATE TABLE IF NOT EXISTS job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES collection_jobs(id)
);

CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    published_at TEXT NOT NULL,
    language TEXT NOT NULL,
    title TEXT,
    text TEXT NOT NULL,
    source_url TEXT,
    content_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS cleaned_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_item_id INTEGER NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    published_at TEXT NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    source_url TEXT,
    cleaned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cleaned_item_id INTEGER NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    sentiment_label TEXT,
    published_date TEXT,
    result_json TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_source_metrics (
    metric_date TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_count INTEGER NOT NULL DEFAULT 0,
    cleaned_count INTEGER NOT NULL DEFAULT 0,
    analyzed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(metric_date, source)
);
"""

COLLECTION_JOB_COLUMNS: dict[str, str] = {
    "job_type": "TEXT NOT NULL DEFAULT 'online_crawl'",
    "source": "TEXT NOT NULL DEFAULT 'unknown'",
    "config": "TEXT NOT NULL DEFAULT '{}'",
    "total_count": "INTEGER NOT NULL DEFAULT 0",
    "new_count": "INTEGER NOT NULL DEFAULT 0",
    "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
    "error_message": "TEXT",
    "last_run_at": "TEXT",
    "next_run_at": "TEXT",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_hash(*parts: str) -> str:
    joined = "|".join(part.strip() for part in parts if part)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return html.unescape(re.sub(r"\s+", " ", without_tags)).strip()


def normalize_text(value: str) -> str:
    text = strip_html(value)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def guess_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "Chinese"
    return "EN"


def simple_source_name(value: str) -> str:
    text = str(value or "").strip().lower()
    if "youtube" in text:
        return "youtube"
    if "autohome" in text:
        return "autohome"
    if text in {"csv", "xlsx"}:
        return text
    return text or "unknown"


def published_date(value: str) -> str:
    if not value:
        return "unknown"
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if match:
        return match.group(0)
    return value[:10]


def normalize_published_at(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        serial = int(float(text))
        if 20_000 <= serial <= 80_000:
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()
    return text or "unknown"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(collection_jobs)").fetchall()
    }
    for column, definition in COLLECTION_JOB_COLUMNS.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE collection_jobs ADD COLUMN {column} {definition}")
    conn.commit()


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def normalize_job_source(sources: list[str], source: str | None = None) -> str:
    if source:
        return source
    if len(sources) == 1:
        return sources[0]
    if not sources:
        return "unknown"
    return "mixed"


def log_job_event(
    conn: sqlite3.Connection,
    job_id: int,
    step: str,
    status: str,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO job_logs(job_id, step, status, message, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            step,
            status,
            message,
            json.dumps(payload or {}, ensure_ascii=False),
            utc_now(),
        ),
    )
    conn.commit()


def set_job_status(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    *,
    step: str = "job_status",
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if status not in JOB_STATUSES:
        raise ValueError(f"Unsupported job status: {status}")
    conn.execute(
        """
        UPDATE collection_jobs
        SET status = ?, last_run_at = CASE WHEN ? = 'running' THEN ? ELSE last_run_at END
        WHERE id = ?
        """,
        (status, status, utc_now(), job_id),
    )
    conn.commit()
    log_job_event(conn, job_id, step, status, message, payload)


def start_job(
    conn: sqlite3.Connection,
    sources: list[str],
    *,
    job_type: str = "online_crawl",
    source: str | None = None,
    status: str = "running",
    config: dict[str, Any] | None = None,
) -> int:
    if job_type not in JOB_TYPES:
        raise ValueError(f"Unsupported job_type: {job_type}")
    if status not in JOB_STATUSES:
        raise ValueError(f"Unsupported job status: {status}")
    resolved_source = normalize_job_source(sources, source)
    cursor = conn.execute(
        """
        INSERT INTO collection_jobs(job_type, source, started_at, status, sources, config, last_run_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_type,
            resolved_source,
            utc_now(),
            status,
            json.dumps(sources, ensure_ascii=False),
            json.dumps(config or {}, ensure_ascii=False),
            utc_now() if status == "running" else None,
        ),
    )
    conn.commit()
    job_id = int(cursor.lastrowid)
    log_job_event(
        conn,
        job_id,
        "job_created",
        status,
        f"{job_type} job created for {resolved_source}",
        {"sources": sources, "config": config or {}},
    )
    return job_id


def finish_job(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    status: str,
    raw_inserted: int,
    raw_duplicates: int,
    cleaned_count: int,
    analyzed_count: int,
    failed_count: int,
    error: str | None = None,
) -> None:
    if status not in JOB_STATUSES:
        raise ValueError(f"Unsupported job status: {status}")
    conn.execute(
        """
        UPDATE collection_jobs
        SET completed_at = ?, status = ?, total_count = ?, new_count = ?,
            duplicate_count = ?, raw_inserted = ?, raw_duplicates = ?,
            cleaned_count = ?, analyzed_count = ?, failed_count = ?,
            error = ?, error_message = ?
        WHERE id = ?
        """,
        (
            utc_now(),
            status,
            raw_inserted + raw_duplicates + failed_count,
            raw_inserted,
            raw_duplicates,
            raw_inserted,
            raw_duplicates,
            cleaned_count,
            analyzed_count,
            failed_count,
            error,
            error,
            job_id,
        ),
    )
    conn.commit()
    log_job_event(
        conn,
        job_id,
        "job_finished",
        status,
        error,
        {
            "raw_inserted": raw_inserted,
            "raw_duplicates": raw_duplicates,
            "cleaned_count": cleaned_count,
            "analyzed_count": analyzed_count,
            "failed_count": failed_count,
        },
    )


def push_rag_after_analysis_if_enabled(conn: sqlite3.Connection, job_id: int, *, force: bool = False) -> dict[str, Any] | None:
    try:
        from c_rag_push import is_enabled, push_bucket_results_to_rag_from_env
        from six_dimension_service import build_job_bucket_six_dimensions

        if not force and not is_enabled():
            return None
        log_job_event(conn, job_id, "rag_hub_push", "running", "Pushing C-end six-dimension results to RAG Hub")
        bucket_results = build_job_bucket_six_dimensions(conn, job_id)
        result = push_bucket_results_to_rag_from_env(conn, bucket_results)
        status = "completed" if int(result.get("failed", 0)) == 0 else "failed"
        log_job_event(
            conn,
            job_id,
            "rag_hub_push",
            status,
            None if status == "completed" else "Some RAG Hub push items failed",
            result,
        )
        return result
    except Exception as exc:  # noqa: BLE001 - RAG push must not fail VOC analysis
        log_job_event(conn, job_id, "rag_hub_push", "failed", str(exc))
        return {"job_id": job_id, "failed": 1, "error": str(exc)}


def process_pending_rag_retries_if_enabled(conn: sqlite3.Connection, *, force: bool = False) -> dict[str, Any] | None:
    try:
        from c_rag_push import is_enabled, process_pending_rag_retries_from_env

        if not force and not is_enabled():
            return None
        result = process_pending_rag_retries_from_env(conn)
        for item in result.get("items", []):
            job_id = int(item.get("job_id") or 0)
            if not job_id:
                continue
            status = "completed" if item.get("status") == "completed" else "failed"
            log_job_event(
                conn,
                job_id,
                "rag_hub_auto_retry",
                status,
                item.get("error"),
                item,
            )
        return result
    except Exception:
        return None


def insert_raw_items(conn: sqlite3.Connection, job_id: int, items: Iterable[dict[str, Any]]) -> tuple[list[int], int]:
    inserted_ids: list[int] = []
    duplicates = 0
    for item in items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        source = str(item.get("source") or "unknown").strip()
        source_id = str(item.get("source_id") or source_hash(source, text)).strip()
        row = {
            "job_id": job_id,
            "source": source,
            "source_id": source_id,
            "channel": str(item.get("channel") or "other").strip(),
            "published_at": str(item.get("published_at") or "unknown").strip(),
            "language": str(item.get("language") or guess_language(text)).strip(),
            "title": str(item.get("title") or "").strip(),
            "text": text,
            "source_url": str(item.get("source_url") or "").strip(),
            "content_hash": source_hash(source, source_id, text),
            "raw_json": json.dumps(item, ensure_ascii=False),
            "created_at": utc_now(),
        }
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO raw_items(
                job_id, source, source_id, channel, published_at, language, title,
                text, source_url, content_hash, raw_json, created_at
            )
            VALUES (
                :job_id, :source, :source_id, :channel, :published_at, :language, :title,
                :text, :source_url, :content_hash, :raw_json, :created_at
            )
            """,
            row,
        )
        if cursor.rowcount:
            inserted_ids.append(int(cursor.lastrowid))
        else:
            duplicates += 1
    conn.commit()
    return inserted_ids, duplicates


def value_from_payload(payload: dict[str, Any], field: str, default: str = "") -> str:
    value = payload.get(field)
    if value not in (None, ""):
        return str(value)
    nested = payload.get("raw")
    if isinstance(nested, dict):
        value = nested.get(field)
        if value not in (None, ""):
            return str(value)
    return default


def file_source_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    raise ValueError("Only CSV and XLSX files are supported for VOC file import.")


def read_import_rows(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_rows(path)
    if suffix == ".xlsx":
        return read_xlsx_rows(path)
    raise ValueError("Only CSV and XLSX files are supported for VOC file import.")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_existing_file_import_job(conn: sqlite3.Connection, file_hash: str) -> sqlite3.Row | None:
    rows = conn.execute(
        """
        SELECT *
        FROM collection_jobs
        WHERE job_type = 'file_import'
          AND status IN ('completed', 'partial_failed')
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        try:
            config = json.loads(row["config"] or "{}")
        except json.JSONDecodeError:
            continue
        stored_hash = config.get("file_hash")
        if not stored_hash and config.get("path"):
            legacy_path = Path(str(config["path"]))
            if legacy_path.is_file():
                stored_hash = file_sha256(legacy_path)
        if stored_hash == file_hash:
            return row
    return None


def analyze_job(conn: sqlite3.Connection, job_id: int, analyze_func: Any | None = None) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise ValueError(f"Task #{job_id} does not exist.")
    if job["status"] in {"queued", "running"}:
        raise ValueError("The task is still running and cannot be analyzed yet.")

    pending_count = len(rows_for_analysis(conn, job_id))
    if pending_count == 0:
        return {
            "job_id": job_id,
            "analyzed_now": 0,
            "analyzed_count": int(job["analyzed_count"]),
            "message": "No pending cleaned data to analyze.",
        }

    set_job_status(conn, job_id, "running", step="manual_analysis", message=f"Analyzing {pending_count} cleaned items")
    try:
        analyzed_now = analyze_cleaned_items(conn, job_id, analyze_func=analyze_func)
        analyzed_total = int(job["analyzed_count"]) + analyzed_now
        conn.execute(
            """
            UPDATE collection_jobs
            SET analyzed_count = ?, status = 'completed', completed_at = ?, error = NULL, error_message = NULL
            WHERE id = ?
            """,
            (analyzed_total, utc_now(), job_id),
        )
        log_job_event(conn, job_id, "manual_analysis", "completed", None, {"analyzed": analyzed_now})
        update_daily_metrics(conn)
        push_rag_after_analysis_if_enabled(conn, job_id)
    except Exception as exc:
        conn.execute(
            """
            UPDATE collection_jobs
            SET status = 'failed', completed_at = ?, error = ?, error_message = ?
            WHERE id = ?
            """,
            (utc_now(), str(exc), str(exc), job_id),
        )
        conn.commit()
        log_job_event(conn, job_id, "manual_analysis", "failed", str(exc))
        raise
    return {
        "job_id": job_id,
        "analyzed_now": analyzed_now,
        "analyzed_count": analyzed_total,
        "message": f"Analyzed {analyzed_now} items.",
    }


def delete_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise ValueError(f"Task #{job_id} does not exist.")
    if job["status"] in {"queued", "running"}:
        raise ValueError("A running task cannot be deleted.")

    raw_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM raw_items WHERE job_id = ?", (job_id,))]
    cleaned_ids: list[int] = []
    if raw_ids:
        placeholders = ",".join("?" for _ in raw_ids)
        cleaned_ids = [
            int(row["id"])
            for row in conn.execute(
                f"SELECT id FROM cleaned_items WHERE raw_item_id IN ({placeholders})",
                raw_ids,
            )
        ]
        if cleaned_ids:
            cleaned_placeholders = ",".join("?" for _ in cleaned_ids)
            conn.execute(
                f"DELETE FROM analysis_results WHERE cleaned_item_id IN ({cleaned_placeholders})",
                cleaned_ids,
            )
        conn.execute(f"DELETE FROM cleaned_items WHERE raw_item_id IN ({placeholders})", raw_ids)
        conn.execute("DELETE FROM raw_items WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM job_logs WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM collection_jobs WHERE id = ?", (job_id,))
    conn.execute("DELETE FROM daily_source_metrics")
    conn.commit()
    update_daily_metrics(conn)
    return {
        "job_id": job_id,
        "deleted": True,
        "raw_deleted": len(raw_ids),
        "cleaned_deleted": len(cleaned_ids),
    }


def standardize_import_row(row: dict[str, str], source: str, row_number: int) -> dict[str, Any] | None:
    text = str(row.get("text") or row.get("ocr_text") or "").strip()
    if not text:
        return None
    source_id = str(row.get("source_id") or "").strip() or source_hash(source, str(row_number), text)
    return {
        "source": source,
        "source_id": source_id,
        "channel": str(row.get("channel") or "other").strip() or "other",
        "published_at": normalize_published_at(row.get("published_at")),
        "language": str(row.get("language") or guess_language(text) or "UNKNOWN").strip() or "UNKNOWN",
        "region": str(row.get("region") or "UNKNOWN").strip() or "UNKNOWN",
        "brand": str(row.get("brand") or "UNKNOWN_BRAND").strip() or "UNKNOWN_BRAND",
        "model": str(row.get("model") or "UNKNOWN_MODEL").strip() or "UNKNOWN_MODEL",
        "title": str(row.get("title") or "").strip(),
        "text": text,
        "source_url": str(row.get("source_url") or "").strip(),
        "raw": {
            "source_platform": source,
            "row_number": row_number,
            "source_record": row,
            "region": str(row.get("region") or "UNKNOWN").strip() or "UNKNOWN",
            "brand": str(row.get("brand") or "UNKNOWN_BRAND").strip() or "UNKNOWN_BRAND",
            "model": str(row.get("model") or "UNKNOWN_MODEL").strip() or "UNKNOWN_MODEL",
            "model_ycode": str(row.get("model_ycode") or "").strip(),
        },
    }


def import_voc_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    analyze: bool = True,
    analysis_limit: int | None = None,
    analyze_func: Any | None = None,
    display_filename: str | None = None,
    dedupe_existing: bool = True,
) -> dict[str, Any]:
    source = file_source_from_path(path)
    file_hash = file_sha256(path)
    if dedupe_existing:
        existing_job = find_existing_file_import_job(conn, file_hash)
        if existing_job is not None:
            try:
                existing_config = json.loads(existing_job["config"] or "{}")
            except json.JSONDecodeError:
                existing_config = {}
            existing_config.update(
                {
                    "filename": display_filename or existing_config.get("filename") or path.name,
                    "file_hash": file_hash,
                }
            )
            conn.execute(
                "UPDATE collection_jobs SET config = ? WHERE id = ?",
                (json.dumps(existing_config, ensure_ascii=False), int(existing_job["id"])),
            )
            conn.commit()
            log_job_event(
                conn,
                int(existing_job["id"]),
                "duplicate_upload",
                "completed",
                f"Duplicate upload reused existing job #{existing_job['id']}",
                {"filename": display_filename or path.name, "file_hash": file_hash},
            )
            analysis_summary = {"analyzed_now": 0, "analyzed_count": int(existing_job["analyzed_count"])}
            if analyze:
                analysis_summary = analyze_job(conn, int(existing_job["id"]), analyze_func=analyze_func)
            return {
                "job_id": int(existing_job["id"]),
                "source": source,
                "raw_inserted": int(existing_job["raw_inserted"]),
                "raw_duplicates": int(existing_job["raw_duplicates"]),
                "cleaned_count": int(existing_job["cleaned_count"]),
                "analyzed_count": int(analysis_summary["analyzed_count"]),
                "failed_count": int(existing_job["failed_count"]),
                "duplicate_upload": True,
                "message": f"Same file already imported as job #{existing_job['id']}.",
            }
    job_id = start_job(
        conn,
        [source],
        job_type="file_import",
        source=source,
        config={
            "filename": display_filename or path.name,
            "stored_filename": path.name,
            "path": str(path),
            "file_hash": file_hash,
            "auto_analyze": analyze,
        },
    )
    raw_inserted = 0
    raw_duplicates = 0
    cleaned_count = 0
    analyzed_count = 0
    skipped_count = 0
    failed_count = 0
    try:
        log_job_event(conn, job_id, "file_read", "running", f"Reading {path.name}")
        rows = read_import_rows(path)
        standardized = []
        for index, row in enumerate(rows, start=1):
            item = standardize_import_row(row, source, index)
            if item is None:
                skipped_count += 1
                continue
            standardized.append(item)
        log_job_event(
            conn,
            job_id,
            "standardize",
            "completed",
            f"Standardized {len(standardized)} rows",
            {"input_rows": len(rows), "skipped_rows": skipped_count},
        )
        raw_ids, raw_duplicates = insert_raw_items(conn, job_id, standardized)
        raw_inserted = len(raw_ids)
        log_job_event(conn, job_id, "raw_items", "completed", None, {"inserted": raw_inserted, "duplicates": raw_duplicates})
        cleaned_count = clean_raw_items(conn, raw_ids)
        log_job_event(conn, job_id, "cleaned_items", "completed", None, {"cleaned": cleaned_count})
        if analyze:
            analyzed_count = analyze_cleaned_items(conn, job_id, limit=analysis_limit, analyze_func=analyze_func)
            log_job_event(conn, job_id, "analysis_results", "completed", None, {"analyzed": analyzed_count})
        update_daily_metrics(conn)
        if analyze:
            push_rag_after_analysis_if_enabled(conn, job_id)
        status = "completed"
        finish_job(
            conn,
            job_id,
            status=status,
            raw_inserted=raw_inserted,
            raw_duplicates=raw_duplicates,
            cleaned_count=cleaned_count,
            analyzed_count=analyzed_count,
            failed_count=failed_count,
            error=None,
        )
    except Exception as exc:
        finish_job(
            conn,
            job_id,
            status="failed",
            raw_inserted=raw_inserted,
            raw_duplicates=raw_duplicates,
            cleaned_count=cleaned_count,
            analyzed_count=analyzed_count,
            failed_count=max(1, failed_count),
            error=str(exc),
        )
        raise
    return {
        "job_id": job_id,
        "source": source,
        "raw_inserted": raw_inserted,
        "raw_duplicates": raw_duplicates,
        "cleaned_count": cleaned_count,
        "analyzed_count": analyzed_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "duplicate_upload": False,
    }


def clean_raw_items(conn: sqlite3.Connection, raw_ids: list[int]) -> int:
    cleaned_count = 0
    for raw_id in raw_ids:
        raw = conn.execute("SELECT * FROM raw_items WHERE id = ?", (raw_id,)).fetchone()
        if not raw:
            continue
        text = normalize_text(str(raw["text"]))
        if len(text) < 3:
            continue
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO cleaned_items(
                raw_item_id, source, source_id, channel, published_at, language,
                text, source_url, cleaned_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw["id"],
                raw["source"],
                raw["source_id"],
                raw["channel"],
                raw["published_at"],
                raw["language"],
                text,
                raw["source_url"],
                utc_now(),
            ),
        )
        cleaned_count += int(bool(cursor.rowcount))
    conn.commit()
    return cleaned_count


def rows_for_analysis(conn: sqlite3.Connection, job_id: int, limit: int | None = None) -> list[dict[str, str]]:
    sql = """
        SELECT c.id AS cleaned_item_id, c.source, c.source_id, c.channel, c.published_at,
               c.language, c.text, c.source_url, r.raw_json
        FROM cleaned_items c
        JOIN raw_items r ON r.id = c.raw_item_id
        LEFT JOIN analysis_results a ON a.cleaned_item_id = c.id
        WHERE r.job_id = ? AND a.id IS NULL
        ORDER BY c.id
    """
    params: list[Any] = [job_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = []
    for row in conn.execute(sql, params):
        raw_payload: dict[str, Any] = {}
        try:
            raw_payload = json.loads(row["raw_json"] or "{}")
        except json.JSONDecodeError:
            raw_payload = {}
        analysis_row = {
            "_cleaned_item_id": str(row["cleaned_item_id"]),
            "source": row["source"],
            "source_id": row["source_id"],
            "channel": row["channel"],
            "published_at": row["published_at"],
            "language": row["language"],
            "source_url": row["source_url"] or "",
            "text": row["text"],
            "review_status": "review_pass",
        }
        for field in ("region", "brand", "model", "model_ycode"):
            value = value_from_payload(raw_payload, field)
            if value:
                analysis_row[field] = value
        rows.append(analysis_row)
    return rows


def cleaned_rows_for_job(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    job = conn.execute("SELECT id, source FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise ValueError(f"Task #{job_id} does not exist.")
    total = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM cleaned_items c
            JOIN raw_items r ON r.id = c.raw_item_id
            WHERE r.job_id = ?
            """,
            (job_id,),
        ).fetchone()[0]
    )
    rows = conn.execute(
        """
        SELECT c.source_id, c.channel, c.published_at, c.language, c.text,
               c.source_url, r.raw_json
        FROM cleaned_items c
        JOIN raw_items r ON r.id = c.raw_item_id
        WHERE r.job_id = ?
        ORDER BY c.id
        LIMIT ? OFFSET ?
        """,
        (job_id, max(1, min(limit, 200)), max(0, offset)),
    ).fetchall()
    items: list[dict[str, str]] = []
    for row in rows:
        try:
            payload = json.loads(row["raw_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        items.append(
            {
                "source_id": row["source_id"],
                "channel": row["channel"],
                "published_at": normalize_published_at(row["published_at"]),
                "language": row["language"],
                "region": value_from_payload(payload, "region", "UNKNOWN") or "UNKNOWN",
                "brand": value_from_payload(payload, "brand", "UNKNOWN_BRAND") or "UNKNOWN_BRAND",
                "model": value_from_payload(payload, "model", "UNKNOWN_MODEL") or "UNKNOWN_MODEL",
                "text": row["text"],
                "source_url": row["source_url"] or "",
            }
        )
    return {
        "job_id": job_id,
        "source": job["source"],
        "total": total,
        "limit": max(1, min(limit, 200)),
        "offset": max(0, offset),
        "items": items,
    }


def analyze_cleaned_items(
    conn: sqlite3.Connection,
    job_id: int,
    limit: int | None = None,
    analyze_func: Any | None = None,
) -> int:
    rows = rows_for_analysis(conn, job_id, limit=limit)
    if not rows:
        return 0

    def progress(done: int, total: int) -> None:
        log_job_event(
            conn,
            job_id,
            "analysis_progress",
            "running",
            f"Analyzed {done}/{total} cleaned items",
            {"done": done, "total": total},
        )

    report = analyze_voc_rows(rows, limit=limit, analyze_func=analyze_func, progress=progress)
    cleaned_by_source_id = {row["source_id"]: row["_cleaned_item_id"] for row in rows}
    analyzed_count = 0
    for event in report.get("standardized_events", []):
        cleaned_item_id = int(cleaned_by_source_id[str(event["source_id"])])
        matching_row = next((row for row in rows if row["_cleaned_item_id"] == str(cleaned_item_id)), {})
        event.setdefault("source", matching_row.get("source", ""))
        event.setdefault("source_url", matching_row.get("source_url", ""))
        event.setdefault("text", matching_row.get("text", ""))
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO analysis_results(
                cleaned_item_id, source, source_id, sentiment_label, published_date,
                result_json, analyzed_at
            )
            SELECT ?, c.source, c.source_id, ?, ?, ?, ?
            FROM cleaned_items c
            WHERE c.id = ?
            """,
            (
                cleaned_item_id,
                event.get("sentiment_label"),
                event.get("published_date"),
                json.dumps(event, ensure_ascii=False),
                utc_now(),
                cleaned_item_id,
            ),
        )
        analyzed_count += int(bool(cursor.rowcount))
    conn.commit()
    return analyzed_count


def update_daily_metrics(conn: sqlite3.Connection) -> None:
    metrics: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"raw": 0, "cleaned": 0, "analyzed": 0})
    for row in conn.execute("SELECT source, published_at, COUNT(*) AS count FROM raw_items GROUP BY source, published_at"):
        metrics[(published_date(row["published_at"]), row["source"])]["raw"] += int(row["count"])
    for row in conn.execute("SELECT source, published_at, COUNT(*) AS count FROM cleaned_items GROUP BY source, published_at"):
        metrics[(published_date(row["published_at"]), row["source"])]["cleaned"] += int(row["count"])
    for row in conn.execute(
        """
        SELECT c.source, c.published_at, COUNT(*) AS count
        FROM analysis_results a
        JOIN cleaned_items c ON c.id = a.cleaned_item_id
        GROUP BY c.source, c.published_at
        """
    ):
        metrics[(published_date(row["published_at"]), row["source"])]["analyzed"] += int(row["count"])

    for (metric_date, source), values in metrics.items():
        conn.execute(
            """
            INSERT INTO daily_source_metrics(
                metric_date, source, raw_count, cleaned_count, analyzed_count, failed_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(metric_date, source) DO UPDATE SET
                raw_count = excluded.raw_count,
                cleaned_count = excluded.cleaned_count,
                analyzed_count = excluded.analyzed_count,
                failed_count = excluded.failed_count,
                updated_at = excluded.updated_at
            """,
            (metric_date, source, values["raw"], values["cleaned"], values["analyzed"], 0, utc_now()),
        )
    conn.commit()


def latest_metrics(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT metric_date, source, raw_count, cleaned_count, analyzed_count, failed_count
        FROM daily_source_metrics
        ORDER BY metric_date DESC, source
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
