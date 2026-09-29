from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Kol, PerformanceReview
from app.schemas import PerformanceReviewResponse, PerformanceReviewWrite
from app.sync.outbox import record_mutation

router = APIRouter(prefix="/kols", tags=["Performance reviews"])


def _require_kol(session: Session, kol_id: int) -> None:
    if session.get(Kol, kol_id) is None:
        raise HTTPException(status_code=404, detail="KOL not found")


@router.post(
    "/{kol_id}/reviews",
    response_model=PerformanceReviewResponse,
    status_code=201,
)
def create_review(
    kol_id: int,
    payload: PerformanceReviewWrite,
    session: Session = Depends(get_session),
) -> PerformanceReview:
    _require_kol(session, kol_id)
    review = PerformanceReview(kol_id=kol_id, **payload.model_dump())
    session.add(review)
    session.flush()
    record_mutation(session, review, "upsert")
    session.commit()
    session.refresh(review)
    return review


@router.get(
    "/{kol_id}/reviews",
    response_model=list[PerformanceReviewResponse],
)
def list_reviews(
    kol_id: int,
    session: Session = Depends(get_session),
) -> list[PerformanceReview]:
    _require_kol(session, kol_id)
    return list(
        session.scalars(
            select(PerformanceReview)
            .where(
                PerformanceReview.kol_id == kol_id,
                PerformanceReview.deleted_at.is_(None),
            )
            .order_by(PerformanceReview.created_at.desc())
        )
    )
