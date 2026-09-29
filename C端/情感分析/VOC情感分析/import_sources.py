#!/usr/bin/env python
"""Import CSV/XLSX files into the unified VOC task pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from source_pipeline import DEFAULT_DB_PATH, connect, import_voc_file, latest_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import CSV/XLSX VOC signals into the unified task pipeline.")
    parser.add_argument("path", type=Path, help="CSV or XLSX file to import.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--skip-analyze", action="store_true", help="Only import and clean rows; do not run VOC analysis.")
    parser.add_argument("--analysis-limit", type=int, default=None, help="Maximum cleaned rows to analyze in this run.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    conn = connect(args.db)
    try:
        summary = import_voc_file(
            conn,
            args.path,
            analyze=not args.skip_analyze,
            analysis_limit=args.analysis_limit,
        )
        summary["db"] = str(args.db)
        summary["metrics"] = latest_metrics(conn)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
