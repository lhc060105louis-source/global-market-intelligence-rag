from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.closure_schemas import (
    ClosureActionPayload,
    ClosureChecksPayload,
    ClosureCreate,
    ClosureDecisionPayload,
    ClosureIssueCreate,
    ClosureIssuePatch,
    ClosureSummaryPayload,
)
from app.database import get_session
from app.models import ClosureIssue
from app.services.closures import (
    ClosureConflictError,
    ClosureValidationError,
    archive_payload,
    create_closure,
    create_issue,
    decide_closure,
    get_campaign,
    get_closure,
    list_closure_candidates,
    revise_closure,
    save_summary,
    serialize_closure,
    submit_closure,
    update_checks,
    update_issue,
)


router = APIRouter(prefix="/closures", tags=["Campaign close-out"])


def _require_closure(session: Session, closure_id: str):
    closure = get_closure(session, closure_id)
    if closure is None:
        raise HTTPException(status_code=404, detail="Closure record not found")
    return closure


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ClosureConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ClosureValidationError):
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "issues": exc.issues},
        ) from exc
    raise exc


@router.get("")
def closures(
    q: str = Query(default="", max_length=100),
    brand: str = Query(default="", max_length=20),
    market: str = Query(default="", max_length=2),
    status: str = Query(default="", max_length=30),
    session: Session = Depends(get_session),
) -> dict:
    items = list_closure_candidates(
        session, query=q, brand=brand, market=market, status=status
    )
    return {
        "total": len(items),
        "metrics": {
            "not_ready": sum(item["closure_status"] == "not_ready" for item in items),
            "pending_confirmation": sum(item["closure_status"] == "pending_confirmation" for item in items),
            "closed": sum(item["closure_status"] == "closed" for item in items),
            "blocking": sum(item["blocking_count"] for item in items),
        },
        "items": items,
    }


@router.post("/campaigns/{campaign_id}", status_code=201)
def create(
    campaign_id: str,
    payload: ClosureCreate,
    session: Session = Depends(get_session),
) -> dict:
    campaign = get_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        closure = create_closure(session, campaign, payload.actor, payload.actor_role)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.get("/{closure_id}")
def detail(closure_id: str, session: Session = Depends(get_session)) -> dict:
    return serialize_closure(session, _require_closure(session, closure_id))


@router.put("/{closure_id}/checks")
def save_checks(
    closure_id: str,
    payload: ClosureChecksPayload,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    try:
        update_checks(session, closure, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.post("/{closure_id}/issues", status_code=201)
def add_issue(
    closure_id: str,
    payload: ClosureIssueCreate,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    try:
        issue = create_issue(session, closure, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return {
        "issue": {
            "issue_id": issue.issue_id,
            "title": issue.title,
            "status": issue.status,
        },
        "closure": serialize_closure(session, closure),
    }


@router.patch("/{closure_id}/issues/{issue_id}")
def patch_issue(
    closure_id: str,
    issue_id: str,
    payload: ClosureIssuePatch,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    issue = session.scalar(
        select(ClosureIssue).where(
            ClosureIssue.closure_pk == closure.id,
            ClosureIssue.issue_id == issue_id,
        )
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Open item not found")
    try:
        update_issue(session, closure, issue, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.put("/{closure_id}/summary")
def save_closure_summary(
    closure_id: str,
    payload: ClosureSummaryPayload,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    try:
        save_summary(session, closure, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.post("/{closure_id}/submit")
def submit(
    closure_id: str,
    payload: ClosureActionPayload,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    try:
        submit_closure(session, closure, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.post("/{closure_id}/decision")
def decision(
    closure_id: str,
    payload: ClosureDecisionPayload,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    try:
        decide_closure(session, closure, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.post("/{closure_id}/revise")
def revise(
    closure_id: str,
    payload: ClosureActionPayload,
    session: Session = Depends(get_session),
) -> dict:
    closure = _require_closure(session, closure_id)
    try:
        revise_closure(session, closure, payload)
    except (PermissionError, ClosureConflictError, ClosureValidationError) as exc:
        _raise_service_error(exc)
    return serialize_closure(session, closure)


@router.get("/{closure_id}/archive")
def archive(closure_id: str, session: Session = Depends(get_session)) -> dict:
    return archive_payload(session, _require_closure(session, closure_id))
