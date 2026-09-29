"""Add delivery idempotency keys for coordination callbacks."""
from alembic import op
from sqlalchemy import Column, String, inspect

revision = "0003_coordination_delivery_idempotency"
down_revision = "0002_coordination_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    execution_columns = {item["name"] for item in inspector.get_columns("execution_results")}
    monitoring_columns = {item["name"] for item in inspector.get_columns("monitoring_snapshots")}
    if "result_push_id" not in execution_columns:
        op.add_column("execution_results", Column("result_push_id", String(255), nullable=True))
    if "snapshot_push_id" not in monitoring_columns:
        op.add_column("monitoring_snapshots", Column("snapshot_push_id", String(255), nullable=True))
    inspector = inspect(bind)
    if "ix_execution_results_result_push_id" not in {item["name"] for item in inspector.get_indexes("execution_results")}: 
        op.create_index("ix_execution_results_result_push_id", "execution_results", ["result_push_id"], unique=True)
    if "ix_monitoring_snapshots_snapshot_push_id" not in {item["name"] for item in inspector.get_indexes("monitoring_snapshots")}: 
        op.create_index("ix_monitoring_snapshots_snapshot_push_id", "monitoring_snapshots", ["snapshot_push_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_monitoring_snapshots_snapshot_push_id", table_name="monitoring_snapshots")
    op.drop_index("ix_execution_results_result_push_id", table_name="execution_results")
    op.drop_column("monitoring_snapshots", "snapshot_push_id")
    op.drop_column("execution_results", "result_push_id")
