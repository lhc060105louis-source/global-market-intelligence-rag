from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.post_campaign import (
    apply_crisis_action,
    close_crisis,
    get_campaign_overview,
    get_campaign_review,
    get_crisis,
    get_kol_performance,
    get_sentiment_analysis,
    list_crises,
    save_campaign_decision,
    save_crisis_decision,
    serialize_crisis,
)

router = APIRouter(prefix="/post-campaign", tags=["Post campaign"])


class DecisionPayload(BaseModel):
    decision: str
    notes: str | None = None


class CrisisDecisionPayload(BaseModel):
    decision: str


def _require_crisis(session: Session, crisis_code: str):
    crisis = get_crisis(session, crisis_code)
    if crisis is None:
        raise HTTPException(status_code=404, detail="重大风险事件不存在")
    return crisis


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    return get_campaign_overview(session)


@router.get("/kols/{kol_key}")
def kol_detail(kol_key: str, session: Session = Depends(get_session)) -> dict:
    result = get_kol_performance(session, kol_key)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到该 KOL 的合作效果记录")
    return result


@router.get("/sentiment")
def sentiment(session: Session = Depends(get_session)) -> dict:
    return get_sentiment_analysis(session)


@router.get("/review")
def review(session: Session = Depends(get_session)) -> dict:
    return get_campaign_review(session)


@router.post("/review/decision")
def review_decision(payload: DecisionPayload, session: Session = Depends(get_session)) -> dict:
    try:
        review = save_campaign_decision(session, payload.decision, payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"decision": review.decision, "status": review.status, "notes": review.notes}


@router.get("/crises")
def crises(
    include_closed: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> dict:
    records = list_crises(session, include_closed=include_closed)
    return {"total": len(records), "items": [serialize_crisis(item) for item in records]}


@router.get("/crises/{crisis_code}")
def crisis_detail(crisis_code: str, session: Session = Depends(get_session)) -> dict:
    return serialize_crisis(_require_crisis(session, crisis_code), include_detail=True)


@router.post("/crises/{crisis_code}/actions/{action}")
def crisis_action(crisis_code: str, action: str, session: Session = Depends(get_session)) -> dict:
    crisis = _require_crisis(session, crisis_code)
    try:
        apply_crisis_action(session, crisis, action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_crisis(crisis, include_detail=True)


@router.post("/crises/{crisis_code}/decision")
def crisis_decision(
    crisis_code: str,
    payload: CrisisDecisionPayload,
    session: Session = Depends(get_session),
) -> dict:
    crisis = _require_crisis(session, crisis_code)
    try:
        save_crisis_decision(session, crisis, payload.decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_crisis(crisis, include_detail=True)


@router.post("/crises/{crisis_code}/close")
def crisis_close(crisis_code: str, session: Session = Depends(get_session)) -> dict:
    crisis = _require_crisis(session, crisis_code)
    try:
        close_crisis(session, crisis)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_crisis(crisis, include_detail=True)
