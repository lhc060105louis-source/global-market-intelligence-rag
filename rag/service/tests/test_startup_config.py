from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings_for(tmp_path, **changes):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'startup.db'}",
        api_key="local-private-test-key",
        adapter="fake",
        fake_mode="success",
        auto_sync_on_ingest=False,
    )
    return replace(settings, **changes)


@pytest.mark.parametrize("key", ["", "   ", "replace-me", "REPLACE-ME", "replace_with_rag_hub_api_key", "replace-with-shared-secret"])
def test_startup_rejects_missing_or_placeholder_primary_key(tmp_path, key):
    with pytest.raises(ValueError, match="RAG_HUB_API_KEY"):
        with TestClient(create_app(settings_for(tmp_path, api_key=key))):
            pass


def test_startup_rejects_placeholder_actor_key(tmp_path):
    settings = settings_for(tmp_path, actor_api_keys={"replace-me": "domain_service"})
    with pytest.raises(ValueError, match="actor API key"):
        with TestClient(create_app(settings)):
            pass


def test_valid_configuration_keeps_health_and_authenticated_api_available(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/v1/records", headers={"X-API-Key": settings.api_key}).status_code == 200
        assert client.get("/api/v1/records", headers={"X-API-Key": "replace-me"}).status_code == 401
