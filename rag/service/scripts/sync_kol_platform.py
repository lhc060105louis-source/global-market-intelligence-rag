#!/usr/bin/env python3
"""Synchronize completed KOL assessments into the formal RAG Hub."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.kol_source_adapter import KOLAdapterConfig, KOLSourceError, sync_kol_assessments  # noqa: E402


def load_service_env() -> None:
    env_path = SERVICE_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Sync completed creator assessments to the production RAG Hub")
    result.add_argument("--kol-url", help="Creator platform URL; defaults to KOL_SOURCE_BASE_URL")
    result.add_argument("--rag-url", help="Production RAG Hub URL; defaults to RAG_HUB_BASE_URL or http://127.0.0.1:8001")
    result.add_argument("--api-key", help="RAG Hub API key; defaults to RAG_HUB_API_KEY")
    result.add_argument("--dry-run", action="store_true", help="Validate and transform data without sending it")
    result.add_argument("--mock", action="store_true", help="Mark this source as demo data")
    result.add_argument("--watch-seconds", type=float, default=0, help="Keep syncing at this interval when greater than 0")
    return result


def run_once(args: argparse.Namespace) -> dict:
    config = KOLAdapterConfig(
        kol_base_url=args.kol_url or os.getenv("KOL_SOURCE_BASE_URL", "http://127.0.0.1:8766"),
        rag_base_url=args.rag_url or os.getenv("RAG_HUB_BASE_URL", "http://127.0.0.1:8001"),
        rag_api_key=args.api_key or os.getenv("RAG_HUB_API_KEY", ""),
        timeout_seconds=float(os.getenv("KOL_SOURCE_TIMEOUT_SECONDS", "15")),
        kol_session_token=os.getenv("KOL_SOURCE_SESSION_TOKEN", ""),
        is_mock=args.mock or _env_bool("KOL_SOURCE_IS_MOCK", False),
    )
    return sync_kol_assessments(config, dry_run=args.dry_run)


def main() -> int:
    load_service_env()
    args = parser().parse_args()
    if args.watch_seconds < 0:
        print("--watch-seconds must not be negative", file=sys.stderr)
        return 2
    while True:
        try:
            report = run_once(args)
        except KOLSourceError as exc:
            print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.watch_seconds == 0:
            return 1 if report["failed_count"] else 0
        time.sleep(args.watch_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
