from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.closure_schemas import (
    ClosureActionPayload,
    ClosureChecksPayload,
    ClosureDecisionPayload,
    ClosureIssueCreate,
    ClosureIssuePatch,
    ClosureSummaryPayload,
)
from app.models import (
    Campaign,
    CampaignClosure,
    CampaignEntityLink,
    CampaignReview,
    ClosureAudit,
    ClosureIssue,
    ContentRiskEvent,
    ContentTask,
    Contract,
    KolCrisisEvent,
    PerformanceReview,
)


EDIT_ROLES = {"project_owner", "business_analyst", "data_owner", "brand_owner", "admin"}
SUBMIT_ROLES = {"project_owner", "business_analyst", "admin"}
DECISION_ROLES = {"brand_owner", "admin"}

STATUS_LABELS = {
    "not_ready": "暂不能结案",
    "draft": "结案草稿",
    "pending_confirmation": "待确认",
    "returned": "已退回",
    "closed": "已结案",
    "revised": "已修订",
}

CHECK_DEFINITIONS = [
    ("project_configuration", "项目配置", True, "项目立项与目标配置"),
    ("contract_delivery", "合同与约定", True, "合同管理"),
    ("content_delivery", "内容发布与验收", True, "中期内容监控"),
    ("risk_events", "风险事件", True, "中期内容监控 / 主体风险"),
    ("performance_data", "效果数据", True, "后期效果复盘"),
    ("project_review", "项目复盘", True, "后期效果复盘"),
    ("asset_archive", "资产沉淀", True, "资产与复投"),
    ("budget_confirmation", "预算确认", True, "项目预算 / 人工确认"),
]


class ClosureConflictError(ValueError):
    pass


class ClosureValidationError(ValueError):
    def __init__(self, message: str, issues: list[dict] | None = None):
        super().__init__(message)
        self.issues = issues or []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{_now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def _require_role(role: str, allowed: set[str], action: str) -> None:
    if role not in allowed:
        raise PermissionError(f"当前角色无权{action}")


def _check_revision(closure: CampaignClosure, expected_revision: int) -> None:
    if closure.revision != expected_revision:
        raise ClosureConflictError(
            f"版本冲突：页面版本为{expected_revision}，当前版本为{closure.revision}"
        )


def get_campaign(session: Session, campaign_id: str) -> Campaign | None:
    return session.scalar(select(Campaign).where(Campaign.campaign_id == campaign_id))


def get_closure(session: Session, closure_id: str) -> CampaignClosure | None:
    return session.scalar(
        select(CampaignClosure).where(CampaignClosure.closure_id == closure_id)
    )


def get_campaign_closure(session: Session, campaign: Campaign) -> CampaignClosure | None:
    return session.scalar(
        select(CampaignClosure).where(CampaignClosure.campaign_pk == campaign.id)
    )


def _automatic_checks(session: Session, campaign: Campaign) -> dict[str, dict]:
    updated_at = campaign.updated_at.isoformat()
    result: dict[str, dict] = {}

    configured = bool(campaign.approved_version) or campaign.status in {
        "approved", "executing", "completed", "archived"
    }
    result["project_configuration"] = {
        "status": "通过" if configured else "待确认",
        "detail": "已读取批准版本" if configured else "项目尚未形成批准版本",
        "updated_at": updated_at,
        "system_blocking": False,
    }

    links = list(
        session.scalars(
            select(CampaignEntityLink).where(
                CampaignEntityLink.campaign_pk == campaign.id,
                CampaignEntityLink.entity_type == "contract",
            )
        )
    )
    contracts: list[Contract] = []
    for link in links:
        if str(link.entity_id).isdigit():
            contract = session.get(Contract, int(link.entity_id))
            if contract is not None and contract.deleted_at is None:
                contracts.append(contract)
    if contracts and all(item.status in {"signed", "completed", "已签署", "已完成"} for item in contracts):
        contract_status, contract_detail = "通过", f"已关联并确认 {len(contracts)} 份合同"
    elif contracts:
        contract_status, contract_detail = "待确认", "存在未签署或未完成的合同记录"
    else:
        contract_status, contract_detail = "待确认", "尚未发现与本项目绑定的合同记录，允许人工核对"
    result["contract_delivery"] = {
        "status": contract_status, "detail": contract_detail,
        "updated_at": updated_at, "system_blocking": False,
    }

    tasks = list(
        session.scalars(select(ContentTask).where(ContentTask.campaign == campaign.project_name))
    )
    completed_stages = {"已发布/监测", "已发布", "已取消"}
    if tasks and all(item.execution_stage in completed_stages for item in tasks):
        content_status, content_detail = "通过", f"{len(tasks)} 条内容任务均已发布或记录取消"
    elif tasks:
        pending = sum(item.execution_stage not in completed_stages for item in tasks)
        content_status, content_detail = "待确认", f"仍有 {pending} 条内容任务未结束"
    else:
        content_status, content_detail = "待确认", "尚未发现与本项目同名的内容任务，需人工核对"
    result["content_delivery"] = {
        "status": content_status, "detail": content_detail,
        "updated_at": max((item.updated_at for item in tasks), default=campaign.updated_at).isoformat(),
        "system_blocking": False,
    }

    task_ids = [item.id for item in tasks]
    risk_events = list(
        session.scalars(
            select(ContentRiskEvent).where(ContentRiskEvent.task_id.in_(task_ids))
        )
    ) if task_ids else []
    kol_ids = {item.kol_id for item in tasks if item.kol_id is not None}
    handles = {item.kol_handle for item in tasks if item.kol_handle}
    crises = list(
        session.scalars(
            select(KolCrisisEvent).where(KolCrisisEvent.status != "已关闭")
        )
    )
    related_crises = [
        item for item in crises
        if item.kol_id in kol_ids or (item.details or {}).get("kol_handle") in handles
    ]
    open_risks = [
        item for item in risk_events
        if item.status not in {"已关闭", "已解决"} and (item.blocked or item.level in {"高风险", "重大"})
    ]
    if open_risks or related_crises:
        risk_status = "阻断"
        risk_detail = f"存在 {len(open_risks) + len(related_crises)} 个未关闭重大风险"
        risk_blocking = True
    elif tasks:
        risk_status, risk_detail, risk_blocking = "通过", "未发现未关闭的重大风险", False
    else:
        risk_status, risk_detail, risk_blocking = "待确认", "缺少可关联的内容任务，需人工核对风险", False
    result["risk_events"] = {
        "status": risk_status, "detail": risk_detail,
        "updated_at": max(
            [item.updated_at for item in risk_events + related_crises] or [campaign.updated_at]
        ).isoformat(),
        "system_blocking": risk_blocking,
    }

    performance = list(
        session.scalars(
            select(PerformanceReview).where(
                PerformanceReview.campaign == campaign.project_name,
                PerformanceReview.deleted_at.is_(None),
            )
        )
    )
    usable = [item for item in performance if any(
        value is not None for value in (item.impressions, item.engagements, item.conversions)
    )]
    result["performance_data"] = {
        "status": "通过" if usable else "待确认",
        "detail": f"已读取 {len(usable)} 条有效效果记录" if usable else "核心KPI尚无可关联记录或缺失原因",
        "updated_at": max((item.updated_at for item in performance), default=campaign.updated_at).isoformat(),
        "system_blocking": False,
    }

    review = session.scalar(
        select(CampaignReview).where(CampaignReview.campaign == campaign.project_name)
    )
    review_ready = review is not None and review.status in {"已确认", "completed", "closed"}
    result["project_review"] = {
        "status": "通过" if review_ready else "待确认",
        "detail": "后期复盘结论已经确认" if review_ready else "后期复盘结论尚未确认或未能关联",
        "updated_at": (review.updated_at if review else campaign.updated_at).isoformat(),
        "system_blocking": False,
    }

    asset_state = session.scalar(
        select(CampaignReview).where(CampaignReview.campaign == "__asset_reinvestment__")
    )
    result["asset_archive"] = {
        "status": "待确认",
        "detail": "资产模块已有运行记录，仍需确认是否已写回本项目" if asset_state else "尚未发现资产沉淀确认记录",
        "updated_at": (asset_state.updated_at if asset_state else campaign.updated_at).isoformat(),
        "system_blocking": False,
    }

    result["budget_confirmation"] = {
        "status": "待确认",
        "detail": f"立项预算为 {campaign.currency} {campaign.budget_total:,.0f}；实际支出需人工确认",
        "updated_at": updated_at,
        "system_blocking": False,
    }
    return result


def build_checks(
    session: Session, campaign: Campaign, closure: CampaignClosure | None = None
) -> list[dict]:
    automatic = _automatic_checks(session, campaign)
    saved = dict((closure.checks if closure else {}) or {})
    rows = []
    for key, label, required, source in CHECK_DEFINITIONS:
        auto = automatic[key]
        manual = dict(saved.get(key) or {})
        status = auto["status"]
        if manual.get("status") and not auto.get("system_blocking"):
            status = manual["status"]
        rows.append({
            "key": key,
            "label": label,
            "required": required,
            "source": source,
            "status": status,
            "automatic_status": auto["status"],
            "detail": manual.get("note") or auto["detail"],
            "updated_at": manual.get("confirmed_at") or auto["updated_at"],
            "confirmed_by": manual.get("confirmed_by"),
            "system_blocking": auto.get("system_blocking", False),
        })
    return rows


def _readiness(checks: list[dict]) -> float:
    required = [item for item in checks if item["required"]]
    passed = sum(item["status"] == "通过" for item in required)
    return round(passed / len(required) * 100, 1) if required else 100.0


def _open_blocking_issues(closure: CampaignClosure | None) -> list[ClosureIssue]:
    if closure is None:
        return []
    return [
        item for item in closure.issues
        if item.severity == "阻断" and item.status != "已解决"
    ]


def _refresh_status(session: Session, closure: CampaignClosure) -> list[dict]:
    checks = build_checks(session, closure.campaign, closure)
    closure.readiness = _readiness(checks)
    if closure.status not in {"pending_confirmation", "closed", "revised"}:
        blocked = any(item["status"] == "阻断" for item in checks) or bool(
            _open_blocking_issues(closure)
        )
        closure.status = "not_ready" if blocked or closure.readiness < 100 else "draft"
    return checks


def _touch(closure: CampaignClosure) -> None:
    closure.revision += 1
    closure.updated_at = _now()


def _snapshot(session: Session, closure: CampaignClosure) -> dict:
    return {
        "closure_id": closure.closure_id,
        "campaign_id": closure.campaign.campaign_id,
        "version": closure.version,
        "status": closure.status,
        "readiness": closure.readiness,
        "checks": build_checks(session, closure.campaign, closure),
        "summary": dict(closure.summary or {}),
        "issues": [serialize_issue(item) for item in closure.issues],
    }


def _audit(
    session: Session,
    closure: CampaignClosure,
    action: str,
    actor: str,
    actor_role: str,
    reason: str | None = None,
    *,
    include_snapshot: bool = False,
) -> None:
    session.add(
        ClosureAudit(
            closure_pk=closure.id,
            action=action,
            actor=actor,
            actor_role=actor_role,
            reason=reason,
            version=closure.version,
            snapshot=_snapshot(session, closure) if include_snapshot else {},
        )
    )


def create_closure(
    session: Session, campaign: Campaign, actor: str, actor_role: str
) -> CampaignClosure:
    _require_role(actor_role, EDIT_ROLES, "创建结案工作区")
    existing = get_campaign_closure(session, campaign)
    if existing is not None:
        return existing
    closure = CampaignClosure(
        closure_id=_new_id("CLS"),
        campaign_pk=campaign.id,
        created_by=actor,
        status="not_ready",
        checks={},
        summary={},
    )
    session.add(closure)
    session.flush()
    _refresh_status(session, closure)
    _audit(session, closure, "created", actor, actor_role)
    session.commit()
    session.refresh(closure)
    return closure


def list_closure_candidates(
    session: Session,
    *,
    query: str = "",
    brand: str = "",
    market: str = "",
    status: str = "",
) -> list[dict]:
    statement = select(Campaign).where(Campaign.status != "archived")
    if query.strip():
        token = f"%{query.strip()}%"
        statement = statement.where(
            or_(Campaign.project_name.like(token), Campaign.campaign_id.like(token))
        )
    if brand:
        statement = statement.where(Campaign.brand == brand)
    campaigns = list(session.scalars(statement.order_by(Campaign.updated_at.desc())))
    if market:
        campaigns = [item for item in campaigns if market in (item.markets or [])]

    rows = []
    for campaign in campaigns:
        closure = get_campaign_closure(session, campaign)
        checks = build_checks(session, campaign, closure)
        readiness = _readiness(checks)
        blocking = sum(item["status"] == "阻断" for item in checks) + len(
            _open_blocking_issues(closure)
        )
        closure_status = closure.status if closure else (
            "not_ready" if readiness < 100 or blocking else "draft"
        )
        if status and closure_status != status:
            continue
        rows.append({
            "campaign_id": campaign.campaign_id,
            "closure_id": closure.closure_id if closure else None,
            "project_name": campaign.project_name,
            "brand": campaign.brand,
            "vehicle_model": campaign.vehicle_model,
            "markets": list(campaign.markets or []),
            "primary_market": campaign.primary_market,
            "owner": campaign.owner,
            "planned_end_date": campaign.end_date.isoformat(),
            "campaign_status": campaign.status,
            "closure_status": closure_status,
            "closure_status_label": STATUS_LABELS[closure_status],
            "readiness": readiness,
            "blocking_count": blocking,
            "open_issue_count": sum(
                item.status != "已解决" for item in (closure.issues if closure else [])
            ),
            "updated_at": (closure.updated_at if closure else campaign.updated_at).isoformat(),
        })
    return rows


def serialize_issue(issue: ClosureIssue) -> dict:
    return {
        "issue_id": issue.issue_id,
        "issue_type": issue.issue_type,
        "title": issue.title,
        "description": issue.description,
        "severity": issue.severity,
        "owner": issue.owner,
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "status": issue.status,
        "source_reference": issue.source_reference,
        "resolution_note": issue.resolution_note,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }


def serialize_audit(audit: ClosureAudit) -> dict:
    return {
        "action": audit.action,
        "actor": audit.actor,
        "actor_role": audit.actor_role,
        "reason": audit.reason,
        "version": audit.version,
        "created_at": audit.created_at.isoformat(),
    }


def serialize_closure(
    session: Session, closure: CampaignClosure, *, include_detail: bool = True
) -> dict:
    checks = _refresh_status(session, closure)
    campaign = closure.campaign
    payload = {
        "closure_id": closure.closure_id,
        "campaign_id": campaign.campaign_id,
        "project_name": campaign.project_name,
        "brand": campaign.brand,
        "vehicle_model": campaign.vehicle_model,
        "markets": list(campaign.markets or []),
        "primary_market": campaign.primary_market,
        "currency": campaign.currency,
        "budget_total": campaign.budget_total,
        "owner": campaign.owner,
        "planned_end_date": campaign.end_date.isoformat(),
        "status": closure.status,
        "status_label": STATUS_LABELS[closure.status],
        "readiness": closure.readiness,
        "revision": closure.revision,
        "version": closure.version,
        "blocking_count": sum(item["status"] == "阻断" for item in checks) + len(_open_blocking_issues(closure)),
        "open_issue_count": sum(item.status != "已解决" for item in closure.issues),
        "updated_at": closure.updated_at.isoformat(),
        "closed_at": closure.closed_at.isoformat() if closure.closed_at else None,
    }
    if include_detail:
        payload.update({
            "checks": checks,
            "issues": [serialize_issue(item) for item in closure.issues],
            "summary": dict(closure.summary or {}),
            "audits": [serialize_audit(item) for item in closure.audits],
        })
    return payload


def update_checks(
    session: Session, closure: CampaignClosure, payload: ClosureChecksPayload
) -> CampaignClosure:
    _require_role(payload.actor_role, EDIT_ROLES, "确认结案核对项")
    _check_revision(closure, payload.expected_revision)
    if closure.status == "closed":
        raise ClosureConflictError("已结案版本只读，如需更正请建立修订版本")
    if closure.status == "returned":
        closure.status = "draft"
    valid_keys = {item[0] for item in CHECK_DEFINITIONS}
    automatic = _automatic_checks(session, closure.campaign)
    saved = dict(closure.checks or {})
    for item in payload.items:
        if item.check_key not in valid_keys:
            raise ClosureValidationError(f"未知核对项：{item.check_key}")
        if automatic[item.check_key].get("system_blocking") and item.status == "通过":
            raise ClosureValidationError("未关闭的重大风险不能通过人工确认绕过")
        saved[item.check_key] = {
            "status": item.status,
            "note": (item.note or "").strip() or None,
            "confirmed_by": payload.actor,
            "confirmed_at": _now().isoformat(),
        }
    closure.checks = saved
    _touch(closure)
    _refresh_status(session, closure)
    _audit(session, closure, "checks_updated", payload.actor, payload.actor_role)
    session.commit()
    session.refresh(closure)
    return closure


def create_issue(
    session: Session, closure: CampaignClosure, payload: ClosureIssueCreate
) -> ClosureIssue:
    _require_role(payload.actor_role, EDIT_ROLES, "新增遗留事项")
    _check_revision(closure, payload.expected_revision)
    if closure.status == "closed":
        raise ClosureConflictError("已结案版本只读")
    if closure.status == "returned":
        closure.status = "draft"
    issue = ClosureIssue(
        issue_id=_new_id("ISS"),
        closure=closure,
        issue_type=payload.issue_type,
        title=payload.title.strip(),
        description=payload.description.strip(),
        severity=payload.severity,
        owner=payload.owner.strip(),
        due_date=payload.due_date,
        source_reference=(payload.source_reference or "").strip() or None,
    )
    session.add(issue)
    _touch(closure)
    _refresh_status(session, closure)
    _audit(session, closure, "issue_created", payload.actor, payload.actor_role, issue.title)
    session.commit()
    session.refresh(issue)
    return issue


def update_issue(
    session: Session,
    closure: CampaignClosure,
    issue: ClosureIssue,
    payload: ClosureIssuePatch,
) -> ClosureIssue:
    _require_role(payload.actor_role, EDIT_ROLES, "更新遗留事项")
    _check_revision(closure, payload.expected_revision)
    if closure.status == "closed":
        raise ClosureConflictError("已结案版本只读")
    if closure.status == "returned":
        closure.status = "draft"
    if issue.severity == "阻断" and payload.status == "接受遗留":
        raise ClosureValidationError("阻断事项必须解决，不能直接接受遗留")
    issue.status = payload.status
    issue.resolution_note = (payload.resolution_note or "").strip() or None
    issue.updated_at = _now()
    _touch(closure)
    _refresh_status(session, closure)
    _audit(session, closure, "issue_updated", payload.actor, payload.actor_role, issue.title)
    session.commit()
    session.refresh(issue)
    return issue


def save_summary(
    session: Session, closure: CampaignClosure, payload: ClosureSummaryPayload
) -> CampaignClosure:
    _require_role(payload.actor_role, EDIT_ROLES, "编辑结案摘要")
    _check_revision(closure, payload.expected_revision)
    if closure.status == "closed":
        raise ClosureConflictError("已结案版本只读")
    if closure.status == "returned":
        closure.status = "draft"
    closure.summary = payload.model_dump(
        exclude={"expected_revision", "actor", "actor_role"}
    )
    _touch(closure)
    _refresh_status(session, closure)
    _audit(session, closure, "summary_updated", payload.actor, payload.actor_role)
    session.commit()
    session.refresh(closure)
    return closure


def submit_closure(
    session: Session, closure: CampaignClosure, payload: ClosureActionPayload
) -> CampaignClosure:
    _require_role(payload.actor_role, SUBMIT_ROLES, "提交结案确认")
    _check_revision(closure, payload.expected_revision)
    if closure.status == "closed":
        raise ClosureConflictError("项目已经结案")
    checks = _refresh_status(session, closure)
    failures = [
        {"type": "check", "key": item["key"], "message": item["detail"]}
        for item in checks if item["required"] and item["status"] != "通过"
    ]
    failures += [
        {"type": "issue", "key": item.issue_id, "message": item.title}
        for item in _open_blocking_issues(closure)
    ]
    required_summary = {
        "objective_result", "executive_summary", "key_results", "top_kols",
        "risk_kols", "lessons_learned", "next_action",
    }
    missing_summary = sorted(required_summary - set((closure.summary or {}).keys()))
    failures += [
        {"type": "summary", "key": key, "message": "结案摘要字段未填写"}
        for key in missing_summary
    ]
    if failures:
        raise ClosureValidationError("结案材料尚未满足提交条件", failures)
    closure.status = "pending_confirmation"
    _touch(closure)
    _audit(
        session, closure, "submitted", payload.actor, payload.actor_role,
        payload.reason, include_snapshot=True,
    )
    session.commit()
    session.refresh(closure)
    return closure


def decide_closure(
    session: Session, closure: CampaignClosure, payload: ClosureDecisionPayload
) -> CampaignClosure:
    _require_role(payload.actor_role, DECISION_ROLES, "确认或退回结案")
    _check_revision(closure, payload.expected_revision)
    if closure.status != "pending_confirmation":
        raise ClosureConflictError("只有待确认的结案版本可以审批")
    if payload.decision == "退回补充":
        closure.status = "returned"
        action = "returned"
    else:
        closure.status = "closed"
        closure.closed_at = _now()
        action = "closed"
    _touch(closure)
    _audit(
        session, closure, action, payload.actor, payload.actor_role,
        payload.reason, include_snapshot=True,
    )
    session.commit()
    session.refresh(closure)
    return closure


def revise_closure(
    session: Session, closure: CampaignClosure, payload: ClosureActionPayload
) -> CampaignClosure:
    _require_role(payload.actor_role, SUBMIT_ROLES, "建立修订版本")
    _check_revision(closure, payload.expected_revision)
    if closure.status != "closed":
        raise ClosureConflictError("只有已结案记录可以建立修订版本")
    if not (payload.reason or "").strip():
        raise ClosureValidationError("建立修订版本必须填写原因")
    closure.version += 1
    closure.status = "revised"
    closure.closed_at = None
    _touch(closure)
    _refresh_status(session, closure)
    _audit(session, closure, "revision_created", payload.actor, payload.actor_role, payload.reason)
    session.commit()
    session.refresh(closure)
    return closure


def archive_payload(session: Session, closure: CampaignClosure) -> dict:
    payload = serialize_closure(session, closure, include_detail=True)
    snapshots = [
        {
            "action": item.action,
            "version": item.version,
            "created_at": item.created_at.isoformat(),
            "snapshot": item.snapshot,
        }
        for item in closure.audits if item.snapshot
    ]
    payload["snapshots"] = snapshots
    payload["read_only"] = closure.status == "closed"
    return payload
