from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.exporter import export_kols
from app.services.search import build_kol_search

router = APIRouter(prefix="/exports", tags=["Exports"])


@router.get("/kols.xlsx")
def download_kols(
    keyword: str | None = None,
    country: str | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
    min_commercial_score: float | None = None,
    max_risk_score: float | None = None,
    risk_level: str | None = None,
    min_completeness: float | None = None,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    statement = build_kol_search(
        keyword=keyword, country=country, platform=platform, language=language,
        min_followers=min_followers, max_followers=max_followers,
        min_commercial_score=min_commercial_score, max_risk_score=max_risk_score,
        risk_level=risk_level, min_completeness=min_completeness,
    )
    return StreamingResponse(
        export_kols(list(session.scalars(statement))),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="kols.xlsx"'},
    )
