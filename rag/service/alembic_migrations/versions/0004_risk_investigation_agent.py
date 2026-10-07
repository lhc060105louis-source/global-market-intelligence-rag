"""Persist bounded risk investigation Agent runs."""
from alembic import op
import sqlalchemy as sa


revision = "0004_risk_investigation_agent"
down_revision = "0003_coordination_delivery_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("agent_runs"):
        # Older 0001 revisions used live metadata and could create this table
        # before 0004. Preserve its rows while completing the failed upgrade.
        required_columns = {
            "id", "request_key", "risk_object_id", "episode_id", "source_versions_json",
            "status", "tool_trace_json", "draft_json", "decision", "decision_reason",
            "initiated_by", "event_id", "candidate_id", "case_id", "object_version",
            "error_code", "created_at", "completed_at", "decided_at",
        }
        if not required_columns.issubset({column["name"] for column in inspector.get_columns("agent_runs")}):
            raise RuntimeError("Existing agent_runs table is incompatible with migration 0004")
    else:
        _create_agent_runs()
    indexes = {item["name"]: item for item in sa.inspect(op.get_bind()).get_indexes("agent_runs")}
    for name, columns, unique in (
        ("uq_agent_runs_request_key", ["request_key"], True),
        ("ix_agent_runs_risk_created", ["risk_object_id", "created_at"], False),
        ("ix_agent_runs_status_created", ["status", "created_at"], False),
        ("ix_agent_runs_risk_object_id", ["risk_object_id"], False),
        ("ix_agent_runs_episode_id", ["episode_id"], False),
        ("ix_agent_runs_status", ["status"], False),
    ):
        existing = indexes.get(name)
        if existing is None:
            op.create_index(name, "agent_runs", columns, unique=unique)
        elif existing["column_names"] != columns or bool(existing["unique"]) != unique:
            raise RuntimeError(f"Existing agent_runs index {name} is incompatible with migration 0004")


def _create_agent_runs() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_episode_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_risk_object_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_risk_created", table_name="agent_runs")
    op.drop_index("uq_agent_runs_request_key", table_name="agent_runs")
    op.drop_table("agent_runs")
