from fastapi import APIRouter, HTTPException, Request

from app.schemas import (
    SupabaseSettingsResponse,
    SupabaseSettingsWrite,
    YouTubeKeyRequest,
    YouTubeSettingsResponse,
)
from app.security import CredentialStore, CredentialStoreError
from app.services.youtube_enrichment import validate_youtube_api_key

router = APIRouter(prefix="/settings/youtube", tags=["Settings"])
cloud_router = APIRouter(prefix="/settings/supabase", tags=["Settings"])


def _store(request: Request):
    return getattr(request.app.state, "credential_store", CredentialStore())


@router.get("", response_model=YouTubeSettingsResponse)
def get_youtube_settings(request: Request) -> YouTubeSettingsResponse:
    failed = False
    configured = False
    try:
        configured = bool(_store(request).get_youtube_api_key())
    except CredentialStoreError:
        failed = True
    if failed:
        raise HTTPException(status_code=503, detail="Credential storage unavailable")
    return YouTubeSettingsResponse(configured=configured, valid=None)


@router.put("", response_model=YouTubeSettingsResponse)
def put_youtube_settings(
    payload: YouTubeKeyRequest, request: Request
) -> YouTubeSettingsResponse:
    if not validate_youtube_api_key(payload.api_key):
        raise HTTPException(status_code=422, detail="YouTube API key is invalid")
    failed = False
    try:
        _store(request).set_youtube_api_key(payload.api_key)
    except CredentialStoreError:
        failed = True
    if failed:
        raise HTTPException(status_code=503, detail="Credential storage unavailable")
    return YouTubeSettingsResponse(configured=True, valid=True)


@router.delete("", response_model=YouTubeSettingsResponse)
def delete_youtube_settings(request: Request) -> YouTubeSettingsResponse:
    failed = False
    try:
        _store(request).delete_youtube_api_key()
    except CredentialStoreError:
        failed = True
    if failed:
        raise HTTPException(status_code=503, detail="Credential storage unavailable")
    return YouTubeSettingsResponse(configured=False, valid=None)


@cloud_router.get("", response_model=SupabaseSettingsResponse)
def get_supabase_settings(request: Request) -> SupabaseSettingsResponse:
    try:
        url = _store(request).get_secret("supabase-url")
        configured = bool(
            url
            and _store(request).get_secret("supabase-anon-key")
            and _store(request).get_secret("supabase-access-token")
        )
    except CredentialStoreError:
        raise HTTPException(
            status_code=503, detail="Credential storage unavailable"
        ) from None
    return SupabaseSettingsResponse(configured=configured, url=url)


@cloud_router.put("", response_model=SupabaseSettingsResponse)
def put_supabase_settings(
    payload: SupabaseSettingsWrite,
    request: Request,
) -> SupabaseSettingsResponse:
    try:
        store = _store(request)
        store.set_secret("supabase-url", payload.url.rstrip("/"))
        store.set_secret("supabase-anon-key", payload.anon_key)
        store.set_secret("supabase-access-token", payload.access_token)
    except CredentialStoreError:
        raise HTTPException(
            status_code=503, detail="Credential storage unavailable"
        ) from None
    return SupabaseSettingsResponse(
        configured=True,
        url=payload.url.rstrip("/"),
    )


@cloud_router.delete("", response_model=SupabaseSettingsResponse)
def delete_supabase_settings(request: Request) -> SupabaseSettingsResponse:
    try:
        store = _store(request)
        for username in (
            "supabase-url",
            "supabase-anon-key",
            "supabase-access-token",
        ):
            store.delete_secret(username)
    except CredentialStoreError:
        raise HTTPException(
            status_code=503, detail="Credential storage unavailable"
        ) from None
    return SupabaseSettingsResponse(configured=False, url=None)
