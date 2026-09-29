"""Add the shared cross-domain coordination foundation."""
from alembic import op
from sqlalchemy import Boolean, Column, String, inspect

from app.database import Base
from app import models  # noqa: F401

revision = "0002_coordination_foundation"
down_revision = "0001_existing_baseline"
branch_labels = None
depends_on = None

_COORDINATION_TABLES = {
    "domain_events", "domain_event_revisions", "association_candidates", "coordination_cases",
    "case_domain_impacts", "coordination_tasks", "execution_results", "monitoring_snapshots",
    "retrospectives", "coordination_audit_events",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name in _COORDINATION_TABLES and table.name not in existing_tables:
            table.create(bind=bind, checkfirst=True)
    inspector = inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("domain_events")}
    revision_columns = {column["name"] for column in inspector.get_columns("domain_event_revisions")}
    if "execution_mode" not in event_columns:
        op.add_column("domain_events", Column("execution_mode", String(32), nullable=False, server_default="real"))
    if "is_simulated" not in event_columns:
        op.add_column("domain_events", Column("is_simulated", Boolean, nullable=False, server_default="0"))
    if "execution_mode" not in revision_columns:
        op.add_column("domain_event_revisions", Column("execution_mode", String(32), nullable=False, server_default="real"))
    if "is_simulated" not in revision_columns:
        op.add_column("domain_event_revisions", Column("is_simulated", Boolean, nullable=False, server_default="0"))
    columns = {column["name"] for column in inspector.get_columns("ingestion_events")}
    if "ingestion_kind" not in columns:
        op.add_column("ingestion_events", Column("ingestion_kind", String(32), nullable=False, server_default="knowledge_record"))
    if "target_object_type" not in columns:
        op.add_column("ingestion_events", Column("target_object_type", String(32), nullable=True))
    if "target_object_id" not in columns:
        op.add_column("ingestion_events", Column("target_object_id", String(36), nullable=True))
    # The create pass above also makes this migration safe for a fresh database;
    # the column checks above keep it compatible with an older coordination schema.


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for name in reversed(sorted(_COORDINATION_TABLES)):
        if name in existing:
            op.drop_table(name)
    columns = {column["name"] for column in inspect(bind).get_columns("ingestion_events")}
    for name in ("target_object_id", "target_object_type", "ingestion_kind"):
        if name in columns:
            op.drop_column("ingestion_events", name)
