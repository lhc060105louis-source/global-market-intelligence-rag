"""Workflow helpers shared by online collection, scheduling, and future APIs."""

from __future__ import annotations

import json

from typing import Any, Callable, Iterable

from source_pipeline import (
    analyze_cleaned_items,
    clean_raw_items,
    finish_job,
    insert_raw_items,
    log_job_event,
    push_rag_after_analysis_if_enabled,
    set_job_status,
    start_job,
    update_daily_metrics,
)


Collector = Callable[[], list[dict[str, Any]]]


def explain_error(exc: Exception) -> str:
    message = str(exc)
    if "WinError 10061" in message:
        return f"{message}; the connection was refused. Check the network, proxy, or local forwarding service."
    if "YOUTUBE_API_KEY" in message:
        return f"{message}; YouTube collection requires a valid YOUTUBE_API_KEY."
    return message


def run_online_crawl_job(
    conn,
    *,
    sources: list[str],
    config: dict[str, Any],
    collectors: Iterable[tuple[str, Collector]],
    analyze: bool = True,
    analysis_limit: int | None = None,
    analyze_func: Any | None = None,
) -> dict[str, Any]:
    job_id = start_job(conn, sources, job_type="online_crawl", config={**config, "auto_analyze": analyze})
    return execute_online_crawl_job(
        conn,
        job_id,
        collectors=collectors,
        analyze=analyze,
        analysis_limit=analysis_limit,
        analyze_func=analyze_func,
    )


def execute_online_crawl_job(
    conn,
    job_id: int,
    *,
    collectors: Iterable[tuple[str, Collector]],
    analyze: bool = True,
    analysis_limit: int | None = None,
    analyze_func: Any | None = None,
) -> dict[str, Any]:
    job = conn.execute("SELECT sources FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise ValueError(f"Task #{job_id} does not exist.")
    try:
        sources = list(job["sources"] and json.loads(job["sources"]) or [])
    except Exception:
        sources = []
    set_job_status(conn, job_id, "running", step="job_started", message="Online collection started")
    raw_inserted = 0
    raw_duplicates = 0
    cleaned_count = 0
    analyzed_count = 0
    collected: list[dict[str, Any]] = []
    source_errors: list[str] = []

    try:
        for step, collector in collectors:
            try:
                log_job_event(conn, job_id, step, "running")
                rows = collector()
                collected.extend(rows)
                log_job_event(conn, job_id, step, "completed", None, {"collected": len(rows)})
            except Exception as exc:
                explained = explain_error(exc)
                source_errors.append(f"{step}: {explained}")
                log_job_event(conn, job_id, step, "failed", explained)

        if not collected:
            raise RuntimeError("; ".join(source_errors) or "No source data was collected.")

        raw_ids, raw_duplicates = insert_raw_items(conn, job_id, collected)
        raw_inserted = len(raw_ids)
        log_job_event(conn, job_id, "raw_items", "completed", None, {"inserted": raw_inserted, "duplicates": raw_duplicates})
        cleaned_count = clean_raw_items(conn, raw_ids)
        log_job_event(conn, job_id, "cleaned_items", "completed", None, {"cleaned": cleaned_count})
        if analyze:
            analyzed_count = analyze_cleaned_items(conn, job_id, limit=analysis_limit, analyze_func=analyze_func)
            log_job_event(conn, job_id, "analysis_results", "completed", None, {"analyzed": analyzed_count})
            push_rag_after_analysis_if_enabled(conn, job_id)
        update_daily_metrics(conn)
        finish_job(
            conn,
            job_id,
            status="partial_failed" if source_errors else "completed",
            raw_inserted=raw_inserted,
            raw_duplicates=raw_duplicates,
            cleaned_count=cleaned_count,
            analyzed_count=analyzed_count,
            failed_count=len(source_errors),
            error="; ".join(source_errors) if source_errors else None,
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
            failed_count=max(1, len(source_errors)),
            error=str(exc),
        )
        raise

    return {
        "job_id": job_id,
        "sources": sources,
        "raw_inserted": raw_inserted,
        "raw_duplicates": raw_duplicates,
        "cleaned_count": cleaned_count,
        "analyzed_count": analyzed_count,
        "failed_count": len(source_errors),
        "source_errors": source_errors,
    }
