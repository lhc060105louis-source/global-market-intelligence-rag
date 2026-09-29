from collections.abc import Generator
from uuid import uuid4

from fastapi import FastAPI, Request
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.paths import AppPaths


class Base(DeclarativeBase):
    pass


def _upgrade_sqlite_schema(engine) -> None:
    """Apply additive upgrades needed by databases created before migrations existed."""
    if engine.dialect.name != "sqlite":
        return
    tables = inspect(engine).get_table_names()
    with engine.begin() as connection:
        if "kols" in tables:
            connection.execute(text("UPDATE kols SET country = 'GB' WHERE UPPER(country) = 'UK'"))
            kol_columns = {
                column["name"] for column in inspect(engine).get_columns("kols")
            }
            if "sync_id" not in kol_columns:
                connection.execute(
                    text("ALTER TABLE kols ADD COLUMN sync_id VARCHAR(36)")
                )
            if "version" not in kol_columns:
                connection.execute(
                    text("ALTER TABLE kols ADD COLUMN version INTEGER DEFAULT 1")
                )
            if "updated_by_device" not in kol_columns:
                connection.execute(
                    text("ALTER TABLE kols ADD COLUMN updated_by_device VARCHAR(36)")
                )
            if "deleted_at" not in kol_columns:
                connection.execute(
                    text("ALTER TABLE kols ADD COLUMN deleted_at DATETIME")
                )
            from app.device import get_device_id

            missing_ids = connection.execute(
                text("SELECT id FROM kols WHERE sync_id IS NULL OR sync_id = ''")
            ).scalars()
            for kol_id in missing_ids:
                connection.execute(
                    text("""
                        UPDATE kols
                        SET sync_id = :sync_id,
                            version = COALESCE(version, 1),
                            updated_by_device = COALESCE(updated_by_device, :device_id)
                        WHERE id = :kol_id
                    """),
                    {
                        "sync_id": str(uuid4()),
                        "device_id": get_device_id(),
                        "kol_id": kol_id,
                    },
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_kols_sync_id "
                    "ON kols (sync_id)"
                )
            )
        if "score_records" not in tables:
            return
        columns = {column["name"] for column in inspect(engine).get_columns("score_records")}
        if "manual_evidence" not in columns:
            connection.execute(text("ALTER TABLE score_records ADD COLUMN manual_evidence TEXT"))
        if "manual_source" not in columns:
            connection.execute(text("ALTER TABLE score_records ADD COLUMN manual_source VARCHAR(500)"))
        # Before these columns existed, the score override endpoint stored analyst
        # evidence/source in the only available fields. Copy them for manual rows.
        connection.execute(text("""
            UPDATE score_records
            SET manual_evidence = COALESCE(manual_evidence, evidence),
                manual_source = COALESCE(manual_source, source)
            WHERE manual_score IS NOT NULL
        """))


def default_database_url() -> str:
    paths = AppPaths.from_environment()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{paths.database_path}"


def configure_database(app: FastAPI, database_url: str | None = None) -> None:
    engine = create_engine(
        database_url or default_database_url(),
        connect_args={"check_same_thread": False},
    )
    app.state.engine = engine
    app.state.session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    _upgrade_sqlite_schema(engine)


def get_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
