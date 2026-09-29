import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.settings import put_youtube_settings
from app.schemas import YouTubeKeyRequest
from app.security import CredentialStore, CredentialStoreError


class FakeCredentials:
    def __init__(self):
        self.value = None
        self.fail_writes = False

    def get_youtube_api_key(self):
        return self.value

    def set_youtube_api_key(self, value):
        if self.fail_writes:
            raise CredentialStoreError("credential storage unavailable")
        self.value = value

    def delete_youtube_api_key(self):
        self.value = None


@pytest.fixture()
def fake_credentials(client):
    credentials = FakeCredentials()
    client.app.state.credential_store = credentials
    return credentials


def test_settings_never_returns_key(client, fake_credentials):
    fake_credentials.value = "secret-key"

    assert client.get("/settings/youtube").json() == {
        "configured": True,
        "valid": None,
    }


def test_save_failure_does_not_fall_back_to_plaintext(
    client, fake_credentials, monkeypatch
):
    fake_credentials.fail_writes = True
    monkeypatch.setattr("app.api.settings.validate_youtube_api_key", lambda value: True)

    response = client.put("/settings/youtube", json={"api_key": "secret-key"})

    assert response.status_code == 503
    assert "secret-key" not in response.text


def test_key_is_validated_before_saving(client, fake_credentials, monkeypatch):
    validated = []
    monkeypatch.setattr(
        "app.api.settings.validate_youtube_api_key",
        lambda value: validated.append(value) or False,
    )

    response = client.put("/settings/youtube", json={"api_key": "invalid-secret"})

    assert response.status_code == 422
    assert validated == ["invalid-secret"]
    assert fake_credentials.value is None
    assert "invalid-secret" not in response.text


def test_credential_store_uses_only_keyring(monkeypatch):
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(
            set_password=lambda service, username, value: calls.append(
                (service, username, value)
            )
        ),
    )

    CredentialStore().set_youtube_api_key("stored-secret")

    assert calls == [("kol-cooperation-platform", "youtube-api-key", "stored-secret")]


def test_malformed_settings_payload_never_echoes_secret(client):
    response = client.put(
        "/settings/youtube", json={"api_key": {"nested": "wrong-shaped-secret"}}
    )

    assert response.status_code == 422
    assert "wrong-shaped-secret" not in response.text


def test_keyring_error_drops_secret_bearing_exception_chain(monkeypatch):
    secret = "backend-secret-key"
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(
            set_password=lambda *args: (_ for _ in ()).throw(
                RuntimeError(f"backend rejected {secret}")
            )
        ),
    )

    with pytest.raises(CredentialStoreError) as exc_info:
        CredentialStore().set_youtube_api_key(secret)

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert secret not in repr(exc_info.value)


def test_settings_http_error_drops_credential_exception_chain(monkeypatch):
    secret = "http-secret-key"

    class FailingStore:
        def set_youtube_api_key(self, value):
            raise CredentialStoreError(f"storage rejected {secret}")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(credential_store=FailingStore()))
    )
    monkeypatch.setattr("app.api.settings.validate_youtube_api_key", lambda value: True)

    with pytest.raises(HTTPException) as exc_info:
        put_youtube_settings(YouTubeKeyRequest(api_key=secret), request)

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert secret not in repr(exc_info.value)
