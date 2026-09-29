from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


def create_session_factory(settings: Settings):
    if settings.database_url.startswith("sqlite:///"):
        raw_path = settings.database_url.removeprefix("sqlite:///")
        if raw_path != ":memory:":
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    )
    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
