import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import SESSION_HEADER


@pytest.fixture()
def client(tmp_path):
    database_path = tmp_path / "test.db"
    app = create_app(f"sqlite:///{database_path}", session_token="pytest-session")
    with TestClient(app, headers={SESSION_HEADER: "pytest-session"}, client=("127.0.0.1", 50000)) as test_client:
        yield test_client


@pytest.fixture()
def unauthenticated_client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'unauthenticated.db'}", session_token="pytest-session")
    with TestClient(app, client=("127.0.0.1", 50001)) as test_client:
        yield test_client
