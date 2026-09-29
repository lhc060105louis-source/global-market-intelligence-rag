from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import SyncConflict, SyncEvent, SyncState
from app.schemas import SyncStatusResponse
from app.security import CredentialStore, CredentialStoreError
from app.sync.supabase import SupabaseTransport
from app.sync.worker import SyncWorker

router = APIRouter(prefix="/sync", tags=["Synchronization"])


def _store(request: Request):
    return getattr(request.app.state, "credential_store", CredentialStore())


def _credentials(request: Request) -> tuple[str, str, str] | None:
    try:
        store = _store(request)
        values = (
            store.get_secret("supabase-url"),
            store.get_secret("supabase-anon-key"),
            store.get_secret("supabase-access-token"),
        )
    except (CredentialStoreError, AttributeError):
        return None
    if not all(values):
        return None
    return values


@router.get("/status", response_model=SyncStatusResponse)
def get_sync_status(
    request: Request,
    session: Session = Depends(get_session),
) -> SyncStatusResponse:
    pending = session.scalar(
        select(func.count()).select_from(SyncEvent).where(
            SyncEvent.status == "pending"
        )
    ) or 0
    conflicts = session.scalar(
        select(func.count()).select_from(SyncConflict).where(
            SyncConflict.status == "open"
        )
    ) or 0
    last_state = session.get(SyncState, "last_synced_at")
    configured = _credentials(request) is not None
    state = "conflict" if conflicts else ("synced" if configured else "offline")
    return SyncStatusResponse(
        state=state,
        pending=pending,
        conflicts=conflicts,
        last_synced_at=(
            datetime.fromisoformat(last_state.value) if last_state else None
        ),
    )


@router.post("/run")
def run_sync(
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    credentials = _credentials(request)
    if credentials is None:
        raise HTTPException(status_code=409, detail="Supabase is not configured")
    result = SyncWorker(
        session,
        SupabaseTransport(*credentials),
    ).run_once()
    return {
        "pushed": result.pushed,
        "pulled": result.pulled,
        "cursor": result.cursor,
    }
