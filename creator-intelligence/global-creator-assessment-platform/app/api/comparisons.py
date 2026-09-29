from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Kol
from app.schemas import ComparisonRequest, ComparisonResponse

router = APIRouter(prefix="/comparisons", tags=["Comparisons"])


@router.post("", response_model=ComparisonResponse)
def compare_kols(
    payload: ComparisonRequest,
    session: Session = Depends(get_session),
) -> ComparisonResponse:
    unique_ids = list(dict.fromkeys(payload.kol_ids))
    if len(unique_ids) != len(payload.kol_ids):
        raise HTTPException(status_code=422, detail="KOL IDs must be unique")
    kols = list(session.scalars(select(Kol).where(Kol.id.in_(unique_ids))))
    by_id = {kol.id: kol for kol in kols}
    missing = [kol_id for kol_id in unique_ids if kol_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"KOLs not found: {', '.join(map(str, missing))}",
        )
    return ComparisonResponse(items=[by_id[kol_id] for kol_id in unique_ids])
