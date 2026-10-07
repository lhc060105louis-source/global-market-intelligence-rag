from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import COMMERCIAL_WEIGHTS, RISK_WEIGHTS
from app.models import Campaign, CampaignReview, ContentTask, Kol, KolCrisisEvent, PerformanceReview
from app.services.scoring import calculate_summary

STATE_KEY = "__asset_reinvestment__"
STATUSES = ("Preferred", "Conditional", "Watch", "Paused", "Blocked")


def _now():
    return datetime.now(timezone.utc)


def _read_state(session: Session):
    # Reading an empty database must not create a fictitious campaign record.
    row = session.scalar(select(CampaignReview).where(CampaignReview.campaign == STATE_KEY))
    state = dict(row.analysis_data or {}) if row else {}
    for key, default in (("approvals", {}), ("campaign_approvals", {}), ("governance", {}), ("governance_log", []), ("task_status", {})):
        state.setdefault(key, default)
    # Older decisions were handle-keyed. Retain them only when the handle
    # identifies one persisted creator; later writes use the stable sync identity.
    kols = list(session.scalars(select(Kol).where(Kol.deleted_at.is_(None))))
    for kol in kols:
        if not kol.handle or sum(k.handle == kol.handle for k in kols) != 1:
            continue
        for key in ("approvals", "governance"):
            values = dict(state[key])
            if kol.handle in values:
                values.setdefault(kol.sync_id, values[kol.handle])
            state[key] = values
    return row, state


def _save_state(session, row, state):
    if row is None:
        row = CampaignReview(campaign=STATE_KEY, status="System Status")
        session.add(row)
    row.analysis_data = dict(state)
    row.updated_at = _now()
    session.commit()


def _summary(kol, score_type="commercial"):
    weights = COMMERCIAL_WEIGHTS if score_type == "commercial" else RISK_WEIGHTS
    records = {r.dimension: r.final_score for r in kol.score_records if r.score_type == score_type}
    return calculate_summary(records, weights)


def _history(session, kol_id):
    return list(session.scalars(select(PerformanceReview).where(
        PerformanceReview.kol_id == kol_id, PerformanceReview.deleted_at.is_(None)
    ).order_by(PerformanceReview.created_at.desc(), PerformanceReview.id.desc())))


def _tasks(session, kol_id=None):
    query = select(ContentTask).join(Kol, ContentTask.kol_id == Kol.id).where(Kol.deleted_at.is_(None))
    if kol_id is not None:
        query = query.where(ContentTask.kol_id == kol_id)
    return list(session.scalars(query.order_by(ContentTask.id)))


def _sum_known(records, field):
    values = [getattr(r, field) for r in records if getattr(r, field) is not None]
    return sum(values) if values else None


def _all_assets(session):
    _, state = _read_state(session)
    assets = []
    for kol in session.scalars(select(Kol).where(Kol.deleted_at.is_(None)).order_by(Kol.id)):
        history = _history(session, kol.id)
        tasks = _tasks(session, kol.id)
        summary = _summary(kol)
        crises = list(session.scalars(select(KolCrisisEvent).where(
            KolCrisisEvent.kol_id == kol.id, KolCrisisEvent.status != "Closed"
        )))
        major_risk = any(c.level == "Critical" for c in crises)
        governance = state["governance"].get(kol.sync_id, {})
        status = governance.get("status") or ("Paused" if major_risk else "Unreviewed")
        major_risk = major_risk or status in {"Paused", "Blocked"}
        # Rate requires numerator and denominator from the same observations.
        pairs = [r for r in history if r.impressions is not None and r.engagements is not None]
        impressions = sum(r.impressions for r in pairs)
        rate = round(sum(r.engagements for r in pairs) / impressions * 100, 2) if impressions > 0 else None
        latest = history[0] if history else None
        assets.append({
            "kol_id": kol.id, "creator_id": kol.sync_id, "handle": kol.handle,
            "name": kol.name or kol.handle or str(kol.id), "country": kol.country,
            "market": kol.country, "platform": kol.platform, "followers": kol.followers,
            "collaborations": len({r.campaign for r in history}),
            "recent_project": latest.campaign if latest else None,
            "recent_score": summary.score, "list_status": status,
            "risk": governance.get("reason") or ("; ".join(c.title for c in crises) if crises else "No entity-risk events recorded; assessment may be incomplete."),
            "major_risk": major_risk, "data_completeness": round(summary.completeness * 100, 1),
            "last_collaboration": latest.created_at.isoformat() if latest else None,
            "content_assets": sum(bool(t.content_url) for t in tasks), "avg_engagement": rate,
            "conversions": _sum_known(history, "conversions"), "content_quality": None,
        })
    return assets


def _find_asset(session, key):
    assets = _all_assets(session)
    exact = [a for a in assets if str(a["kol_id"]) == key or a["creator_id"] == key]
    if exact:
        return exact[0]
    matches = [a for a in assets if a["handle"] and a["handle"].casefold() == key.casefold()]
    # Handles can repeat on different platforms; do not write to an arbitrary creator.
    return matches[0] if len(matches) == 1 else None


def _project(session, campaign_id):
    if not campaign_id:
        return None
    row = session.scalar(select(Campaign).where(Campaign.campaign_id == campaign_id, Campaign.archived_at.is_(None)))
    if row is None:
        raise LookupError("Campaign not found.")
    return {"campaign_id": row.campaign_id, "name": row.project_name, "brand": row.brand,
            "model": row.vehicle_model, "market": row.primary_market, "market_code": row.primary_market,
            "objective": ", ".join(row.objectives), "budget": row.budget_total, "currency": row.currency,
            "period": f"{row.start_date.isoformat()} – {row.end_date.isoformat()}", "owner": row.owner}


def get_asset_overview(session, country=None, platform=None, status=None):
    assets = _all_assets(session)
    rows = [a for a in assets if (not country or a["country"] == country)
            and (not platform or a["platform"] == platform) and (not status or a["list_status"] == status)]
    counts = {name: sum(a["list_status"] == name for a in assets) for name in STATUSES}
    markets, platforms = {}, {}
    for a in assets:
        markets[a["market"]] = markets.get(a["market"], 0) + 1
        platforms[a["platform"]] = platforms.get(a["platform"], 0) + 1
    return {
        "context": "Persisted creator records and partnership evidence",
        "metrics": {"total": len(assets), "preferred": counts["Preferred"], "conditional": counts["Conditional"],
                    "watch": counts["Watch"], "blocked": counts["Paused"] + counts["Blocked"],
                    "major_risk": sum(a["major_risk"] for a in assets)},
        "structure": {"by_market": markets, "by_platform": platforms, "statuses": counts},
        "attention": [{"type": "Risk", "text": f"{a['name']}: {a['risk']}"} for a in assets if a["major_risk"]]
            + [{"type": "Data", "text": f"{a['name']}: {a['data_completeness']}% of weighted commercial score evidence is available."} for a in assets if a["data_completeness"] < 100],
        "assets": rows, "filters": {"country": country or "", "platform": platform or "", "status": status or ""},
        "updated_at": _now().isoformat(),
    }


def get_asset_archive(session, key):
    item = _find_asset(session, key)
    if item is None:
        return None
    history = [{"project": r.campaign, "date": r.created_at.isoformat(), "platform": item["platform"],
                "result": f"Impressions: {r.impressions if r.impressions is not None else 'Unavailable'} / Engagements: {r.engagements if r.engagements is not None else 'Unavailable'} / Conversions: {r.conversions if r.conversions is not None else 'Unavailable'}",
                "score": None, "note": r.notes or "Persisted performance record."}
               for r in _history(session, item["kol_id"])]
    tasks = _tasks(session, item["kol_id"])
    return {
        "identity": {k: item[k] for k in ("kol_id", "creator_id", "handle", "name", "country", "market", "platform", "followers", "list_status")},
        "metrics": {k: item[k] for k in ("collaborations", "content_assets", "avg_engagement", "conversions", "content_quality")}
            | {"markets": len({t.market for t in tasks if t.market})},
        "data_completeness": item["data_completeness"], "trend": [],
        "trend_note": "Campaign review scores are unavailable; no score trend can be inferred.",
        "recent_cooperation": history[0] if history else None, "project_history": history,
        "reusable_assets": [t.content_url for t in tasks if t.content_url], "risks": [item["risk"]],
        "audit": [f"{r['date']} — performance record: {r['project']}" for r in history],
        "next": {"page": "evaluation", "target_project": None},
    }


def get_reinvestment_evaluation(session, key, campaign_id=None):
    item = _find_asset(session, key)
    if item is None:
        return None
    kol = session.get(Kol, item["kol_id"])
    records = {(r.score_type, r.dimension): r for r in kol.score_records}
    dimensions = []
    for score_type, weights in (("commercial", COMMERCIAL_WEIGHTS), ("risk", RISK_WEIGHTS)):
        for dimension in weights:
            record = records.get((score_type, dimension))
            manual = record is not None and record.manual_score is not None
            dimensions.append({"name": dimension.replace("_", " ").title(), "dimension": dimension, "score_type": score_type,
                "score": record.final_score if record else None,
                "evidence": (record.manual_evidence if manual else record.evidence) if record else None,
                "source": (record.manual_source if manual else record.source) if record else None,
                "limitation": "Historical assessment; not a project-specific reinvestment score." if record and record.final_score is not None else "Score evidence unavailable."})
    _, state = _read_state(session)
    project = _project(session, campaign_id)
    approvals = state["campaign_approvals"].get(campaign_id, {}) if campaign_id else state["approvals"]
    return {
        "kol": {k: item[k] for k in ("kol_id", "creator_id", "handle", "name", "market", "platform")},
        "project": project, "suggestion_score": None, "historical_score": item["recent_score"],
        "suggestion_status": "Paused Assessment" if item["major_risk"] else "Insufficient Evidence",
        "data_completeness": item["data_completeness"], "major_risk": item["major_risk"], "dimensions": dimensions,
        "conditions": {"quote_cap": None, "currency": None, "content_format": None, "schedule": None,
                       "disclosure": None, "exclusivity": None, "data_required": "Select a campaign and record a project-specific quote, reach evidence and conditions."},
        "approval": approvals.get(item["creator_id"], {"decision": "Pending Approval", "note": "", "updated_at": None}),
        "note": "Historical assessment scores retain manual overrides and missing-data completeness. Project fit, quote caps and forecasts are unavailable until supported by project-specific evidence.",
    }


def save_evaluation_approval(session, key, decision, note=None, campaign_id=None):
    if decision not in {"Approved", "Conditionally Approved", "Returned for More Information", "Rejected"}:
        raise ValueError("Invalid reinvestment approval decision.")
    item = _find_asset(session, key)
    if item is None:
        raise LookupError("Creator not found or handle ambiguous.")
    _project(session, campaign_id)
    row, state = _read_state(session)
    saved = {"decision": decision, "note": note or "", "updated_at": _now().isoformat()}
    if campaign_id:
        approvals = {**state["campaign_approvals"].get(campaign_id, {}), item["creator_id"]: saved}
        state["campaign_approvals"] = {**state["campaign_approvals"], campaign_id: approvals}
    else:
        state["approvals"] = {**state["approvals"], item["creator_id"]: saved}
    _save_state(session, row, state)
    return saved


def get_portfolio_plan(session, campaign_id=None):
    project = _project(session, campaign_id)
    candidates = [{"kol_id": a["kol_id"], "creator_id": a["creator_id"], "handle": a["handle"], "name": a["name"],
                   "market": a["market"], "platform": a["platform"], "recommendation": "Paused Assessment" if a["major_risk"] else "Insufficient Evidence",
                   "score": None, "historical_score": a["recent_score"], "quote_cap": None,
                   "currency": project["currency"] if project else None, "availability": "Unavailable", "risk": a["risk"], "blocked": a["major_risk"]}
                  for a in _all_assets(session)]
    return {"project": project, "candidates": candidates, "scenarios": [], "selected_scenario": None,
            "checks": [{"name": name, "status": "Unavailable", "detail": detail} for name, detail in (
                ("Budget", "No selected portfolio or project-specific quotes."),
                ("Role Coverage", "No selected portfolio and evidenced role assignments."),
                ("Audience Overlap", "No measured audience overlap evidence."),
                ("Entity Risk", "No portfolio selected; consult individual creator governance."))],
            "prediction_note": "Portfolio planning is unavailable until an actual campaign, quotes and a recorded proposal are selected. Historical impressions are not unique reach or a forecast."}


def select_portfolio_scenario(session, scenario_id):
    raise ValueError("Portfolio scenarios are unavailable: no recorded proposal with project-specific quotes exists.")


def get_governance(session):
    assets = _all_assets(session)
    _, state = _read_state(session)
    rows = []
    for item in assets:
        saved = state["governance"].get(item["creator_id"], {})
        rows.append({"kol_id": item["kol_id"], "creator_id": item["creator_id"], "handle": item["handle"], "name": item["name"],
            "status": item["list_status"], "scope": saved.get("scope"), "reason": saved.get("reason") or item["risk"],
            "affected_projects": None, "owner": saved.get("owner"), "recent_change": saved.get("updated_at"),
            "review_at": saved.get("review_at"), "major_risk": item["major_risk"]})
    risk = next((r for r in rows if r["major_risk"]), None)
    return {"metrics": {name: sum(r["status"] == name for r in rows) for name in STATUSES}
            | {"pending_approval": sum(r["status"] in {"Unreviewed", "Conditional", "Watch", "Paused"} for r in rows)},
            "risk_banner": {"visible": bool(risk), "title": "Review recorded entity risk and governance restrictions." if risk else "No blocking entity-risk events recorded.",
                            "kol": risk["handle"] if risk else None, "fact": risk["reason"] if risk else ""},
            "rows": rows, "timeline": state["governance_log"][-12:],
            "rule": "List status governs partnership eligibility. Missing risk evidence does not demonstrate safety."}


def update_governance(session, key, status, reason, scope=None, review_at=None):
    if status not in STATUSES:
        raise ValueError("Invalid list status.")
    if not reason.strip():
        raise ValueError("A reason is required to change the status.")
    item = _find_asset(session, key)
    if item is None:
        raise LookupError("Creator not found or handle ambiguous.")
    row, state = _read_state(session)
    saved = {"status": status, "reason": reason.strip(), "scope": scope or None,
             "review_at": review_at or None, "owner": None, "updated_at": _now().isoformat()}
    state["governance"] = {**state["governance"], item["creator_id"]: saved}
    state["governance_log"] = [*state["governance_log"], {"time": saved["updated_at"], "kol_id": item["kol_id"],
        "creator_id": item["creator_id"], "kol": item["handle"], "event": f"List status changed to {status}.", "reason": reason.strip()}]
    _save_state(session, row, state)
    return {"kol_id": item["kol_id"], "handle": item["handle"], **saved}


def get_action_tracking(session, campaign_id=None):
    project = _project(session, campaign_id)
    _, state = _read_state(session)
    tasks = _tasks(session)
    if project:
        tasks = [t for t in tasks if t.campaign in {project["campaign_id"], project["name"]}]
    rows = [{"task_code": t.task_code, "kol_id": t.kol_id, "kol": t.kol.handle or t.kol.name or str(t.kol_id),
             "task": t.title, "owner": None, "due_at": t.planned_publish_at.isoformat() if t.planned_publish_at else None,
             "status": state["task_status"].get(t.task_code, t.execution_stage), "dependency": None} for t in tasks]
    deadlines = [t.planned_publish_at for t in tasks if t.planned_publish_at]
    return {"project": project, "source_plan": None, "expected_budget": None,
            "currency": project["currency"] if project else None, "milestone": None,
            "next_deadline": min(deadlines).isoformat() if deadlines else None, "owner": project["owner"] if project else None,
            "pipeline": {}, "candidates": [], "tasks": rows,
            "writeback_note": "Tasks come from persisted content records; no portfolio, quote or schedule has been assumed."}


def update_action_status(session, task_code, status):
    if status not in {"To Do", "In Progress", "Completed", "Blocked"}:
        raise ValueError("Invalid task status.")
    if task_code not in {t.task_code for t in _tasks(session)}:
        raise LookupError("Task not found or creator unavailable.")
    row, state = _read_state(session)
    state["task_status"] = {**state["task_status"], task_code: status}
    _save_state(session, row, state)
    return {"task_code": task_code, "status": status, "updated_at": _now().isoformat()}
