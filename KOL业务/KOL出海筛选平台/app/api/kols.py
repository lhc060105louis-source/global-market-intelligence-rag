from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import COMMERCIAL_WEIGHTS, RISK_WEIGHTS
from app.assessment import calculate_assessment
from app.database import get_session
from app.identity import find_existing_kol
from app.market import normalize_market
from app.models import Kol, ScoreRecord
from app.schemas import (
    KolDetail,
    AssessmentPreviewRequest,
    KolListItem,
    KolUpdate,
    KolWrite,
    ScoreOverrideRequest,
    YouTubeEnrichmentRequest,
    YouTubeEnrichmentResponse,
    YouTubeLookupRequest,
    YouTubeLookupResponse,
)
from app.services.importer import persist_assessment, refresh_summary
from app.services.search import build_kol_search
from app.sync.outbox import record_mutation
from app.services.youtube_enrichment import (
    fetch_youtube_channel_metadata,
    youtube_lookup_url,
)

router = APIRouter(prefix="/kols", tags=["KOLs"])


def _save_kol(session: Session, kol: Kol, payload: KolWrite | KolUpdate) -> Kol:
    is_new = kol.id is None
    values = payload.model_dump(exclude_unset=isinstance(payload, KolUpdate))
    commercial_inputs = values.pop("commercial_inputs", None)
    risk_inputs = values.pop("risk_inputs", None)
    for field in ("name", "platform_account_id", "handle", "profile_url", "language", "content_categories"):
        if field in values and isinstance(values[field], str):
            values[field] = values[field].strip() or None
    if "country" in values and values["country"] is not None:
        try:
            values["country"] = normalize_market(values["country"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    identity = {
        "platform": values.get("platform", kol.platform),
        "platform_account_id": values.get("platform_account_id", kol.platform_account_id),
        "profile_url": values.get("profile_url", kol.profile_url),
        "handle": values.get("handle", kol.handle),
    }
    if find_existing_kol(session, **identity, exclude_id=kol.id):
        raise HTTPException(status_code=409, detail="KOL channel already exists")
    for field, value in values.items():
        setattr(kol, field, value)
    session.add(kol)
    try:
        session.flush()
        if commercial_inputs is not None or risk_inputs is not None:
            persist_assessment(session, kol, commercial_inputs if commercial_inputs is not None else kol.commercial_inputs, risk_inputs if risk_inputs is not None else kol.risk_inputs, source="kol-form")
        if not is_new:
            kol.version += 1
        record_mutation(session, kol, "upsert")
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="KOL platform account or handle already exists") from exc
    session.refresh(kol)
    return kol


@router.post("", response_model=KolDetail, status_code=201)
def create_kol(payload: KolWrite, session: Session = Depends(get_session)) -> Kol:
    return _save_kol(session, Kol(), payload)


@router.post("/lookup-youtube", response_model=YouTubeLookupResponse)
def lookup_youtube(payload: YouTubeLookupRequest) -> YouTubeLookupResponse:
    entered = payload.profile_url.strip()
    lookup_url = youtube_lookup_url(profile_url=entered, handle=entered, platform_account_id=entered)
    if lookup_url is None:
        raise HTTPException(status_code=422, detail="YouTube URL, handle, or channel ID is invalid")
    metadata = fetch_youtube_channel_metadata(lookup_url)
    return YouTubeLookupResponse(
        name=_text_or_none(metadata.get("channel") or metadata.get("uploader")),
        platform_account_id=_text_or_none(metadata.get("channel_id") or metadata.get("id")),
        profile_url=_text_or_none(metadata.get("channel_url") or metadata.get("webpage_url")) or lookup_url,
        followers=_int_or_none(metadata.get("channel_follower_count") or metadata.get("subscriber_count")),
        description=_text_or_none(metadata.get("description")),
    )


@router.post("/assessment-preview")
def preview_assessment(payload: AssessmentPreviewRequest) -> dict:
    result = calculate_assessment(payload.commercial_inputs, payload.risk_inputs)
    return {"commercial_score": result.commercial_score, "commercial_grade": result.commercial_grade, "risk_score": result.risk_score, "risk_level": result.risk_level, "flags": result.flags}


@router.put("/{kol_id}", response_model=KolDetail)
def update_kol(kol_id: int, payload: KolUpdate, session: Session = Depends(get_session)) -> Kol:
    kol = session.get(Kol, kol_id)
    if kol is None:
        raise HTTPException(status_code=404, detail="KOL not found")
    return _save_kol(session, kol, payload)


@router.get("", response_model=list[KolListItem])
def list_kols(
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
) -> list[Kol]:
    statement = build_kol_search(
        keyword=keyword,
        country=country,
        platform=platform,
        language=language,
        min_followers=min_followers,
        max_followers=max_followers,
        min_commercial_score=min_commercial_score,
        max_risk_score=max_risk_score,
        risk_level=risk_level,
        min_completeness=min_completeness,
    )
    return list(session.scalars(statement))


@router.post("/enrich-youtube", response_model=YouTubeEnrichmentResponse)
def enrich_youtube_kols(
    payload: YouTubeEnrichmentRequest,
    session: Session = Depends(get_session),
) -> YouTubeEnrichmentResponse:
    requested_ids = list(dict.fromkeys(payload.kol_ids))
    if not requested_ids:
        return YouTubeEnrichmentResponse(requested=0, updated=0, skipped=0, failed=0)

    kols = list(session.scalars(select(Kol).where(Kol.id.in_(requested_ids))))
    by_id = {kol.id: kol for kol in kols}
    updated = 0
    skipped = 0
    failed = 0

    for kol_id in requested_ids:
        kol = by_id.get(kol_id)
        if kol is None:
            failed += 1
            continue
        if kol.platform.strip().lower() != "youtube" or kol.followers is not None:
            skipped += 1
            continue

        lookup_url = youtube_lookup_url(
            profile_url=kol.profile_url,
            handle=kol.handle,
            platform_account_id=kol.platform_account_id,
        )
        if lookup_url is None:
            skipped += 1
            continue

        try:
            metadata = fetch_youtube_channel_metadata(lookup_url)
        except Exception:
            failed += 1
            continue

        followers = _int_or_none(metadata.get("channel_follower_count"))
        if followers is None:
            followers = _int_or_none(metadata.get("subscriber_count"))
        if followers is None:
            skipped += 1
            continue

        values = {"followers": followers}
        channel_id = _text_or_none(metadata.get("channel_id") or metadata.get("id"))
        if channel_id:
            values["platform_account_id"] = channel_id
        channel_name = _text_or_none(metadata.get("channel") or metadata.get("uploader"))
        if channel_name:
            values["name"] = channel_name
        channel_url = _text_or_none(metadata.get("channel_url") or metadata.get("webpage_url"))
        if channel_url:
            values["profile_url"] = channel_url
        result = session.execute(update(Kol).where(Kol.id == kol_id).values(**values))
        if result.rowcount == 0:
            failed += 1
            continue
        session.commit()
        updated += 1

    return YouTubeEnrichmentResponse(
        requested=len(requested_ids),
        updated=updated,
        skipped=skipped,
        failed=failed,
    )


@router.get("/{kol_id}", response_model=KolDetail)
def get_kol(kol_id: int, session: Session = Depends(get_session)) -> Kol:
    kol = session.get(Kol, kol_id)
    if kol is None:
        raise HTTPException(status_code=404, detail="KOL not found")
    return kol


@router.post("/{kol_id}/scores", response_model=KolDetail)
def override_score(
    kol_id: int,
    payload: ScoreOverrideRequest,
    session: Session = Depends(get_session),
) -> Kol:
    kol = session.get(Kol, kol_id)
    if kol is None:
        raise HTTPException(status_code=404, detail="KOL not found")

    weights = (
        COMMERCIAL_WEIGHTS
        if payload.score_type == "commercial"
        else RISK_WEIGHTS
        if payload.score_type == "risk"
        else None
    )
    if weights is None or payload.dimension not in weights:
        raise HTTPException(status_code=422, detail="Unknown score type or dimension")

    record = session.scalar(
        select(ScoreRecord).where(
            ScoreRecord.kol_id == kol_id,
            ScoreRecord.score_type == payload.score_type,
            ScoreRecord.dimension == payload.dimension,
        )
    )
    if record is None:
        record = ScoreRecord(
            kol_id=kol_id,
            score_type=payload.score_type,
            dimension=payload.dimension,
        )
        session.add(record)
    record.manual_score = payload.manual_score
    record.manual_evidence = payload.evidence
    record.manual_source = payload.source
    session.flush()
    refresh_summary(session, kol)
    session.commit()
    session.expire(kol)
    return kol


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
