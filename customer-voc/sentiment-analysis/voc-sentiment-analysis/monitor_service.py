"""Minimal scheduled online collection service for the VOC pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from collectors import collect_autohome_owner_reviews, collect_youtube_vehicle_comments
from source_pipeline import DEFAULT_DB_PATH, connect, utc_now
from workflow_api import run_online_crawl_job


DEFAULT_MONITOR_CONFIG = {
    "enabled": False,
    "interval_minutes": 60,
    "sources": ["youtube", "autohome"],
    "keywords": [],
    "autohome_urls": [],
    "limit_per_source": 30,
    "auto_analyze": True,
    "last_run_at": None,
    "next_run_at": None,
}


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def ensure_monitor_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_configs (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            config_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def load_monitor_config(conn) -> dict[str, Any]:
    ensure_monitor_schema(conn)
    row = conn.execute("SELECT config_json FROM monitor_configs WHERE id = 1").fetchone()
    if not row:
        return dict(DEFAULT_MONITOR_CONFIG)
    try:
        config = json.loads(row["config_json"])
    except json.JSONDecodeError:
        config = {}
    return {**DEFAULT_MONITOR_CONFIG, **config}


def save_monitor_config(conn, config: dict[str, Any]) -> dict[str, Any]:
    ensure_monitor_schema(conn)
    merged = {**DEFAULT_MONITOR_CONFIG, **config}
    interval = int(merged.get("interval_minutes") or 60)
    merged["interval_minutes"] = max(1, interval)
    if merged.get("enabled") and not merged.get("next_run_at"):
        merged["next_run_at"] = utc_now()
    conn.execute(
        """
        INSERT INTO monitor_configs(id, config_json, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            config_json = excluded.config_json,
            updated_at = excluded.updated_at
        """,
        (json.dumps(merged, ensure_ascii=False), utc_now()),
    )
    conn.commit()
    return merged


def monitor_is_due(config: dict[str, Any], now: datetime | None = None) -> bool:
    if not config.get("enabled"):
        return False
    now = now or datetime.now(timezone.utc)
    next_run = parse_utc(config.get("next_run_at"))
    return next_run is None or next_run <= now


def has_running_online_job(conn) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM collection_jobs
        WHERE job_type = 'online_crawl' AND status = 'running'
        """
    ).fetchone()
    return bool(row and row["count"])


def next_run_at(interval_minutes: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(minutes=max(1, interval_minutes))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_collectors(config: dict[str, Any]):
    sources = set(config.get("sources") or [])
    limit = int(config.get("limit_per_source") or 30)
    keywords = list(config.get("keywords") or [])
    autohome_urls = list(config.get("autohome_urls") or [])
    collectors = []
    if "youtube" in sources:
        collectors.append(
            (
                "collect_youtube",
                lambda: collect_youtube_vehicle_comments(keywords or None, limit=limit),
            )
        )
    if "autohome" in sources:
        collectors.append(
            (
                "collect_autohome",
                lambda: collect_autohome_owner_reviews(autohome_urls or None, limit=limit),
            )
        )
    return collectors


def run_monitor_once(
    conn,
    *,
    force: bool = False,
    collector_overrides=None,
    analyze_func: Any | None = None,
) -> dict[str, Any]:
    config = load_monitor_config(conn)
    if not force and not monitor_is_due(config):
        return {"ran": False, "reason": "not_due", "config": config}
    if has_running_online_job(conn):
        config["next_run_at"] = next_run_at(int(config.get("interval_minutes") or 60))
        save_monitor_config(conn, config)
        return {"ran": False, "reason": "previous_run_still_running", "config": config}

    sources = list(config.get("sources") or [])
    collectors = collector_overrides if collector_overrides is not None else build_collectors(config)
    summary = run_online_crawl_job(
        conn,
        sources=sources,
        config=config,
        collectors=collectors,
        analyze=bool(config.get("auto_analyze", True)),
        analyze_func=analyze_func,
    )
    config["last_run_at"] = utc_now()
    config["next_run_at"] = next_run_at(int(config.get("interval_minutes") or 60))
    save_monitor_config(conn, config)
    return {"ran": True, "summary": summary, "config": config}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or configure scheduled VOC online collection.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--interval-minutes", type=int)
    parser.add_argument("--source", action="append", choices=["youtube", "autohome"])
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--autohome-url", action="append", default=[])
    parser.add_argument("--limit-per-source", type=int)
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--run-now", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    conn = connect(args.db)
    try:
        config = load_monitor_config(conn)
        updates: dict[str, Any] = {}
        if args.enable:
            updates["enabled"] = True
        if args.disable:
            updates["enabled"] = False
        if args.interval_minutes is not None:
            updates["interval_minutes"] = args.interval_minutes
        if args.source:
            updates["sources"] = args.source
        if args.keyword:
            updates["keywords"] = args.keyword
        if args.autohome_url:
            updates["autohome_urls"] = args.autohome_url
        if args.limit_per_source is not None:
            updates["limit_per_source"] = args.limit_per_source
        if args.skip_analyze:
            updates["auto_analyze"] = False
        if updates:
            config = save_monitor_config(conn, {**config, **updates})
        result = run_monitor_once(conn, force=args.run_now) if args.run_now else {"config": config}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
