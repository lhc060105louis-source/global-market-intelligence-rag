#!/usr/bin/env python
"""Local VOC workbench API and static frontend server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import threading
import tempfile
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from collectors import collect_autohome_owner_reviews, collect_youtube_vehicle_comments
from import_sources import import_voc_file
from insight_service import build_insight_payload
from monitor_service import load_monitor_config, run_monitor_once, save_monitor_config
from source_pipeline import (
    DEFAULT_DB_PATH,
    analyze_job,
    cleaned_rows_for_job,
    connect,
    delete_job,
    process_pending_rag_retries_if_enabled,
    push_rag_after_analysis_if_enabled,
    rows_for_analysis,
    start_job,
)
from workflow_api import execute_online_crawl_job


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"


def load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    loaded_keys: set[str] = set()
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        os.environ[key] = value.strip().strip('"').strip("'")
        loaded_keys.add(key.upper())
    if "ALL_PROXY" not in loaded_keys and os.getenv("HTTPS_PROXY"):
        os.environ["ALL_PROXY"] = os.environ["HTTPS_PROXY"]
        os.environ["all_proxy"] = os.environ["HTTPS_PROXY"]


load_local_env()


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        value = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON request body.") from exc
    return value if isinstance(value, dict) else {}


def read_upload_file(handler: BaseHTTPRequestHandler) -> tuple[str, bytes] | None:
    content_type = handler.headers.get("Content-Type", "")
    match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if "multipart/form-data" not in content_type or not match:
        return None
    boundary = match.group("boundary").strip().strip('"')
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length)
    delimiter = ("--" + boundary).encode("utf-8")
    for part in raw.split(delimiter):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip()
        header_blob, separator, body = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        if 'name="file"' not in headers:
            continue
        filename_match = re.search(r'filename="([^"]+)"', headers)
        if not filename_match:
            continue
        if body.endswith(b"\r\n"):
            body = body[:-2]
        return filename_match.group(1), body
    return None


def bool_param(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def task_rows(conn, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, job_type, source, status, sources, config, total_count, new_count,
               duplicate_count, cleaned_count, analyzed_count, failed_count,
               started_at, completed_at, error_message, last_run_at, next_run_at
        FROM collection_jobs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def task_detail(conn, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    logs = conn.execute(
        "SELECT step, status, message, payload, created_at FROM job_logs WHERE job_id = ? ORDER BY id",
        (job_id,),
    ).fetchall()
    return {**dict(row), "logs": [dict(log) for log in logs]}


def parse_filters(query: dict[str, list[str]]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if query.get("job_id", [""])[0]:
        filters["job_id"] = int(query["job_id"][0])
    for key in ("start_date", "end_date", "brand", "model", "region", "channel"):
        value = query.get(key, [""])[0]
        if value:
            filters[key] = value
    if query.get("limit", [""])[0]:
        filters["limit"] = int(query["limit"][0])
    return filters


def build_collectors(payload: dict[str, Any]):
    sources = set(payload.get("sources") or [])
    limit = int(payload.get("limit_per_source") or 30)
    keywords = [str(value) for value in payload.get("keywords") or [] if str(value).strip()]
    autohome_urls = [str(value) for value in payload.get("autohome_urls") or [] if str(value).strip()]
    collectors = []
    if "youtube" in sources:
        collectors.append(("collect_youtube", lambda: collect_youtube_vehicle_comments(keywords or None, limit=limit)))
    if "autohome" in sources:
        collectors.append(("collect_autohome", lambda: collect_autohome_owner_reviews(autohome_urls or None, limit=limit)))
    return collectors


def run_background(db_path: Path, target) -> None:
    def worker() -> None:
        conn = connect(db_path)
        try:
            target(conn)
        except Exception:
            # The workflow functions persist task failures in the job log.
            return
        finally:
            conn.close()

    threading.Thread(target=worker, daemon=True).start()


def start_rag_retry_worker(db_path: Path) -> None:
    def worker() -> None:
        while True:
            interval = max(5, int(os.getenv("C_RAG_RETRY_INTERVAL_SECONDS", "60")))
            conn = connect(db_path)
            try:
                process_pending_rag_retries_if_enabled(conn)
            finally:
                conn.close()
            time.sleep(interval)

    threading.Thread(target=worker, name="c-rag-retry", daemon=True).start()


def create_handler(db_path: Path):
    class WorkbenchHandler(BaseHTTPRequestHandler):
        server_version = "VOCWorkbench/1.0"

        def send_json(self, payload: Any, status: int = 200) -> None:
            body = json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_error_json(self, message: str, status: int = 400) -> None:
            self.send_json({"error": message}, status=status)

        def send_static(self, path: str) -> None:
            if path == "/":
                path = "/index.html"
            target = (WEB_ROOT / path.lstrip("/")).resolve()
            if not str(target).startswith(str(WEB_ROOT.resolve())) or not target.exists() or target.is_dir():
                self.send_error_json("Not found.", status=404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            try:
                if parsed.path == "/api/health":
                    self.send_json({"ok": True, "db": str(db_path)})
                    return
                if parsed.path == "/api/tasks":
                    conn = connect(db_path)
                    try:
                        self.send_json({"tasks": task_rows(conn, limit=int(query.get("limit", ["50"])[0]))})
                    finally:
                        conn.close()
                    return
                if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/items"):
                    job_id = int(parsed.path.split("/")[-2])
                    limit = int(query.get("limit", ["50"])[0])
                    offset = int(query.get("offset", ["0"])[0])
                    conn = connect(db_path)
                    try:
                        self.send_json(cleaned_rows_for_job(conn, job_id, limit=limit, offset=offset))
                    finally:
                        conn.close()
                    return
                if parsed.path.startswith("/api/tasks/"):
                    job_id = int(parsed.path.rsplit("/", 1)[-1])
                    conn = connect(db_path)
                    try:
                        detail = task_detail(conn, job_id)
                    finally:
                        conn.close()
                    if detail is None:
                        self.send_error_json("Task not found.", status=404)
                    else:
                        self.send_json(detail)
                    return
                if parsed.path == "/api/insights":
                    conn = connect(db_path)
                    try:
                        self.send_json(build_insight_payload(conn, **parse_filters(query)))
                    finally:
                        conn.close()
                    return
                if parsed.path == "/api/monitor":
                    conn = connect(db_path)
                    try:
                        self.send_json(load_monitor_config(conn))
                    finally:
                        conn.close()
                    return
                if parsed.path.startswith("/api/"):
                    self.send_error_json("API route not found.", status=404)
                    return
                self.send_static(parsed.path)
            except Exception as exc:
                self.send_error_json(str(exc), status=500)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            try:
                if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/analyze"):
                    job_id = int(parsed.path.split("/")[-2])
                    conn = connect(db_path)
                    try:
                        job = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
                        if job is None:
                            self.send_error_json("Task not found.", status=404)
                            return
                        if job["status"] in {"queued", "running"}:
                            self.send_error_json("The task is still running and cannot be analyzed yet.", status=409)
                            return
                        pending_count = len(rows_for_analysis(conn, job_id))
                        if pending_count == 0:
                            self.send_json(
                                {
                                    "job_id": job_id,
                                    "analyzed_now": 0,
                                    "analyzed_count": int(job["analyzed_count"]),
                                    "message": "No pending cleaned data to analyze.",
                                }
                            )
                            return
                    finally:
                        conn.close()
                    run_background(db_path, lambda bg_conn: analyze_job(bg_conn, job_id))
                    self.send_json({"job_id": job_id, "queued": True, "pending_count": pending_count}, status=202)
                    return
                if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/rag-push"):
                    job_id = int(parsed.path.split("/")[-2])
                    conn = connect(db_path)
                    try:
                        job = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
                        if job is None:
                            self.send_error_json("Task not found.", status=404)
                            return
                        if int(job["analyzed_count"] or 0) <= 0:
                            self.send_error_json("The task has no analyzed results to push.", status=409)
                            return
                    finally:
                        conn.close()
                    run_background(db_path, lambda bg_conn: push_rag_after_analysis_if_enabled(bg_conn, job_id, force=True))
                    self.send_json({"job_id": job_id, "queued": True, "message": "RAG Hub push queued."}, status=202)
                    return
                if parsed.path == "/api/import":
                    uploaded = read_upload_file(self)
                    if uploaded is None:
                        self.send_error_json("Missing upload file.")
                        return
                    filename, file_bytes = uploaded
                    suffix = Path(filename).suffix.lower()
                    if suffix not in {".csv", ".xlsx"}:
                        self.send_error_json("Only CSV and XLSX uploads are supported.")
                        return
                    upload_dir = ROOT / "work" / "uploads"
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=upload_dir)
                    try:
                        handle.write(file_bytes)
                        upload_path = Path(handle.name)
                    finally:
                        handle.close()
                    analyze = bool_param(query.get("analyze", ["1"])[0], default=True)
                    conn = connect(db_path)
                    try:
                        result = import_voc_file(
                            conn,
                            upload_path,
                            analyze=analyze,
                            display_filename=filename,
                        )
                        self.send_json(result)
                    finally:
                        conn.close()
                    if result.get("duplicate_upload"):
                        upload_path.unlink(missing_ok=True)
                    return
                if parsed.path == "/api/collect":
                    payload = read_json_body(self)
                    sources = [str(value) for value in payload.get("sources") or []]
                    conn = connect(db_path)
                    try:
                        if not sources:
                            self.send_error_json("Choose at least one collection source.")
                            return
                        job_id = start_job(
                            conn,
                            sources,
                            job_type="online_crawl",
                            status="queued",
                            config={**payload, "auto_analyze": bool(payload.get("auto_analyze", True))},
                        )
                    finally:
                        conn.close()
                    run_background(
                        db_path,
                        lambda bg_conn: execute_online_crawl_job(
                            bg_conn,
                            job_id,
                            collectors=build_collectors(payload),
                            analyze=bool(payload.get("auto_analyze", True)),
                        ),
                    )
                    self.send_json({"job_id": job_id, "queued": True, "sources": sources}, status=202)
                    return
                if parsed.path == "/api/monitor":
                    payload = read_json_body(self)
                    conn = connect(db_path)
                    try:
                        self.send_json(save_monitor_config(conn, payload))
                    finally:
                        conn.close()
                    return
                if parsed.path == "/api/monitor/run":
                    payload = read_json_body(self)
                    conn = connect(db_path)
                    try:
                        self.send_json(run_monitor_once(conn, force=bool(payload.get("force", True))))
                    finally:
                        conn.close()
                    return
                self.send_error_json("API route not found.", status=404)
            except Exception as exc:
                self.send_error_json(str(exc), status=500)

        def do_DELETE(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path.startswith("/api/tasks/"):
                    job_id = int(parsed.path.rsplit("/", 1)[-1])
                    conn = connect(db_path)
                    try:
                        self.send_json(delete_job(conn, job_id))
                    finally:
                        conn.close()
                    return
                self.send_error_json("API route not found.", status=404)
            except ValueError as exc:
                status = 404 if "does not exist" in str(exc) else 400
                self.send_error_json(str(exc), status=status)
            except Exception as exc:
                self.send_error_json(str(exc), status=500)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return WorkbenchHandler


def create_server(host: str, port: int, db_path: Path) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), create_handler(db_path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local VOC workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = create_server(args.host, args.port, args.db)
    start_rag_retry_worker(args.db)
    print(f"VOC workbench running at http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
