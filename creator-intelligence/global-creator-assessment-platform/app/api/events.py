from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Kol, RegulationReview
from app.schemas import (
    KOLRiskAlertResponse,
    RegulationChangeRequest,
    RegulationChangeResult,
    RegulationReviewResponse,
)
from app.shared_contracts import (
    MaterialStatus,
    RegulationChange,
    build_kol_risk_alert,
    regulation_affects_kol,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post(
    "/regulation-changes",
    response_model=RegulationChangeResult,
    status_code=201,
)
def receive_regulation_change(
    payload: RegulationChangeRequest,
    session: Session = Depends(get_session),
) -> RegulationChangeResult:
    change = RegulationChange(**payload.model_dump())
    matched = created = existing = 0

    for kol in session.scalars(select(Kol)):
        if not regulation_affects_kol(change, kol):
            continue
        matched += 1
        prior = session.scalar(
            select(RegulationReview.id).where(
                RegulationReview.kol_id == kol.id,
                RegulationReview.regulation_id == change.regulation_id,
                RegulationReview.published_at == change.published_at,
            )
        )
        if prior is not None:
            existing += 1
            continue
        session.add(
            RegulationReview(
                kol_id=kol.id,
                regulation_id=change.regulation_id,
                regulation_name=change.regulation_name,
                change_type=change.change_type,
                summary=change.summary,
                affected_scenarios=change.affected_scenarios,
                published_at=change.published_at,
                status=MaterialStatus.NEED_UPDATE.value,
            )
        )
        created += 1

    session.commit()
    return RegulationChangeResult(
        matched=matched,
        created=created,
        existing=existing,
    )


@router.get(
    "/regulation-reviews",
    response_model=list[RegulationReviewResponse],
)
def list_regulation_reviews(
    session: Session = Depends(get_session),
) -> list[RegulationReview]:
    return list(
        session.scalars(
            select(RegulationReview).order_by(
                RegulationReview.created_at.desc(),
                RegulationReview.id.desc(),
            )
        )
    )


@router.get(
    "/kol-risk-alerts",
    response_model=list[KOLRiskAlertResponse],
)
def list_kol_risk_alerts(
    session: Session = Depends(get_session),
) -> list[dict]:
    alerts = (
        build_kol_risk_alert(kol)
        for kol in session.scalars(select(Kol))
    )
    return [asdict(alert) for alert in alerts if alert is not None]
