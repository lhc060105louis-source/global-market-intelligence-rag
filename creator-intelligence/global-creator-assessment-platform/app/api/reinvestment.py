from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.reinvestment import (
    get_action_tracking,
    get_asset_archive,
    get_asset_overview,
    get_governance,
    get_portfolio_plan,
    get_reinvestment_evaluation,
    save_evaluation_approval,
    select_portfolio_scenario,
    update_action_status,
    update_governance,
)

router = APIRouter(prefix="/reinvestment", tags=["Reinvestment"])


class DecisionPayload(BaseModel):
    decision: str
    note: str | None = None


class ScenarioPayload(BaseModel):
    scenario_id: str


class GovernancePayload(BaseModel):
    status: str
    reason: str
    scope: str | None = None
    review_at: str | None = None


class TaskPayload(BaseModel):
    status: str


@router.get("/overview")
def overview(
    country: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    return get_asset_overview(session, country, platform, status)


@router.get("/archives/{kol_key}")
def archive(kol_key: str, session: Session = Depends(get_session)) -> dict:
    data = get_asset_archive(session, kol_key)
    if data is None:
        raise HTTPException(status_code=404, detail="No partnership history found for this creator")
    return data


@router.get("/evaluations/{kol_key}")
def evaluation(kol_key: str, session: Session = Depends(get_session)) -> dict:
    data = get_reinvestment_evaluation(session, kol_key)
    if data is None:
        raise HTTPException(status_code=404, detail="No reinvestment assessment found for this creator")
    return data


@router.post("/evaluations/{kol_key}/approval")
def save_approval(kol_key: str, payload: DecisionPayload, session: Session = Depends(get_session)) -> dict:
    try:
        return save_evaluation_approval(session, kol_key, payload.decision, payload.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/portfolio")
def portfolio(session: Session = Depends(get_session)) -> dict:
    return get_portfolio_plan(session)


@router.post("/portfolio/select")
def choose_portfolio(payload: ScenarioPayload, session: Session = Depends(get_session)) -> dict:
    try:
        return select_portfolio_scenario(session, payload.scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/governance")
def governance(session: Session = Depends(get_session)) -> dict:
    return get_governance(session)


@router.post("/governance/{kol_key}")
def save_governance(kol_key: str, payload: GovernancePayload, session: Session = Depends(get_session)) -> dict:
    try:
        return update_governance(
            session,
            kol_key,
            payload.status,
            payload.reason,
            payload.scope,
            payload.review_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/actions")
def actions(session: Session = Depends(get_session)) -> dict:
    return get_action_tracking(session)


@router.post("/actions/{task_code}")
def save_action(task_code: str, payload: TaskPayload, session: Session = Depends(get_session)) -> dict:
    try:
        return update_action_status(session, task_code, payload.status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
