"""Baseline for the pre-coordination RAG Hub schema."""
from alembic import op
from sqlalchemy import inspect

from app.database import Base
from app import models  # noqa: F401

revision = "0001_existing_baseline"
down_revision = None
branch_labels = None
depends_on = None

_BASELINE_TABLES = {
    "knowledge_records", "ingestion_events", "rag_document_mappings", "rag_sync_tasks",
    "risk_objects", "risk_episodes", "risk_trend_points", "record_annotations",
    "maintenance_operations",
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table in Base.metadata.sorted_tables:
        # New models belong to their own migration, not this historical baseline.
        if table.name in _BASELINE_TABLES and table.name not in existing:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    pass
