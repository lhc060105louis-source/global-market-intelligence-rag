from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_upgrades_pre_manual_evidence_database(tmp_path):
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE kols (
              id INTEGER PRIMARY KEY, name VARCHAR(255), platform VARCHAR(50) NOT NULL,
              platform_account_id VARCHAR(255), handle VARCHAR(255), profile_url VARCHAR(500),
              country VARCHAR(2) NOT NULL, language VARCHAR(50), content_categories TEXT,
              followers INTEGER, average_engagement_rate FLOAT, audience_country_ratio FLOAT,
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE score_records (
              id INTEGER PRIMARY KEY, kol_id INTEGER NOT NULL, score_type VARCHAR(20) NOT NULL,
              dimension VARCHAR(100) NOT NULL, auto_score FLOAT, manual_score FLOAT,
              evidence TEXT, source VARCHAR(500), scored_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT INTO kols VALUES
            (1, 'Legacy', 'YouTube', NULL, '@legacy', NULL, 'GB', NULL, NULL,
             100, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        connection.execute(text("""
            INSERT INTO score_records VALUES
            (1, 1, 'commercial', 'audience_fit', 70, 90,
             'legacy analyst evidence', 'legacy analyst', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
    engine.dispose()

    app = create_app(f"sqlite:///{path}")
    with app.state.session_factory() as session:
        row = session.execute(text(
            "SELECT manual_evidence, manual_source FROM score_records WHERE id=1"
        )).one()
        assert row == ("legacy analyst evidence", "legacy analyst")
    with TestClient(app) as client:
        detail = client.get("/kols/1")
        assert detail.status_code == 200
        score = detail.json()["score_records"][0]
        assert score["manual_evidence"] == "legacy analyst evidence"
        assert score["manual_source"] == "legacy analyst"
def test_startup_country_upgrade_is_idempotent(tmp_path):
    path = tmp_path / "country.db"
    app = create_app(f"sqlite:///{path}")
    with app.state.engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO kols (
              platform, handle, country, sync_id, version, updated_by_device,
              created_at, updated_at
            ) VALUES (
              'YouTube', '@uk', 'UK',
              '00000000-0000-0000-0000-000000000001', 1,
              '00000000-0000-0000-0000-000000000002',
              CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """))
    create_app(f"sqlite:///{path}")
    upgraded = create_app(f"sqlite:///{path}")
    with upgraded.state.engine.connect() as connection:
        assert connection.execute(text("SELECT country FROM kols WHERE handle='@uk'")).scalar_one() == "GB"


def test_startup_adds_sync_metadata_to_existing_kols(tmp_path):
    path = tmp_path / "pre-sync.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE kols (
              id INTEGER PRIMARY KEY, name VARCHAR(255), platform VARCHAR(50) NOT NULL,
              platform_account_id VARCHAR(255), handle VARCHAR(255), profile_url VARCHAR(500),
              country VARCHAR(2) NOT NULL, language VARCHAR(50), content_categories TEXT,
              followers INTEGER, average_engagement_rate FLOAT, audience_country_ratio FLOAT,
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT INTO kols VALUES
            (1, 'Legacy', 'YouTube', NULL, '@legacy-sync', NULL, 'GB', NULL, NULL,
             100, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
    engine.dispose()

    app = create_app(f"sqlite:///{path}")
    with app.state.engine.connect() as connection:
        row = connection.execute(text("""
            SELECT sync_id, version, updated_by_device, deleted_at
            FROM kols WHERE id = 1
        """)).one()

    assert len(row.sync_id) == 36
    assert row.version == 1
    assert len(row.updated_by_device) == 36
    assert row.deleted_at is None
