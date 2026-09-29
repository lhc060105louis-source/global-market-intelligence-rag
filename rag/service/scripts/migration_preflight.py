"""Read-only preflight for the RAG Hub database migration."""
import argparse
import json
import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


REQUIRED_TABLES = {
    "knowledge_records", "ingestion_events", "rag_sync_tasks", "domain_events",
    "domain_event_revisions", "association_candidates", "coordination_cases",
    "case_domain_impacts", "coordination_tasks", "execution_results",
    "monitoring_snapshots", "retrospectives", "coordination_audit_events",
}
REQUIRED_INGESTION_COLUMNS = {"ingestion_kind", "target_object_type", "target_object_id"}
REQUIRED_EVENT_COLUMNS = {"execution_mode", "is_simulated"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check RAG Hub migration readiness without writing")
    parser.add_argument("--database", default="./data/rag_hub.db", help="SQLite database path")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    database = Path(args.database).resolve()
    if not database.exists():
        result = {"status": "missing", "database": str(database), "message": "database file does not exist; a fresh migration can create it"}
    else:
        db = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in db.execute("select name from sqlite_master where type = 'table'")}
            version = db.execute("select version_num from alembic_version").fetchone()[0] if "alembic_version" in tables else None
            ingestion_columns = {row[1] for row in db.execute("pragma table_info(ingestion_events)")} if "ingestion_events" in tables else set()
            event_columns = {row[1] for row in db.execute("pragma table_info(domain_events)")} if "domain_events" in tables else set()
            revision_columns = {row[1] for row in db.execute("pragma table_info(domain_event_revisions)")} if "domain_event_revisions" in tables else set()
        finally:
            db.close()
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        head = ScriptDirectory.from_config(config).get_current_head()
        missing_tables = sorted(REQUIRED_TABLES - tables)
        result = {
            "status": "ready" if not missing_tables and REQUIRED_INGESTION_COLUMNS <= ingestion_columns and REQUIRED_EVENT_COLUMNS <= event_columns and REQUIRED_EVENT_COLUMNS <= revision_columns else "needs_migration",
            "database": str(database), "current_revision": version, "head_revision": head,
            "missing_tables": missing_tables,
            "missing_ingestion_columns": sorted(REQUIRED_INGESTION_COLUMNS - ingestion_columns),
            "missing_domain_event_columns": sorted(REQUIRED_EVENT_COLUMNS - event_columns),
            "missing_domain_event_revision_columns": sorted(REQUIRED_EVENT_COLUMNS - revision_columns),
            "read_only": True,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else format_result(result))
    return 0 if result["status"] in {"ready", "missing"} else 1


def format_result(result: dict) -> str:
    lines = [f"status: {result['status']}", f"database: {result['database']}"]
    if result["status"] == "missing":
        lines.append(result["message"])
    else:
        lines.extend([f"current_revision: {result['current_revision']}", f"head_revision: {result['head_revision']}"])
        for key in ("missing_tables", "missing_ingestion_columns", "missing_domain_event_columns", "missing_domain_event_revision_columns"):
            if result[key]:
                lines.append(f"{key}: {', '.join(result[key])}")
        lines.append("read_only: true")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
