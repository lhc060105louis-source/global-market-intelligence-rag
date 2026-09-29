import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


def test_delivery_package_is_canonical_app_root(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    assert (root / "app" / "index.html").exists()
    assert importlib.util.find_spec("app.main") is not None

    from app.main import create_app

    client = TestClient(
        create_app(
            f"sqlite:///{tmp_path / 'baseline.db'}",
            session_token="test-token",
        )
    )
    response = client.get("/")

    assert response.status_code == 200
    assert "Creator Partnership Management Platform" in response.text
    assert "v3.0" in response.text


def test_desktop_bundle_uses_the_application_entry_point_and_static_assets():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "kol-platform.spec").read_text("utf-8")

    assert 'APP_NAME = "CreatorPartnershipPlatform"' in spec
    assert 'app/static' in spec
    assert 'supabase/schema.sql' in spec
