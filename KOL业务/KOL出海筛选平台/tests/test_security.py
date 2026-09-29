from fastapi.testclient import TestClient

from app.main import create_app
from app.security import SESSION_COOKIE, SESSION_HEADER, create_session_token


def test_session_token_is_random_and_url_safe():
    first, second = create_session_token(), create_session_token()
    assert first != second
    assert len(first) >= 32
    assert all(char.isalnum() or char in "-_" for char in first)


def test_mutation_requires_session_token(unauthenticated_client):
    assert unauthenticated_client.post("/collections", json={"keywords": ["BYD"]}).status_code == 403


def test_health_does_not_require_token(unauthenticated_client):
    assert unauthenticated_client.get("/health").status_code == 200


def test_mutation_accepts_header_or_cookie(tmp_path):
    token = "test-session-token"
    app = create_app(f"sqlite:///{tmp_path / 'secure.db'}", session_token=token)
    with TestClient(app, client=("127.0.0.1", 50000)) as browser:
        assert browser.post("/collections", json={"keywords": ["BYD"]}, headers={SESSION_HEADER: token}).status_code == 201
        browser.cookies.set(SESSION_COOKIE, token)
        assert browser.delete("/settings/youtube").status_code in {200, 503}


def test_protected_download_requires_session(client, unauthenticated_client):
    assert unauthenticated_client.get("/exports/kols.xlsx").status_code == 403
    assert client.get("/exports/kols.xlsx").status_code == 200


def test_home_bootstraps_token_and_secure_cookie(tmp_path):
    token = "bootstrap-secret"
    app = create_app(f"sqlite:///{tmp_path / 'bootstrap.db'}", session_token=token)
    with TestClient(app, client=("127.0.0.1", 50000)) as browser:
        response = browser.get("/")
    assert f'window.__KOL_SESSION_TOKEN__ = "{token}"' in response.text
    cookie = response.headers["set-cookie"]
    assert SESSION_COOKIE in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" in cookie


def test_non_loopback_client_is_rejected(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'remote.db'}", session_token="secret")
    with TestClient(app, client=("203.0.113.9", 50000)) as remote:
        assert remote.get("/health").status_code == 403
