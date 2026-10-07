from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import AgentRun, RiskEpisode, RiskObject, utc_now


def migration_config(path):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}".replace("%", "%%"))
    return config


def test_baseline_does_not_create_future_agent_table(tmp_path):
    path = tmp_path / "baseline.db"
    command.upgrade(migration_config(path), "0001_existing_baseline")
    engine = create_engine(f"sqlite:///{path}")
    try:
        assert "knowledge_records" in inspect(engine).get_table_names()
        assert "agent_runs" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_fresh_database_reaches_head_and_can_restart(tmp_path):
    path = tmp_path / "fresh.db"
    config = migration_config(path)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path}")
    try:
        assert "agent_runs" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004_risk_investigation_agent"
    finally:
        engine.dispose()


def test_upgrade_recovers_table_created_by_old_baseline_without_losing_runs(tmp_path):
    path = tmp_path / "partial-upgrade.db"
    config = migration_config(path)
    command.upgrade(config, "0003_coordination_delivery_idempotency")
    engine = create_engine(f"sqlite:///{path}")
    try:
        # The old baseline used current metadata and created this future table.
        AgentRun.__table__.create(engine)
        with Session(engine) as db:
            risk = RiskObject(brand="Synthetic", vehicle_model="Model", part="battery", region="EU", risk_type="heat")
            db.add(risk)
            db.flush()
            episode = RiskEpisode(risk_object_id=risk.id, status="open", started_at=utc_now(), current_value=12, threshold=10)
            db.add(episode)
            db.flush()
            run = AgentRun(request_key="preserved-run", risk_object_id=risk.id, episode_id=episode.id, initiated_by="test")
            db.add(run)
            db.commit()
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT request_key FROM agent_runs")) == "preserved-run"
        indexes = {item["name"]: item for item in inspect(engine).get_indexes("agent_runs")}
        assert indexes["uq_agent_runs_request_key"]["unique"]
    finally:
        engine.dispose()
