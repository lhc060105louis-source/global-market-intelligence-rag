#!/usr/bin/env python
"""Create missing C historical snapshots from active current records.

This is an API-only maintenance script. It deliberately leaves current
records untouched and lets RAG Hub create normal MaxKB sync tasks through its
ingestion endpoint.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = SERVICE_ROOT / ".env"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.schemas import RESULT_REQUIRED
from app.text_quality import find_text_quality_issues


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def payload_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def request_json(
    *,
    url: str,
    method: str,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "X-API-Key": api_key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed if isinstance(parsed, dict) else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"detail": raw[:500]}
        detail = parsed.get("detail") if isinstance(parsed, dict) else raw[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"RAG Hub connection failed: {exc.reason}") from exc


def list_current_records(base_url: str, api_key: str, page_size: int, timeout: float) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urlencode({
            "source_system": "C",
            "record_mode": "current",
            "status": "active",
            "target_knowledge_base": "c_current",
            "page": page,
            "page_size": page_size,
        })
        _, response = request_json(
            url=f"{base_url}/api/v1/records?{query}",
            method="GET",
            api_key=api_key,
            timeout=timeout,
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise RuntimeError("RAG Hub returned an invalid records response")
        records.extend(item for item in items if isinstance(item, dict))
        total = int(response.get("total") or len(records))
        if len(records) >= total or not items:
            return records
        page += 1


def snapshot_envelope(
    record: dict[str, Any],
    business_date: date,
    *,
    repair_invalid_optional_fields: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    source_record_id = str(record.get("source_record_id") or "").strip()
    record_type = str(record.get("record_type") or "").strip()
    source_version = int(record.get("source_version") or 0)
    if not source_record_id or not record_type or source_version < 1:
        raise ValueError("current record is missing source identity or version")
    source_url = record.get("source_url")
    if source_url and not str(source_url).startswith(("http://", "https://")):
        source_url = None
    payload = payload_mapping(record.get("payload_json"))
    if not payload:
        raise ValueError("current record has no object payload_json")
    repaired_fields: list[str] = []
    if repair_invalid_optional_fields and isinstance(payload.get("result"), dict):
        required_fields = RESULT_REQUIRED.get(record_type, set())
        for issue in find_text_quality_issues(payload):
            prefix = "payload.result."
            if issue.path.startswith(prefix) and "." not in issue.path[len(prefix):]:
                field = issue.path[len(prefix):]
                if field not in required_fields:
                    payload["result"].pop(field, None)
                    repaired_fields.append(field)
        if find_text_quality_issues(payload):
            raise ValueError("payload still contains invalid text after optional-field repair")
    return {
        "source_system": "C",
        "source_record_id": source_record_id,
        "record_type": record_type,
        "event_type": "create_snapshot",
        "source_version": source_version,
        "effective_at": record.get("effective_at"),
        "source_updated_at": record.get("source_updated_at"),
        "source_url": source_url,
        "push_id": f"c-voc-rag:{source_record_id}:snapshot:{business_date.isoformat()}:v{source_version}",
        "is_mock": bool(record.get("is_mock")),
        "payload": payload,
    }, sorted(set(repaired_fields))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill C current records into date-keyed historical snapshots.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--base-url", help="RAG Hub URL; defaults to RAG_HUB_URL or RAG_HUB_BASE_URL from env")
    parser.add_argument("--api-key", help="RAG Hub API key; defaults to RAG_HUB_API_KEY from env")
    parser.add_argument("--before-date", help="Only snapshot records before YYYY-MM-DD; defaults to today in Asia/Shanghai")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true", help="List eligible records without posting")
    parser.add_argument(
        "--repair-invalid-optional-fields",
        action="store_true",
        help="Drop only invalid non-required result fields in a new snapshot; never changes the current record",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    env = load_env(args.env_file)
    base_url = (args.base_url or env.get("RAG_HUB_URL") or env.get("RAG_HUB_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")
    api_key = args.api_key or env.get("RAG_HUB_API_KEY", "")
    if not api_key:
        raise SystemExit("RAG_HUB_API_KEY is required (use --api-key or --env-file)")
    if args.page_size < 1 or args.page_size > 200:
        raise SystemExit("--page-size must be between 1 and 200")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")

    default_cutoff = datetime.now(timezone(timedelta(hours=8))).date()
    cutoff = parse_date(args.before_date) if args.before_date else default_cutoff
    if cutoff is None:
        raise SystemExit("--before-date must be YYYY-MM-DD")

    records = list_current_records(base_url, api_key, args.page_size, args.timeout)
    summary: dict[str, Any] = {
        "base_url": base_url,
        "before_date": cutoff.isoformat(),
        "current_records": len(records),
        "eligible": 0,
        "created": 0,
        "updated": 0,
        "duplicate": 0,
        "idempotent": 0,
        "skipped": 0,
        "failed": 0,
        "sanitized_records": 0,
        "dry_run": args.dry_run,
    }
    failures: list[dict[str, str]] = []
    for record in records:
        payload = payload_mapping(record.get("payload_json"))
        business_date = parse_date(payload.get("business_date")) or parse_date(record.get("business_date"))
        if business_date is None or business_date >= cutoff:
            summary["skipped"] += 1
            continue
        summary["eligible"] += 1
        try:
            envelope, repaired_fields = snapshot_envelope(
                record,
                business_date,
                repair_invalid_optional_fields=args.repair_invalid_optional_fields,
            )
            if repaired_fields:
                summary["sanitized_records"] += 1
            if args.dry_run:
                continue
            status_code, response = request_json(
                url=f"{base_url}/api/v1/ingestion/c",
                method="POST",
                api_key=api_key,
                body=envelope,
                timeout=args.timeout,
            )
            decision = str(response.get("decision") or "")
            if decision == "created":
                summary["idempotent" if status_code == 200 else "created"] += 1
            elif decision == "updated":
                summary["updated"] += 1
            elif decision == "duplicate":
                summary["duplicate"] += 1
            else:
                raise RuntimeError(f"unexpected ingestion decision: {decision or 'missing'}")
        except Exception as exc:  # noqa: BLE001 - report each bad record and continue
            summary["failed"] += 1
            failures.append({"record_id": str(record.get("id") or ""), "error": str(exc)[:500]})
    if failures:
        summary["failures"] = failures
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"failed": 1, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
