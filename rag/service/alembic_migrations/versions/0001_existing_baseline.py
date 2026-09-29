"""Baseline for the pre-coordination RAG Hub schema."""
from alembic import op
from sqlalchemy import inspect

from app.database import Base
from app import models  # noqa: F401

revision = "0001_existing_baseline"
down_revision = None
branch_labels = None
depends_on = None

_COORDINATION_TABLES = {
    "domain_events", "domain_event_revisions", "association_candidates", "coordination_cases",
    "case_domain_impacts", "coordination_tasks", "execution_results", "monitoring_snapshots",
    "retrospectives", "coordination_audit_events",
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in _COORDINATION_TABLES and table.name not in existing:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    pass
