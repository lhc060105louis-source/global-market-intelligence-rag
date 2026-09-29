from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
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
from app.models import (
    Campaign,
    CampaignApproval,
    CampaignEntityLink,
    CampaignHandoff,
    CampaignVersion,
)


MARKET_DEFAULTS = {
    "DE": {"currency": "EUR", "timezone": "Europe/Berlin"},
    "GB": {"currency": "GBP", "timezone": "Europe/London"},
}
EDIT_ROLES = {"project_owner", "business_analyst", "content_media"}
SUBMIT_ROLES = {"project_owner", "business_analyst"}
PUBLISH_ROLES = {"project_owner"}
TARGET_LABELS = {
    "kol_screening": "KOL筛选",
    "shortlists": "候选名单",
    "contracts": "合同管理",
    "monitoring": "中期内容监控",
    "post_campaign": "后期效果复盘",
    "reinvestment": "资产与复投",
}


class CampaignConflictError(ValueError):
    pass


class CampaignValidationError(ValueError):
    def __init__(self, issues: list[dict]):
        super().__init__("项目配置未通过审批前校验")
        self.issues = issues


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_role(role: str, allowed: set[str], action: str) -> None:
    if role not in allowed:
        raise PermissionError(f"当前角色无权{action}")


def _campaign_code() -> str:
    return f"CMP-{_now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def get_campaign(session: Session, campaign_id: str) -> Campaign | None:
    return session.scalar(select(Campaign).where(Campaign.campaign_id == campaign_id))


def _current_version(session: Session, campaign: Campaign) -> CampaignVersion:
    version = session.scalar(
        select(CampaignVersion).where(
            CampaignVersion.campaign_pk == campaign.id,
            CampaignVersion.version_number == campaign.current_version,
        )
    )
    if version is None:
        raise RuntimeError("项目当前版本不存在")
    return version


def _version(session: Session, campaign: Campaign, number: int) -> CampaignVersion | None:
    return session.scalar(
        select(CampaignVersion).where(
            CampaignVersion.campaign_pk == campaign.id,
            CampaignVersion.version_number == number,
        )
    )


def _basic_snapshot(campaign: Campaign, milestones: list[dict] | None = None) -> dict:
    return {
        "project_name": campaign.project_name,
        "campaign_code": campaign.campaign_code,
        "brand": campaign.brand,
        "vehicle_model": campaign.vehicle_model,
        "markets": list(campaign.markets or []),
        "primary_market": campaign.primary_market,
        "objectives": list(campaign.objectives or []),
        "start_date": campaign.start_date.isoformat(),
        "end_date": campaign.end_date.isoformat(),
        "timezone": campaign.timezone,
        "currency": campaign.currency,
        "budget_total": campaign.budget_total,
        "owner": campaign.owner,
        "collaborators": list(campaign.collaborators or []),
        "milestones": milestones or [],
    }


def _new_snapshot(campaign: Campaign, milestones: list[dict]) -> dict:
    return {
        "basic": _basic_snapshot(campaign, milestones),
        "strategy": {
            "audiences": [],
            "platforms": [],
            "content_formats": [],
            "message_pillars": [],
            "prohibited_claims": [],
            "cta": None,
            "disclosure_rule": None,
            "usage_rights_need": None,
            "competitor_exclusivity": None,
            "risk_reviewer": None,
        },
        "measurement_plan": {"items": []},
        "kol_requirements": {"roles": [], "budget_items": []},
    }


def _check_revision(campaign: Campaign, expected_revision: int) -> None:
    if campaign.revision != expected_revision:
        raise CampaignConflictError(
            f"版本冲突：页面版本为{expected_revision}，当前版本为{campaign.revision}"
        )


def _ensure_editable_version(
    session: Session, campaign: Campaign, actor: str
) -> CampaignVersion:
    if campaign.status == "archived":
        raise CampaignConflictError("已归档项目需要恢复后才能编辑")
    if campaign.status == "pending_approval":
        raise CampaignConflictError("待审批版本已锁定，不能直接编辑")
    current = _current_version(session, campaign)
    if campaign.status in {"approved", "executing", "completed"} or current.is_frozen:
        next_number = max(version.version_number for version in campaign.versions) + 1
        current = CampaignVersion(
            campaign_pk=campaign.id,
            version_number=next_number,
            status="draft",
            snapshot=dict(current.snapshot or {}),
            change_summary={"source_version": campaign.approved_version},
            is_frozen=False,
            created_by=actor,
        )
        session.add(current)
        campaign.current_version = next_number
        campaign.status = "draft"
        session.flush()
    return current


def _save_snapshot(
    session: Session,
    campaign: Campaign,
    version: CampaignVersion,
    snapshot: dict,
) -> None:
    version.snapshot = snapshot
    campaign.revision += 1
    campaign.updated_at = _now()
    session.add_all([campaign, version])
    session.commit()
    session.refresh(campaign)


def create_campaign(session: Session, payload: CampaignCreate) -> Campaign:
    _require_role(payload.actor_role, EDIT_ROLES, "新建项目")
    if payload.campaign_code:
        duplicate = session.scalar(
            select(Campaign.id).where(Campaign.campaign_code == payload.campaign_code)
        )
        if duplicate is not None:
            raise CampaignConflictError("业务项目编号已存在")
    defaults = MARKET_DEFAULTS[payload.primary_market]
    campaign = Campaign(
        campaign_id=_campaign_code(),
        campaign_code=payload.campaign_code or None,
        project_name=payload.project_name,
        brand=payload.brand,
        vehicle_model=payload.vehicle_model,
        markets=list(payload.markets),
        primary_market=payload.primary_market,
        objectives=list(payload.objectives),
        start_date=payload.start_date,
        end_date=payload.end_date,
        timezone=payload.timezone or defaults["timezone"],
        currency=payload.currency or defaults["currency"],
        budget_total=payload.budget_total,
        owner=payload.owner,
        collaborators=list(payload.collaborators),
        status="draft",
        revision=1,
        current_version=1,
    )
    session.add(campaign)
    session.flush()
    session.add(
        CampaignVersion(
            campaign_pk=campaign.id,
            version_number=1,
            status="draft",
            snapshot=_new_snapshot(
                campaign, [item.model_dump(mode="json") for item in payload.milestones]
            ),
            change_summary={"created": True},
            is_frozen=False,
            created_by=payload.actor,
        )
    )
    session.commit()
    session.refresh(campaign)
    return campaign


def list_campaigns(
    session: Session,
    *,
    query: str = "",
    brand: str = "",
    market: str = "",
    status: str = "",
    include_archived: bool = False,
) -> list[Campaign]:
    statement = select(Campaign)
    if not include_archived:
        statement = statement.where(Campaign.status != "archived")
    if query.strip():
        token = f"%{query.strip()}%"
        statement = statement.where(
            or_(Campaign.project_name.like(token), Campaign.campaign_id.like(token))
        )
    if brand:
        statement = statement.where(Campaign.brand == brand)
    if status:
        statement = statement.where(Campaign.status == status)
    records = list(session.scalars(statement.order_by(Campaign.updated_at.desc())))
    if market:
        records = [item for item in records if market in (item.markets or [])]
    return records


def update_basic(
    session: Session, campaign: Campaign, payload: CampaignPatch
) -> Campaign:
    _require_role(payload.actor_role, EDIT_ROLES, "编辑项目")
    _check_revision(campaign, payload.expected_revision)
    version = _ensure_editable_version(session, campaign, payload.actor)
    values = payload.model_dump(
        exclude={"expected_revision", "actor", "actor_role", "milestones"},
        exclude_none=True,
    )
    old_primary = campaign.primary_market
    for field, value in values.items():
        setattr(campaign, field, value)
    if campaign.primary_market not in campaign.markets:
        raise CampaignValidationError([
            _issue("M2", "primary_market", "primary_market_not_selected", "主市场必须属于目标市场")
        ])
    if campaign.start_date > campaign.end_date:
        raise CampaignValidationError([
            _issue("M2", "start_date", "invalid_project_period", "项目开始日期不得晚于结束日期")
        ])
    if campaign.primary_market != old_primary:
        defaults = MARKET_DEFAULTS[campaign.primary_market]
        if payload.currency is None:
            campaign.currency = defaults["currency"]
        if payload.timezone is None:
            campaign.timezone = defaults["timezone"]
    snapshot = dict(version.snapshot or {})
    prior_basic = dict(snapshot.get("basic") or {})
    milestones = (
        [item.model_dump(mode="json") for item in payload.milestones]
        if payload.milestones is not None
        else list(prior_basic.get("milestones") or [])
    )
    snapshot["basic"] = _basic_snapshot(campaign, milestones)
    _save_snapshot(session, campaign, version, snapshot)
    return campaign


def update_strategy(
    session: Session, campaign: Campaign, payload: StrategyPayload
) -> Campaign:
    _require_role(payload.actor_role, EDIT_ROLES, "编辑受众与内容策略")
    _check_revision(campaign, payload.expected_revision)
    version = _ensure_editable_version(session, campaign, payload.actor)
    data = payload.model_dump(
        mode="json", exclude={"expected_revision", "actor", "actor_role"}
    )
    outside = [item["name"] for item in data["audiences"] if item["market"] not in campaign.markets]
    if outside:
        raise CampaignValidationError([
            _issue("M3", "audiences", "audience_market_out_of_scope", "受众市场必须属于项目目标市场")
        ])
    snapshot = dict(version.snapshot or {})
    snapshot["strategy"] = data
    _save_snapshot(session, campaign, version, snapshot)
    return campaign


def update_measurement_plan(
    session: Session, campaign: Campaign, payload: MeasurementPlanPayload
) -> Campaign:
    _require_role(payload.actor_role, EDIT_ROLES, "编辑KPI测量方案")
    _check_revision(campaign, payload.expected_revision)
    version = _ensure_editable_version(session, campaign, payload.actor)
    snapshot = dict(version.snapshot or {})
    snapshot["measurement_plan"] = {
        "items": [item.model_dump(mode="json") for item in payload.items]
    }
    _save_snapshot(session, campaign, version, snapshot)
    return campaign


def update_kol_requirements(
    session: Session, campaign: Campaign, payload: KolRequirementsPayload
) -> Campaign:
    _require_role(payload.actor_role, EDIT_ROLES, "编辑KOL需求与预算")
    _check_revision(campaign, payload.expected_revision)
    version = _ensure_editable_version(session, campaign, payload.actor)
    strategy = (version.snapshot or {}).get("strategy") or {}
    errors: list[dict] = []
    for role in payload.roles:
        if role.market not in campaign.markets:
            errors.append(_issue("M5", "roles", "role_market_out_of_scope", f"{role.role_name}的市场不在项目范围内"))
        if strategy.get("platforms") and role.platform not in strategy["platforms"]:
            errors.append(_issue("M5", "roles", "role_platform_out_of_scope", f"{role.role_name}的平台未在M3策略中配置"))
    if errors:
        raise CampaignValidationError(errors)
    snapshot = dict(version.snapshot or {})
    snapshot["kol_requirements"] = {
        "roles": [item.model_dump(mode="json") for item in payload.roles],
        "budget_items": [item.model_dump(mode="json") for item in payload.budget_items],
    }
    _save_snapshot(session, campaign, version, snapshot)
    return campaign


def _issue(page: str, field: str, code: str, message: str, severity: str = "error") -> dict:
    return {"page": page, "field": field, "code": code, "message": message, "severity": severity}


def validate_campaign(session: Session, campaign: Campaign) -> dict:
    version = _current_version(session, campaign)
    snapshot = version.snapshot or {}
    basic = snapshot.get("basic") or {}
    strategy = snapshot.get("strategy") or {}
    measurement = snapshot.get("measurement_plan") or {}
    requirements = snapshot.get("kol_requirements") or {}
    errors: list[dict] = []
    warnings: list[dict] = []

    required_basic = {
        "project_name": "项目名称", "brand": "服务品牌", "vehicle_model": "传播车型",
        "markets": "目标市场", "primary_market": "主市场", "start_date": "开始日期",
        "end_date": "结束日期", "currency": "币种", "owner": "负责人",
    }
    for field, label in required_basic.items():
        if not basic.get(field):
            errors.append(_issue("M2", field, "required", f"{label}不能为空"))
    milestones = basic.get("milestones") or []
    dates = [item.get("planned_date") for item in milestones if item.get("planned_date")]
    if dates != sorted(dates):
        errors.append(_issue("M2", "milestones", "milestone_order", "里程碑日期顺序不合理"))

    audiences = strategy.get("audiences") or []
    if not audiences:
        errors.append(_issue("M3", "audiences", "audience_required", "至少配置一个核心受众"))
    elif not any(item.get("priority") == "core" for item in audiences):
        errors.append(_issue("M3", "audiences", "core_audience_required", "至少一个受众必须标记为核心"))
    for field, label in (("platforms", "目标平台"), ("content_formats", "内容形式")):
        if not strategy.get(field):
            errors.append(_issue("M3", field, "required", f"至少配置一项{label}"))
    if not strategy.get("cta"):
        errors.append(_issue("M3", "cta", "required", "必须配置CTA"))
    if not strategy.get("disclosure_rule"):
        errors.append(_issue("M3", "disclosure_rule", "required", "必须配置商业合作披露规则"))
    if not strategy.get("prohibited_claims"):
        errors.append(_issue("M3", "prohibited_claims", "required", "必须配置禁止或待确认表述"))
    if not strategy.get("risk_reviewer"):
        errors.append(_issue("M3", "risk_reviewer", "required", "必须指定风险合规复核人"))

    metrics = measurement.get("items") or []
    if not metrics:
        errors.append(_issue("M4", "items", "kpi_required", "至少配置一个KPI"))
    if metrics and not any(item.get("is_primary") for item in metrics):
        errors.append(_issue("M4", "items", "primary_kpi_required", "至少一个KPI必须标记为核心指标"))
    for index, item in enumerate(metrics):
        for field in ("formula", "data_source", "observation_window", "owner"):
            if not item.get(field):
                errors.append(_issue("M4", f"items.{index}.{field}", "kpi_not_measurable", f"KPI {item.get('name') or index + 1}缺少{field}"))
        if item.get("data_status") == "pending":
            warnings.append(_issue("M4", f"items.{index}.data_source", "data_source_pending", f"KPI {item.get('name')}的数据源待接入", "warning"))

    roles = requirements.get("roles") or []
    if not roles:
        errors.append(_issue("M5", "roles", "kol_role_required", "至少配置一个KOL角色需求"))
    if any(not item.get("risk_threshold") for item in roles):
        errors.append(_issue("M5", "roles", "risk_threshold_required", "每个KOL角色必须配置风险门槛"))
    budget_items = requirements.get("budget_items") or []
    allocated = sum(float(item.get("amount") or 0) for item in budget_items)
    if allocated > campaign.budget_total:
        errors.append(_issue("M5", "budget_items", "budget_exceeded", f"分项预算超出总预算{allocated - campaign.budget_total:.2f} {campaign.currency}"))
    if not budget_items:
        warnings.append(_issue("M5", "budget_items", "budget_items_missing", "尚未配置分项预算", "warning"))
    if allocated and campaign.budget_total and allocated / campaign.budget_total > 0.7:
        largest = max((float(item.get("amount") or 0) for item in budget_items), default=0)
        if largest / campaign.budget_total > 0.7:
            warnings.append(_issue("M5", "budget_items", "budget_concentration", "单一预算项超过总预算的70%，建议复核集中度", "warning"))

    return {
        "valid": not errors,
        "campaign_id": campaign.campaign_id,
        "version_number": version.version_number,
        "revision": campaign.revision,
        "errors": errors,
        "warnings": warnings,
        "completion": _completion(snapshot),
    }


def _completion(snapshot: dict) -> int:
    sections = [
        bool((snapshot.get("basic") or {}).get("project_name")),
        bool((snapshot.get("strategy") or {}).get("audiences")),
        bool((snapshot.get("measurement_plan") or {}).get("items")),
        bool((snapshot.get("kol_requirements") or {}).get("roles")),
    ]
    return round(sum(sections) / len(sections) * 100)


def submit_campaign(
    session: Session, campaign: Campaign, payload: VersionedAction
) -> Campaign:
    _require_role(payload.actor_role, SUBMIT_ROLES, "提交审批")
    _check_revision(campaign, payload.expected_revision)
    if campaign.status != "draft":
        raise CampaignConflictError("只有草稿项目可以提交审批")
    result = validate_campaign(session, campaign)
    if not result["valid"]:
        raise CampaignValidationError(result["errors"])
    version = _current_version(session, campaign)
    version.status = "submitted"
    version.is_frozen = True
    version.submitted_at = _now()
    campaign.status = "pending_approval"
    campaign.revision += 1
    session.add(
        CampaignApproval(
            campaign_pk=campaign.id,
            version_number=version.version_number,
            action="submitted",
            actor=payload.actor,
            actor_role=payload.actor_role,
        )
    )
    session.commit()
    session.refresh(campaign)
    return campaign


def decide_campaign(
    session: Session, campaign: Campaign, payload: DecisionPayload
) -> Campaign:
    _require_role(payload.actor_role, {"brand_owner"}, "审批项目")
    _check_revision(campaign, payload.expected_revision)
    if campaign.status != "pending_approval":
        raise CampaignConflictError("项目当前不在待审批状态")
    if payload.decision in {"return", "reject"} and not (payload.reason or "").strip():
        raise CampaignValidationError([
            _issue("M6", "reason", "decision_reason_required", "退回或不批准必须填写原因")
        ])
    version = _current_version(session, campaign)
    strategy = (version.snapshot or {}).get("strategy") or {}
    compliance_required = bool(
        strategy.get("prohibited_claims") or strategy.get("disclosure_rule")
    )
    if payload.decision == "approve" and compliance_required and not payload.risk_signoff:
        raise CampaignConflictError("该项目包含合规限制，批准前需要风险合规会签")

    session.add(
        CampaignApproval(
            campaign_pk=campaign.id,
            version_number=version.version_number,
            action=payload.decision,
            actor=payload.actor,
            actor_role=payload.actor_role,
            reason=payload.reason,
            risk_signoff=payload.risk_signoff,
        )
    )
    if payload.decision == "approve":
        version.status = "approved"
        version.approved_at = _now()
        campaign.status = "approved"
        campaign.approved_version = version.version_number
    else:
        version.status = "returned" if payload.decision == "return" else "rejected"
        version.is_frozen = True
        next_number = max(item.version_number for item in campaign.versions) + 1
        session.add(
            CampaignVersion(
                campaign_pk=campaign.id,
                version_number=next_number,
                status="draft",
                snapshot=dict(version.snapshot or {}),
                change_summary={"source_version": version.version_number, "reason": payload.reason},
                is_frozen=False,
                created_by=payload.actor,
            )
        )
        campaign.current_version = next_number
        campaign.status = "draft"
    campaign.revision += 1
    session.commit()
    session.refresh(campaign)
    return campaign


def _handoff_payload(campaign: Campaign, version: CampaignVersion, target: str) -> dict:
    snapshot = version.snapshot or {}
    common = {
        "campaign_id": campaign.campaign_id,
        "project_version": version.version_number,
        "project_name": campaign.project_name,
        "brand": campaign.brand,
        "vehicle_model": campaign.vehicle_model,
        "markets": campaign.markets,
        "primary_market": campaign.primary_market,
        "currency": campaign.currency,
        "budget_total": campaign.budget_total,
    }
    strategy = snapshot.get("strategy") or {}
    measurement = snapshot.get("measurement_plan") or {}
    requirements = snapshot.get("kol_requirements") or {}
    basic = snapshot.get("basic") or {}
    if target in {"kol_screening", "shortlists"}:
        common.update({"audiences": strategy.get("audiences", []), "platforms": strategy.get("platforms", []), "kol_requirements": requirements.get("roles", [])})
    elif target == "contracts":
        common.update({"content_formats": strategy.get("content_formats", []), "usage_rights_need": strategy.get("usage_rights_need"), "competitor_exclusivity": strategy.get("competitor_exclusivity")})
    elif target == "monitoring":
        common.update({"message_pillars": strategy.get("message_pillars", []), "prohibited_claims": strategy.get("prohibited_claims", []), "cta": strategy.get("cta"), "disclosure_rule": strategy.get("disclosure_rule"), "milestones": basic.get("milestones", [])})
    elif target == "post_campaign":
        common.update({"measurement_plan": measurement.get("items", []), "objectives": campaign.objectives})
    elif target == "reinvestment":
        common.update({"objectives": campaign.objectives, "kol_requirements": requirements.get("roles", [])})
    return common


def publish_campaign(
    session: Session, campaign: Campaign, payload: PublishPayload
) -> list[CampaignHandoff]:
    _require_role(payload.actor_role, PUBLISH_ROLES, "发布项目交接包")
    version_number = payload.version_number or campaign.approved_version
    if version_number is None:
        raise CampaignConflictError("项目尚无已批准版本")
    version = _version(session, campaign, version_number)
    if version is None or version.status != "approved":
        raise CampaignConflictError("只能发布已批准版本")
    results: list[CampaignHandoff] = []
    for target in dict.fromkeys(payload.targets):
        record = session.scalar(
            select(CampaignHandoff).where(
                CampaignHandoff.campaign_pk == campaign.id,
                CampaignHandoff.version_number == version_number,
                CampaignHandoff.target_module == target,
            )
        )
        if record is None:
            record = CampaignHandoff(
                campaign_pk=campaign.id,
                version_number=version_number,
                target_module=target,
                status="published",
                payload=_handoff_payload(campaign, version, target),
                attempts=1,
                published_by=payload.actor,
            )
            session.add(record)
        else:
            record.attempts += 1
            record.status = "published"
            record.error = None
            record.payload = _handoff_payload(campaign, version, target)
            record.published_by = payload.actor
            record.published_at = _now()
        results.append(record)
    session.commit()
    for record in results:
        session.refresh(record)
    return results


def archive_campaign(session: Session, campaign: Campaign, payload: VersionedAction) -> Campaign:
    _require_role(payload.actor_role, {"project_owner"}, "归档项目")
    _check_revision(campaign, payload.expected_revision)
    campaign.status = "archived"
    campaign.archived_at = _now()
    campaign.revision += 1
    session.commit()
    session.refresh(campaign)
    return campaign


def restore_campaign(session: Session, campaign: Campaign, payload: VersionedAction) -> Campaign:
    _require_role(payload.actor_role, {"project_owner"}, "恢复项目")
    _check_revision(campaign, payload.expected_revision)
    if campaign.status != "archived":
        raise CampaignConflictError("项目当前未归档")
    current = _current_version(session, campaign)
    campaign.status = "approved" if current.status == "approved" else "draft"
    campaign.archived_at = None
    campaign.revision += 1
    session.commit()
    session.refresh(campaign)
    return campaign


def link_entity(
    session: Session, campaign: Campaign, payload: EntityLinkPayload
) -> CampaignEntityLink:
    version_number = payload.version_number or campaign.approved_version or campaign.current_version
    record = session.scalar(
        select(CampaignEntityLink).where(
            CampaignEntityLink.campaign_pk == campaign.id,
            CampaignEntityLink.entity_type == payload.entity_type,
            CampaignEntityLink.entity_id == payload.entity_id,
        )
    )
    if record is None:
        record = CampaignEntityLink(
            campaign_pk=campaign.id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            linked_version=version_number,
        )
        session.add(record)
    else:
        record.linked_version = version_number
    session.commit()
    session.refresh(record)
    return record


def serialize_campaign(
    session: Session, campaign: Campaign, *, include_detail: bool = False
) -> dict:
    current = _current_version(session, campaign)
    payload = {
        "campaign_id": campaign.campaign_id,
        "campaign_code": campaign.campaign_code,
        "project_name": campaign.project_name,
        "brand": campaign.brand,
        "vehicle_model": campaign.vehicle_model,
        "markets": campaign.markets or [],
        "primary_market": campaign.primary_market,
        "objectives": campaign.objectives or [],
        "start_date": campaign.start_date.isoformat(),
        "end_date": campaign.end_date.isoformat(),
        "timezone": campaign.timezone,
        "currency": campaign.currency,
        "budget_total": campaign.budget_total,
        "owner": campaign.owner,
        "collaborators": campaign.collaborators or [],
        "status": campaign.status,
        "revision": campaign.revision,
        "current_version": campaign.current_version,
        "approved_version": campaign.approved_version,
        "completion": _completion(current.snapshot or {}),
        "updated_at": campaign.updated_at.isoformat(),
        "archived_at": campaign.archived_at.isoformat() if campaign.archived_at else None,
    }
    if include_detail:
        payload["configuration"] = current.snapshot or {}
        payload["versions"] = [
            {
                "version_number": item.version_number,
                "status": item.status,
                "is_frozen": item.is_frozen,
                "created_by": item.created_by,
                "created_at": item.created_at.isoformat(),
                "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
                "approved_at": item.approved_at.isoformat() if item.approved_at else None,
                "change_summary": item.change_summary or {},
            }
            for item in campaign.versions
        ]
        payload["approvals"] = [
            {
                "id": item.id,
                "version_number": item.version_number,
                "action": item.action,
                "actor": item.actor,
                "actor_role": item.actor_role,
                "reason": item.reason,
                "risk_signoff": item.risk_signoff,
                "created_at": item.created_at.isoformat(),
            }
            for item in sorted(campaign.approvals, key=lambda row: row.created_at)
        ]
        payload["handoffs"] = [serialize_handoff(item) for item in campaign.handoffs]
        payload["entity_links"] = [
            {"entity_type": item.entity_type, "entity_id": item.entity_id, "linked_version": item.linked_version}
            for item in campaign.entity_links
        ]
    return payload


def serialize_handoff(record: CampaignHandoff) -> dict:
    return {
        "id": record.id,
        "version_number": record.version_number,
        "target_module": record.target_module,
        "target_label": TARGET_LABELS.get(record.target_module, record.target_module),
        "status": record.status,
        "payload": record.payload or {},
        "attempts": record.attempts,
        "error": record.error,
        "published_by": record.published_by,
        "published_at": record.published_at.isoformat(),
    }
