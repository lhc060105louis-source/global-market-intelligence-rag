from __future__ import annotations

import hmac
import ipaddress
import secrets

from fastapi import HTTPException, Request

SERVICE_NAME = "kol-cooperation-platform"
YOUTUBE_USERNAME = "youtube-api-key"
SESSION_HEADER = "X-KOL-Session"
SESSION_COOKIE = "kol_session"


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def is_loopback_request(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return request.client.host in {"localhost", "testclient"}


def require_loopback_session(request: Request) -> None:
    if not is_loopback_request(request):
        raise HTTPException(status_code=403, detail="Loopback access only")
    expected = getattr(request.app.state, "session_token", "")
    supplied = request.headers.get(SESSION_HEADER) or request.cookies.get(SESSION_COOKIE) or ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid local session")


class CredentialStoreError(RuntimeError):
    """Raised when the operating-system credential store is unavailable."""


class CredentialStore:
    def get_secret(self, username: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(SERVICE_NAME, username)
        except Exception:
            raise CredentialStoreError("credential storage unavailable") from None

    def set_secret(self, username: str, value: str) -> None:
        try:
            import keyring

            keyring.set_password(SERVICE_NAME, username, value)
        except Exception:
            raise CredentialStoreError("credential storage unavailable") from None

    def delete_secret(self, username: str) -> None:
        try:
            import keyring

            keyring.delete_password(SERVICE_NAME, username)
        except Exception:
            raise CredentialStoreError("credential storage unavailable") from None

    def get_youtube_api_key(self) -> str | None:
        failed = False
        value = None
        try:
            import keyring

            value = keyring.get_password(SERVICE_NAME, YOUTUBE_USERNAME)
        except Exception:
            failed = True
        if failed:
            raise CredentialStoreError("credential storage unavailable")
        return value

    def set_youtube_api_key(self, value: str) -> None:
        failed = False
        try:
            import keyring

            keyring.set_password(SERVICE_NAME, YOUTUBE_USERNAME, value)
        except Exception:
            failed = True
        if failed:
            raise CredentialStoreError("credential storage unavailable")

    def delete_youtube_api_key(self) -> None:
        failed = False
        try:
            import keyring

            keyring.delete_password(SERVICE_NAME, YOUTUBE_USERNAME)
        except Exception:
            failed = True
        if failed:
            raise CredentialStoreError("credential storage unavailable")
