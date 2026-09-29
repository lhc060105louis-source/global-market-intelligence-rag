from sqlalchemy import Select, func, or_, select

from app.models import Kol, KolScoreSummary
from app.market import normalize_market


def build_kol_search(
    *,
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
) -> Select:
    statement = select(Kol).outerjoin(KolScoreSummary)
    if keyword:
        pattern = f"%{keyword.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(Kol.name).like(pattern),
                func.lower(Kol.handle).like(pattern),
                func.lower(Kol.content_categories).like(pattern),
            )
        )
    if country:
        statement = statement.where(Kol.country == normalize_market(country))
    if platform:
        statement = statement.where(
            func.lower(Kol.platform) == platform.strip().lower()
        )
    if language:
        statement = statement.where(func.lower(Kol.language) == language.lower())
    if min_followers is not None:
        statement = statement.where(Kol.followers >= min_followers)
    if max_followers is not None:
        statement = statement.where(Kol.followers <= max_followers)
    if min_commercial_score is not None:
        statement = statement.where(
            KolScoreSummary.commercial_score >= min_commercial_score
        )
    if max_risk_score is not None:
        statement = statement.where(KolScoreSummary.risk_score <= max_risk_score)
    if risk_level:
        statement = statement.where(KolScoreSummary.risk_level == risk_level.lower())
    if min_completeness is not None:
        statement = statement.where(
            KolScoreSummary.commercial_completeness >= min_completeness,
            KolScoreSummary.risk_completeness >= min_completeness,
        )
    return statement.order_by(
        KolScoreSummary.commercial_score.desc().nullslast(),
        KolScoreSummary.risk_score.asc().nullslast(),
        Kol.id,
    )
