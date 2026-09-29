"""Persist bounded risk investigation Agent runs."""
from alembic import op
import sqlalchemy as sa


revision = "0004_risk_investigation_agent"
down_revision = "0003_coordination_delivery_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_key", sa.String(length=128), nullable=False),
        sa.Column("risk_object_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("source_versions_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tool_trace_json", sa.JSON(), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("object_version", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["risk_episodes.id"]),
        sa.ForeignKeyConstraint(["risk_object_id"], ["risk_objects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_agent_runs_request_key", "agent_runs", ["request_key"], unique=True)
    op.create_index("ix_agent_runs_risk_created", "agent_runs", ["risk_object_id", "created_at"])
    op.create_index("ix_agent_runs_status_created", "agent_runs", ["status", "created_at"])
    op.create_index("ix_agent_runs_risk_object_id", "agent_runs", ["risk_object_id"])
    op.create_index("ix_agent_runs_episode_id", "agent_runs", ["episode_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_episode_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_risk_object_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_risk_created", table_name="agent_runs")
    op.drop_index("uq_agent_runs_request_key", table_name="agent_runs")
    op.drop_table("agent_runs")
