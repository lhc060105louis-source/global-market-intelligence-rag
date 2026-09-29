#!/usr/bin/env python
"""Crawl raw vehicle user comments into the VOC SQLite pipeline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    load_dotenv = None

from collectors import (
    AUTOHOME_OWNER_REVIEW_URLS,
    AUTOHOME_SOURCE,
    DEFAULT_YOUTUBE_QUERIES,
    YOUTUBE_SOURCE,
    collect_autohome_owner_reviews,
    collect_youtube_vehicle_comments,
)
from source_pipeline import (
    DEFAULT_DB_PATH,
    analyze_cleaned_items,
    connect,
    latest_metrics,
    update_daily_metrics,
)
from workflow_api import run_online_crawl_job


def load_local_env() -> None:
    env_path = Path(__file__).resolve().with_name(".env")
    if load_dotenv:
        load_dotenv(env_path, override=True)
        return
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl raw vehicle user comments for the VOC pipeline.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument(
        "--autohome-url",
        action="append",
        default=[],
        help="Autohome owner-review page URL. Defaults to public Autohome owner review entry pages.",
    )
    parser.add_argument(
        "--youtube-query",
        action="append",
        default=[],
        help="YouTube vehicle review/problem query. Can be passed multiple times.",
    )
    parser.add_argument("--youtube-api-key", default="", help="YouTube Data API key. Defaults to YOUTUBE_API_KEY.")
    parser.add_argument("--skip-youtube", action="store_true", help="Skip YouTube vehicle comments.")
    parser.add_argument("--skip-autohome", action="store_true", help="Skip Autohome auxiliary owner reviews.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum items per source.")
    parser.add_argument("--analyze", action="store_true", help="Run VOC model analysis after collection.")
    parser.add_argument("--analyze-existing", action="store_true", help="Analyze existing cleaned rows without collecting new data.")
    parser.add_argument("--analysis-limit", type=int, default=None, help="Maximum cleaned rows to analyze in this run.")
    return parser


def analyze_existing_cleaned_items(conn, limit: int | None = None) -> int:
    job_rows = conn.execute(
        """
        SELECT DISTINCT r.job_id
        FROM cleaned_items c
        JOIN raw_items r ON r.id = c.raw_item_id
        LEFT JOIN analysis_results a ON a.cleaned_item_id = c.id
        WHERE a.id IS NULL
        ORDER BY r.job_id, c.id
        """
    ).fetchall()

    analyzed_total = 0
    for row in job_rows:
        remaining = None if limit is None else limit - analyzed_total
        if remaining is not None and remaining <= 0:
            break
        job_id = int(row["job_id"])
        analyzed = analyze_cleaned_items(conn, job_id, limit=remaining)
        if analyzed:
            conn.execute(
                "UPDATE collection_jobs SET analyzed_count = analyzed_count + ? WHERE id = ?",
                (analyzed, job_id),
            )
            conn.commit()
        analyzed_total += analyzed
    return analyzed_total


def latest_analysis_summary(conn) -> dict[str, object]:
    total = conn.execute("SELECT COUNT(*) FROM analysis_results").fetchone()[0]
    latest = conn.execute(
        """
        SELECT id, source, source_id, sentiment_label, published_date, analyzed_at
        FROM analysis_results
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "total_analyzed_in_db": total,
        "latest_result": dict(latest) if latest else None,
    }


def main() -> None:
    load_local_env()
    args = build_parser().parse_args()

    conn = connect(args.db)
    if args.analyze_existing:
        analyzed_count = analyze_existing_cleaned_items(conn, limit=args.analysis_limit)
        update_daily_metrics(conn)
        summary = {
            "db": str(args.db),
            "mode": "analyze_existing",
            "analyzed_this_run": analyzed_count,
            **latest_analysis_summary(conn),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    autohome_urls = args.autohome_url or AUTOHOME_OWNER_REVIEW_URLS
    youtube_queries = args.youtube_query or DEFAULT_YOUTUBE_QUERIES
    source_labels = []
    if not args.skip_youtube:
        source_labels.append("youtube")
    if not args.skip_autohome:
        source_labels.append("autohome")

    collectors = []
    if not args.skip_youtube:
        collectors.append(
            (
                "collect_youtube",
                lambda: collect_youtube_vehicle_comments(
                    list(youtube_queries),
                    limit=args.limit,
                    api_key=args.youtube_api_key or None,
                ),
            )
        )
    if not args.skip_autohome:
        collectors.append(
            (
                "collect_autohome",
                lambda: collect_autohome_owner_reviews(list(autohome_urls), limit=args.limit),
            )
        )

    summary = run_online_crawl_job(
        conn,
        sources=source_labels,
        config={
            "youtube_queries": list(youtube_queries) if not args.skip_youtube else [],
            "autohome_urls": list(autohome_urls) if not args.skip_autohome else [],
            "limit_per_source": args.limit,
        },
        collectors=collectors,
        analyze=args.analyze,
        analysis_limit=args.analysis_limit,
    )

    summary["db"] = str(args.db)
    summary["metrics"] = latest_metrics(conn)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
