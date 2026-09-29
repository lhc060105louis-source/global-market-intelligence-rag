from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.campaign_schemas import (
    CampaignCreate,
    CampaignPatch,
    DecisionPayload,
    EntityLinkPayload,
    KolRequirementsPayload,
    MeasurementPlanPayload,
    PublishPayload,
    StrategyPayload,
    VersionedAction,
)
from app.database import get_session
from app.models import CampaignHandoff
from app.services.campaigns import (
    CampaignConflictError,
    CampaignValidationError,
    archive_campaign,
    create_campaign,
    decide_campaign,
    get_campaign,
    link_entity,
    list_campaigns,
    publish_campaign,
    restore_campaign,
    serialize_campaign,
    serialize_handoff,
    submit_campaign,
    update_basic,
    update_kol_requirements,
    update_measurement_plan,
    update_strategy,
    validate_campaign,
)


router = APIRouter(prefix="/campaigns", tags=["Campaign setup"])


def _require_campaign(session: Session, campaign_id: str):
    campaign = get_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return campaign


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, CampaignValidationError):
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "issues": exc.issues},
        ) from exc
    if isinstance(exc, CampaignConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.get("")
def campaigns(
    q: str = Query(default="", max_length=100),
    brand: str = Query(default="", max_length=20),
    market: str = Query(default="", max_length=2),
    status: str = Query(default="", max_length=30),
    include_archived: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> dict:
    records = list_campaigns(
        session,
        query=q,
        brand=brand,
        market=market,
        status=status,
        include_archived=include_archived,
    )
    return {
        "total": len(records),
        "items": [serialize_campaign(session, item) for item in records],
    }


@router.post("", status_code=201)
def create(payload: CampaignCreate, session: Session = Depends(get_session)) -> dict:
    try:
        campaign = create_campaign(session, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.get("/{campaign_id}")
def detail(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    return serialize_campaign(
        session, _require_campaign(session, campaign_id), include_detail=True
    )


@router.patch("/{campaign_id}")
def patch_basic(
    campaign_id: str,
    payload: CampaignPatch,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        update_basic(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.put("/{campaign_id}/strategy")
def save_strategy(
    campaign_id: str,
    payload: StrategyPayload,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        update_strategy(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.put("/{campaign_id}/measurement-plan")
def save_measurement_plan(
    campaign_id: str,
    payload: MeasurementPlanPayload,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        update_measurement_plan(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.put("/{campaign_id}/kol-requirements")
def save_kol_requirements(
    campaign_id: str,
    payload: KolRequirementsPayload,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        update_kol_requirements(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.post("/{campaign_id}/validate")
def validate(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    return validate_campaign(session, _require_campaign(session, campaign_id))


@router.post("/{campaign_id}/submit")
def submit(
    campaign_id: str,
    payload: VersionedAction,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        submit_campaign(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.post("/{campaign_id}/decision")
def decision(
    campaign_id: str,
    payload: DecisionPayload,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        decide_campaign(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.post("/{campaign_id}/publish")
def publish(
    campaign_id: str,
    payload: PublishPayload,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        records = publish_campaign(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return {
        "campaign_id": campaign.campaign_id,
        "version_number": campaign.approved_version,
        "items": [serialize_handoff(item) for item in records],
    }


@router.post("/{campaign_id}/archive")
def archive(
    campaign_id: str,
    payload: VersionedAction,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        archive_campaign(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.post("/{campaign_id}/restore")
def restore(
    campaign_id: str,
    payload: VersionedAction,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    try:
        restore_campaign(session, campaign, payload)
    except (PermissionError, CampaignValidationError, CampaignConflictError) as exc:
        _raise_service_error(exc)
    return serialize_campaign(session, campaign, include_detail=True)


@router.post("/{campaign_id}/links")
def save_link(
    campaign_id: str,
    payload: EntityLinkPayload,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    record = link_entity(session, campaign, payload)
    return {
        "campaign_id": campaign.campaign_id,
        "entity_type": record.entity_type,
        "entity_id": record.entity_id,
        "linked_version": record.linked_version,
    }


@router.get("/{campaign_id}/handoffs/{target_module}")
def handoff_context(
    campaign_id: str,
    target_module: str,
    session: Session = Depends(get_session),
) -> dict:
    campaign = _require_campaign(session, campaign_id)
    record = session.scalar(
        select(CampaignHandoff)
        .where(
            CampaignHandoff.campaign_pk == campaign.id,
            CampaignHandoff.target_module == target_module,
        )
        .order_by(CampaignHandoff.version_number.desc())
    )
    if record is None:
        raise HTTPException(status_code=404, detail="该下游模块尚无已发布交接包")
    return serialize_handoff(record)
