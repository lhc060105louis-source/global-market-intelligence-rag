from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.monitoring import (
    apply_risk_action,
    approve_task,
    build_overview,
    filter_tasks,
    get_open_risks,
    get_risk,
    get_task,
    list_tasks,
    request_task_changes,
    serialize_risk,
    serialize_task,
)

router = APIRouter(prefix="/monitoring", tags=["Content monitoring"])

def _require_task(session: Session, task_code: str):
    task = get_task(session, task_code)
    if task is None:
        raise HTTPException(status_code=404, detail="Content task not found")
    return task


def _require_risk(session: Session, risk_code: str):
    risk = get_risk(session, risk_code)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk incident not found")
    return risk

@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    return build_overview(session)


@router.get("/tasks")
def tasks(
    q: str = Query(default="", max_length=100),
    stage: str = Query(default="", max_length=50),
    platform: str = Query(default="", max_length=50),
    risk: str = Query(default="", max_length=50),
    session: Session = Depends(get_session),
) -> dict:
    records = filter_tasks(list_tasks(session), query=q, stage=stage, platform=platform, risk=risk)
    return {
        "total": len(records),
        "items": [serialize_task(task) for task in records],
    }


@router.get("/tasks/{task_code}")
def task_detail(task_code: str, session: Session = Depends(get_session)) -> dict:
    task = _require_task(session, task_code)
    risks = [serialize_risk(risk) for risk in task.risks if risk.status != "Closed"]
    payload = serialize_task(task, include_detail=True)
    payload["risks"] = risks
    return payload


@router.post("/tasks/{task_code}/request-changes")
def request_changes(task_code: str, session: Session = Depends(get_session)) -> dict:
    task = _require_task(session, task_code)
    request_task_changes(session, task)
    return serialize_task(task, include_detail=True)


@router.post("/tasks/{task_code}/approve")
def approve(task_code: str, session: Session = Depends(get_session)) -> dict:
    task = _require_task(session, task_code)
    try:
        approve_task(session, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_task(task, include_detail=True)


@router.get("/risks")
def risks(session: Session = Depends(get_session)) -> dict:
    records = get_open_risks(session)
    return {"total": len(records), "items": [serialize_risk(risk) for risk in records]}


@router.get("/risks/{risk_code}")
def risk_detail(risk_code: str, session: Session = Depends(get_session)) -> dict:
    risk = _require_risk(session, risk_code)
    payload = serialize_risk(risk, include_detail=True)
    payload["task"] = serialize_task(risk.task, include_detail=True) if risk.task else None
    return payload


@router.post("/risks/{risk_code}/actions/{action}")
def risk_action(risk_code: str, action: str, session: Session = Depends(get_session)) -> dict:
    risk = get_risk(session, risk_code)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk incident not found")
    try:
        apply_risk_action(session, risk, action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_risk(risk, include_detail=True)
