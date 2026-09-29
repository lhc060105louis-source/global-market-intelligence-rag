import os
import sys
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_permissions.db"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-that-is-not-used-in-production"
os.environ["RSS_SCHEDULER_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture(scope="session")
def account(client):
    response = client.post("/api/auth/register", json={
        "email": "owner@example.com", "password": "correct-horse-123",
        "display_name": "Test User", "organization_name": "Test Organization",
    })
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(account):
    return {"Authorization": f"Bearer {account['access_token']}"}
