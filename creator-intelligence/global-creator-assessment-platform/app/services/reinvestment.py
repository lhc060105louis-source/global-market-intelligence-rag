from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignReview, ContentTask, Kol, KolCrisisEvent, PerformanceReview

STATE_KEY = "__asset_reinvestment__"

PROJECT = {
    "name": "XPENG G6 United Kingdom Test-Drive Reach Campaign",
    "brand": "XPENG",
    "model": "G6",
    "market": "United Kingdom",
    "market_code": "GB",
    "platforms": ["YouTube", "Instagram", "TikTok"],
    "objective": "Test-drive reach, deeper product awareness, and high-intent leads",
    "budget": 60000,
    "currency": "GBP",
    "period": "2026 Q4",
}

ASSETS = [
    {"handle": "@AutoBildDE", "name": "AutoBildDE", "country": "DE", "market": "Germany", "platform": "YouTube", "followers": 1420000, "collaborations": 4, "recent_project": "BYD Seal U Germany Launch Reach Campaign", "recent_score": 91, "list_status": "Preferred", "risk": "No Major Risk", "major_risk": False, "data_completeness": 96, "last_collaboration": "2026-08", "content_assets": 13, "avg_engagement": 8.6, "conversions": 3240, "content_quality": 92},
    {"handle": "@EVReviewUK", "name": "EVReviewUK", "country": "GB", "market": "United Kingdom", "platform": "Instagram", "followers": 865000, "collaborations": 3, "recent_project": "BYD United Kingdom Test-Drive Reach Campaign", "recent_score": 88, "list_status": "Conditional", "risk": "Low Risk", "major_risk": False, "data_completeness": 92, "last_collaboration": "2026-07", "content_assets": 9, "avg_engagement": 8.1, "conversions": 2380, "content_quality": 90},
    {"handle": "@Carwow", "name": "Carwow", "country": "GB", "market": "United Kingdom", "platform": "YouTube", "followers": 9700000, "collaborations": 5, "recent_project": "XPENG G9 United Kingdom Reach Campaign", "recent_score": 90, "list_status": "Preferred", "risk": "No Major Risk", "major_risk": False, "data_completeness": 98, "last_collaboration": "2026-06", "content_assets": 17, "avg_engagement": 7.8, "conversions": 2140, "content_quality": 94},
    {"handle": "@MobiliteVerte", "name": "MobiliteVerte", "country": "FR", "market": "France", "platform": "TikTok", "followers": 612000, "collaborations": 2, "recent_project": "BYD Europe Short-Form Video Reach Campaign", "recent_score": 76, "list_status": "Watch", "risk": "Moderate Negative Comments", "major_risk": False, "data_completeness": 84, "last_collaboration": "2026-05", "content_assets": 6, "avg_engagement": 6.5, "conversions": 1310, "content_quality": 82},
    {"handle": "@EVMotionDE", "name": "EVMotionDE", "country": "DE", "market": "Germany", "platform": "YouTube", "followers": 740000, "collaborations": 2, "recent_project": "BYD Germany New Vehicle Launch Reach Campaign", "recent_score": 71, "list_status": "Paused", "risk": "Critical Entity Risk Pending Verification", "major_risk": True, "data_completeness": 80, "last_collaboration": "2026-08", "content_assets": 7, "avg_engagement": 6.9, "conversions": 980, "content_quality": 78},
]

ARCHIVES = {
    "@AutoBildDE": {
        "markets": ["Germany", "United Kingdom"],
        "project_history": [
            {"project": "BYD Seal U Germany Launch Reach Campaign", "date": "2026-08", "platform": "YouTube", "result": "Objective Achievement: 128%", "score": 91, "note": "Long-form video engagement and conversions were consistent"},
            {"project": "XPENG G9 Europe Test-Drive Campaign", "date": "2026-03", "platform": "YouTube", "result": "Objective Achievement: 116%", "score": 88, "note": "Expert-review content is reusable"},
            {"project": "BYD Atto 3 Product Education", "date": "2025-10", "platform": "YouTube", "result": "Objective Achievement: 104%", "score": 84, "note": "Specifications were clearly explained and delivery was on time"},
            {"project": "Europe EV Buying Guide", "date": "2025-05", "platform": "YouTube", "result": "Objective Achievement: 97%", "score": 79, "note": "Older sample; use as a trend reference only"},
        ],
        "reusable_assets": ["Seal U Germany launch experience long-form video", "Vehicle specification Q&A assets", "German test-drive narration structure"],
        "risks": ["2026-08 Advertising disclosure added: corrected", "No confirmed critical entity risks found"],
        "audit": ["2026-08-20 Post-campaign review recorded", "2026-08-21 Data completeness reviewed", "2026-08-25 Added to reinvestment assessment candidates"],
    },
    "@EVReviewUK": {
        "markets": ["United Kingdom"],
        "project_history": [
            {"project": "BYD United Kingdom Test-Drive Reach Campaign", "date": "2026-07", "platform": "Instagram", "result": "Objective Achievement: 119%", "score": 88, "note": "Short-form video engagement efficiency was high"},
            {"project": "XPENG P7 United Kingdom Social Partnership", "date": "2026-02", "platform": "Instagram", "result": "Objective Achievement: 109%", "score": 84, "note": "Scheduling coordination was consistent"},
            {"project": "Europe Electric Vehicle Feature", "date": "2025-09", "platform": "YouTube", "result": "Objective Achievement: 102%", "score": 81, "note": "Comment quality was good"},
        ],
        "reusable_assets": ["United Kingdom user test-drive Q&A", "Vertical vehicle highlight template"],
        "risks": ["No confirmed critical entity risks found"],
        "audit": ["2026-07-30 Post-campaign review recorded", "2026-08-25 Reinvestment candidates updated"],
    },
}

EVALUATIONS = {
    "@AutoBildDE": {"score": 82, "status": "Continue with Conditions", "quote_cap": 18000, "content_format": "1 YouTube in-depth test drive + 1 short cutdown", "schedule": "Lock the script 10 days before launch; publish during launch week", "exclusivity": "30-day soft exclusivity against comparable competitors", "dimensions": [88, 76, 92, 74, 86, 94]},
    "@EVReviewUK": {"score": 87, "status": "Preferred", "quote_cap": 15000, "content_format": "2 Instagram Reels + Stories", "schedule": "Publish within 7 days after the test drive", "exclusivity": "14-day soft exclusivity against comparable competitors", "dimensions": [94, 88, 89, 82, 86, 84]},
    "@Carwow": {"score": 91, "status": "Preferred", "quote_cap": 28000, "content_format": "1 core YouTube test drive", "schedule": "Priority slot during launch week", "exclusivity": "Confirm in the contract", "dimensions": [96, 94, 95, 76, 91, 93]},
    "@MobiliteVerte": {"score": 68, "status": "Watch", "quote_cap": 8000, "content_format": "2 TikTok short-form videos", "schedule": "Amplification after launch", "exclusivity": "No mandatory exclusivity", "dimensions": [55, 72, 76, 78, 73, 80]},
    "@EVMotionDE": {"score": 64, "status": "Paused Assessment", "quote_cap": 0, "content_format": "Define after risk verification", "schedule": "Paused", "exclusivity": "—", "dimensions": [62, 70, 72, 69, 74, 38]},
}

DIMENSIONS = [
    ("Audience Fit", "Based on historical market reach and the target project's audience profile"),
    ("Content Fit", "Based on historical content quality, vehicle topics, and reusable assets"),
    ("Platform Performance", "Based on historical engagement and content performance by platform"),
    ("Commercial Efficiency", "Based on historical quotes, conversions, and project budget limits"),
    ("Execution Reliability", "Based on delivery, brief coordination, and scheduling history"),
    ("Brand Safety", "Based on entity risks, disclosures, and historical compliance records"),
]

SCENARIOS = [
    {"id": "A", "name": "Core Reach", "kols": ["@Carwow", "@EVReviewUK"], "cost": 52000, "reach_range": "1.8M–2.4M", "engagement_range": "120K–170K", "confidence": "Medium-High", "note": "Prioritizes the core United Kingdom audience while preserving budget flexibility."},
    {"id": "B", "name": "Expert Endorsement", "kols": ["@Carwow", "@AutoBildDE"], "cost": 58000, "reach_range": "2.0M–2.7M", "engagement_range": "130K–180K", "confidence": "Medium", "note": "Strong subject-matter credibility; confirm the United Kingdom audience share for cross-market content."},
    {"id": "C", "name": "Social Amplification", "kols": ["@EVReviewUK", "@MobiliteVerte"], "cost": 34000, "reach_range": "1.2M–1.8M", "engagement_range": "90K–145K", "confidence": "Medium", "note": "Lower cost and strong short-form reach, with less capacity to build in-depth awareness."},
    {"id": "D", "name": "Balanced Mix", "kols": ["@Carwow", "@EVReviewUK", "@MobiliteVerte"], "cost": 60000, "reach_range": "2.3M–3.0M", "engagement_range": "155K–215K", "confidence": "Medium", "note": "Uses the full budget; retain a contingency plan for quote changes."},
]

TASKS = [
    {"task_code": "ACT-001", "kol": "@Carwow", "task": "Confirm the quote and content package", "owner": "Commercial Lead", "due_at": "2026-09-02", "status": "In Progress", "dependency": "None"},
    {"task_code": "ACT-002", "kol": "@Carwow", "task": "Confirm the test-drive and publication schedule", "owner": "Project Manager", "due_at": "2026-09-04", "status": "To Do", "dependency": "ACT-001"},
    {"task_code": "ACT-003", "kol": "@EVReviewUK", "task": "Confirm the Reels format", "owner": "Content Lead", "due_at": "2026-09-03", "status": "To Do", "dependency": "None"},
    {"task_code": "ACT-004", "kol": "@EVReviewUK", "task": "Prepare the brief and disclosure requirements", "owner": "Content Lead", "due_at": "2026-09-06", "status": "To Do", "dependency": "ACT-003"},
    {"task_code": "ACT-005", "kol": "@MobiliteVerte", "task": "Confirm whether to include in supplemental amplification", "owner": "Media Lead", "due_at": "2026-09-05", "status": "To Do", "dependency": "Scenario approval"},
    {"task_code": "ACT-006", "kol": "Project Team", "task": "Complete the list risk review", "owner": "Brand Safety", "due_at": "2026-09-01", "status": "In Progress", "dependency": "None"},
]


def _now():
    return datetime.now(timezone.utc)


def _read_state(session: Session):
    row = session.scalar(select(CampaignReview).where(CampaignReview.campaign == STATE_KEY))
    if row is None:
        row = CampaignReview(
            campaign=STATE_KEY,
            status="System Status",
            analysis_data={
                "selected_scenario": "A",
                "approvals": {},
                "governance": {},
                "governance_log": [],
                "task_status": {},
            },
        )
        session.add(row)
        session.commit()
        session.refresh(row)

    state = dict(row.analysis_data or {})
    state.setdefault("selected_scenario", "A")
    state.setdefault("approvals", {})
    state.setdefault("governance", {})
    state.setdefault("governance_log", [])
    state.setdefault("task_status", {})
    return row, state


def _save_state(session: Session, row: CampaignReview, state: dict):
    row.analysis_data = dict(state)
    row.updated_at = _now()
    session.commit()


def _all_assets(session: Session):
    assets = [dict(item) for item in ASSETS]
    by_handle = {item["handle"]: item for item in assets}

    kols = list(session.scalars(select(Kol).where(Kol.deleted_at.is_(None))))
    reviews = list(session.scalars(select(PerformanceReview).where(PerformanceReview.deleted_at.is_(None)).order_by(PerformanceReview.created_at.desc())))
    content_tasks = list(session.scalars(select(ContentTask)))
    crises = list(session.scalars(select(KolCrisisEvent).where(KolCrisisEvent.status != "Closed")))

    reviews_by_kol = {}
    for review in reviews:
        reviews_by_kol.setdefault(review.kol_id, []).append(review)

    content_count = {}
    for task in content_tasks:
        if task.kol_id is not None:
            content_count[task.kol_id] = content_count.get(task.kol_id, 0) + 1

    active_risk = set()
    for crisis in crises:
        details = crisis.details or {}
        handle = crisis.kol.handle if crisis.kol and crisis.kol.handle else details.get("kol_handle")
        if handle:
            active_risk.add(handle)

    for kol in kols:
        if not kol.handle or kol.handle not in by_handle:
            continue
        item = by_handle[kol.handle]
        item["kol_id"] = kol.id
        item["name"] = kol.name or item["name"]
        item["country"] = kol.country or item["country"]
        item["platform"] = kol.platform or item["platform"]
        if kol.followers is not None:
            item["followers"] = kol.followers

        history = reviews_by_kol.get(kol.id, [])
        if history:
            latest = history[0]
            item["collaborations"] = len(history)
            item["recent_project"] = latest.campaign
            item["last_collaboration"] = latest.created_at.strftime("%Y-%m")
            item["conversions"] = sum(x.conversions or 0 for x in history)
        if content_count.get(kol.id):
            item["content_assets"] = content_count[kol.id]

    for item in assets:
        item.setdefault("kol_id", None)
        if item["handle"] in active_risk:
            item["risk"] = "An unresolved critical entity-level risk event exists."
            item["major_risk"] = True
            item["list_status"] = "Paused"

    _, state = _read_state(session)
    for item in assets:
        saved = state["governance"].get(item["handle"])
        if not saved:
            continue
        item["list_status"] = saved.get("status", item["list_status"])
        item["risk"] = saved.get("reason") or item["risk"]
        if item["list_status"] in {"Paused", "Blocked"}:
            item["major_risk"] = True

    return assets


def _find_asset(session: Session, key: str):
    for item in _all_assets(session):
        if item["handle"].lower() == key.lower() or str(item.get("kol_id")) == key:
            return item
    return None


def get_asset_overview(session: Session, country=None, platform=None, status=None):
    assets = _all_assets(session)
    rows = [
        item for item in assets
        if (not country or item["country"] == country)
        and (not platform or item["platform"] == platform)
        and (not status or item["list_status"] == status)
    ]

    counts = {name: sum(1 for item in assets if item["list_status"] == name) for name in ["Preferred", "Conditional", "Watch", "Paused", "Blocked"]}
    attention = [{"type": "risk", "text": f"{item['handle']}: {item['risk']}"} for item in assets if item["major_risk"]]
    attention += [{"type": "Data", "text": f"{item['handle']} data completeness is {item['data_completeness']}%; complete missing information before reinvestment."} for item in assets if item["data_completeness"] < 85]

    by_market = {}
    by_platform = {}
    for item in assets:
        by_market[item["market"]] = by_market.get(item["market"], 0) + 1
        by_platform[item["platform"]] = by_platform.get(item["platform"], 0) + 1

    return {
        "context": "Historical partnership asset pool",
        "metrics": {
            "total": len(assets),
            "preferred": counts["Preferred"],
            "conditional": counts["Conditional"],
            "watch": counts["Watch"],
            "blocked": counts["Paused"] + counts["Blocked"],
            "major_risk": sum(1 for item in assets if item["major_risk"]),
        },
        "structure": {"by_market": by_market, "by_platform": by_platform, "statuses": counts},
        "attention": attention,
        "assets": rows,
        "filters": {"country": country or "", "platform": platform or "", "status": status or ""},
        "updated_at": _now().isoformat(),
    }


def get_asset_archive(session: Session, key: str):
    item = _find_asset(session, key)
    if item is None:
        return None

    archive = ARCHIVES.get(item["handle"])
    if archive:
        archive = {k: list(v) if isinstance(v, list) else v for k, v in archive.items()}
        archive["project_history"] = [dict(row) for row in archive["project_history"]]
    else:
        archive = {
            "markets": [item["market"]],
            "project_history": [
                {"project": item["recent_project"], "date": item["last_collaboration"], "platform": item["platform"], "result": f"Review score: {item['recent_score']}", "score": item["recent_score"], "note": "Most recent partnership result."},
                {"project": "Historical partnership record", "date": "2025-12", "platform": item["platform"], "result": "Historical sample", "score": max(0, item["recent_score"] - 5), "note": "For archive reference only."},
            ],
            "reusable_assets": ["Historical content assets", "Partnership briefs and execution records"],
            "risks": [item["risk"]],
            "audit": [f"{item['last_collaboration']} — latest partnership record added to the archive."],
        }

    if item.get("kol_id"):
        records = list(session.scalars(select(PerformanceReview).where(PerformanceReview.kol_id == item["kol_id"], PerformanceReview.deleted_at.is_(None)).order_by(PerformanceReview.created_at.desc())))
        if records:
            archive["project_history"] = [
                {
                    "project": row.campaign,
                    "date": row.created_at.strftime("%Y-%m"),
                    "platform": item["platform"],
                    "result": f"Impressions: {row.impressions if row.impressions is not None else 'Unavailable'} / Engagements: {row.engagements if row.engagements is not None else 'Unavailable'} / Conversions: {row.conversions if row.conversions is not None else 'Unavailable'}",
                    "score": None,
                    "note": "From the existing partnership performance record.",
                }
                for row in records
            ]

    history = archive["project_history"]
    score_count = sum(1 for row in history if row.get("score") is not None)
    identity = {name: item[name] for name in ["kol_id", "handle", "name", "country", "market", "platform", "followers", "list_status"]}

    return {
        "identity": identity,
        "metrics": {
            "collaborations": item["collaborations"],
            "markets": len(archive["markets"]),
            "content_assets": item["content_assets"],
            "avg_engagement": item["avg_engagement"],
            "conversions": item["conversions"],
            "content_quality": item["content_quality"],
        },
        "data_completeness": item["data_completeness"],
        "trend": [{"date": row["date"], "score": row["score"], "project": row["project"]} for row in history] if score_count >= 3 else [],
        "trend_note": "The trend reflects historical projects and does not predict the next project." if score_count >= 3 else "The sample is too small to generate a trend; individual results are retained.",
        "recent_cooperation": history[0],
        "project_history": history,
        "reusable_assets": archive["reusable_assets"],
        "risks": archive["risks"],
        "audit": archive["audit"],
        "next": {"page": "evaluation", "target_project": PROJECT["name"]},
    }


def get_reinvestment_evaluation(session: Session, key: str):
    item = _find_asset(session, key)
    if item is None:
        return None

    seed = EVALUATIONS[item["handle"]]
    _, state = _read_state(session)
    blocked = item["major_risk"] or item["list_status"] in {"Paused", "Blocked"}
    dimensions = []

    for i, (name, evidence) in enumerate(DIMENSIONS):
        limitation = "No critical information is missing." if item["data_completeness"] >= 90 else "Some historical data is insufficient; supplement it before confirmation."
        if name == "Brand Safety" and blocked:
            limitation = "An entity-level risk blocks reinvestment; manual review is required first."
        dimensions.append({"name": name, "score": seed["dimensions"][i], "evidence": evidence, "limitation": limitation})

    approval = state["approvals"].get(item["handle"], {"decision": "Pending Approval", "note": "", "updated_at": None})
    return {
        "kol": {"handle": item["handle"], "name": item["name"], "market": item["market"], "platform": item["platform"]},
        "project": PROJECT,
        "suggestion_score": seed["score"],
        "suggestion_status": "Paused Assessment" if blocked else seed["status"],
        "data_completeness": item["data_completeness"],
        "major_risk": blocked,
        "dimensions": dimensions,
        "conditions": {
            "quote_cap": seed["quote_cap"],
            "currency": PROJECT["currency"],
            "content_format": seed["content_format"],
            "schedule": seed["schedule"],
            "disclosure": "Follow United Kingdom commercial partnership disclosure requirements.",
            "exclusivity": seed["exclusivity"],
            "data_required": "After publication, provide platform screenshots and basic engagement and conversion data.",
        },
        "approval": approval,
        "note": "The recommendation score supports comparisons for this project. Critical risks and manual approvals are handled separately.",
    }


def save_evaluation_approval(session: Session, key: str, decision: str, note=None):
    if decision not in {"Approved", "Conditionally Approved", "Returned for More Information", "Rejected"}:
        raise ValueError("Invalid reinvestment approval decision.")
    item = _find_asset(session, key)
    if item is None:
        raise LookupError("Creator not found.")

    row, state = _read_state(session)
    approvals = dict(state["approvals"])
    saved = {"decision": decision, "note": note or "", "updated_at": _now().isoformat()}
    approvals[item["handle"]] = saved
    state["approvals"] = approvals
    _save_state(session, row, state)
    return saved


def get_portfolio_plan(session: Session):
    _, state = _read_state(session)
    selected = state["selected_scenario"]
    assets = {item["handle"]: item for item in _all_assets(session)}

    candidates = []
    for handle in ["@Carwow", "@EVReviewUK", "@AutoBildDE", "@MobiliteVerte"]:
        item = assets[handle]
        evaluation = get_reinvestment_evaluation(session, handle)
        candidates.append({
            "handle": handle,
            "name": item["name"],
            "market": item["market"],
            "platform": item["platform"],
            "recommendation": evaluation["suggestion_status"],
            "score": evaluation["suggestion_score"],
            "quote_cap": evaluation["conditions"]["quote_cap"],
            "currency": PROJECT["currency"],
            "availability": "Available to Coordinate",
            "risk": item["risk"],
            "blocked": evaluation["major_risk"],
        })

    scenarios = []
    for item in SCENARIOS:
        row = dict(item)
        row["selected"] = row["id"] == selected
        row["budget_usage"] = round(row["cost"] / PROJECT["budget"] * 100, 1)
        row["assumption"] = "Estimated from historical samples and current quote caps."
        scenarios.append(row)

    current = next(item for item in scenarios if item["selected"])
    return {
        "project": PROJECT,
        "candidates": candidates,
        "scenarios": scenarios,
        "selected_scenario": selected,
        "checks": [
            {"name": "Budget", "status": "Passed" if current["cost"] <= PROJECT["budget"] else "Over Budget", "detail": f"{current['cost']:,} / {PROJECT['budget']:,} {PROJECT['currency']}"},
            {"name": "Role Coverage", "status": "Passed", "detail": "Candidates are available for both core reach and amplification roles."},
            {"name": "Audience Overlap", "status": "Notice", "detail": "Estimated at approximately 18% from historical samples; for scenario comparison only."},
            {"name": "Entity Risk", "status": "Passed", "detail": "The current scenario includes no paused or blocked creators."},
        ],
        "prediction_note": "Reach and engagement are indicative ranges, not performance guarantees.",
    }


def select_portfolio_scenario(session: Session, scenario_id: str):
    if scenario_id not in {item["id"] for item in SCENARIOS}:
        raise ValueError("Unknown portfolio scenario.")
    row, state = _read_state(session)
    state["selected_scenario"] = scenario_id
    _save_state(session, row, state)
    return {"selected_scenario": scenario_id, "updated_at": _now().isoformat()}


def get_governance(session: Session):
    assets = _all_assets(session)
    _, state = _read_state(session)
    rows = []

    for item in assets:
        saved = state["governance"].get(item["handle"], {})
        rows.append({
            "handle": item["handle"],
            "name": item["name"],
            "status": item["list_status"],
            "scope": saved.get("scope") or "European automotive partnership projects",
            "reason": saved.get("reason") or item["risk"],
            "affected_projects": 3 if item["major_risk"] else 0,
            "owner": saved.get("owner") or "Brand Safety / Project Team",
            "recent_change": saved.get("updated_at") or item["last_collaboration"],
            "review_at": saved.get("review_at") or "Review by project",
            "major_risk": item["major_risk"],
        })

    counts = {name: sum(1 for item in rows if item["status"] == name) for name in ["Preferred", "Conditional", "Watch", "Paused", "Blocked"]}
    risk_row = next((item for item in rows if item["major_risk"]), None)
    return {
        "metrics": {**counts, "pending_approval": sum(1 for item in rows if item["status"] in {"Conditional", "Watch", "Paused"})},
        "risk_banner": {
            "visible": risk_row is not None,
            "title": "Review the critical entity-level risk before deciding partnership eligibility." if risk_row else "No critical entity-level risks are currently recorded.",
            "kol": risk_row["handle"] if risk_row else None,
            "fact": "The current record captures a risk signal and a pause action; a person must confirm the final decision." if risk_row else "",
        },
        "rows": rows,
        "timeline": state["governance_log"][-12:],
        "rule": "List status governs partnership eligibility across projects. Routine content performance does not by itself indicate entity-level risk.",
    }


def update_governance(session: Session, key: str, status: str, reason: str, scope=None, review_at=None):
    if status not in {"Preferred", "Conditional", "Watch", "Paused", "Blocked"}:
        raise ValueError("Invalid list status.")
    if not reason.strip():
        raise ValueError("A reason is required to change the status.")

    item = _find_asset(session, key)
    if item is None:
        raise LookupError("Creator not found.")

    row, state = _read_state(session)
    governance = dict(state["governance"])
    log = list(state["governance_log"])
    saved = {
        "status": status,
        "reason": reason.strip(),
        "scope": scope or "European automotive partnership projects",
        "review_at": review_at or "Review by project",
        "owner": "Brand Safety / Project Team",
        "updated_at": _now().isoformat(),
    }
    governance[item["handle"]] = saved
    log.append({"time": saved["updated_at"], "kol": item["handle"], "event": f"List status changed to {status}.", "reason": reason.strip()})
    state["governance"] = governance
    state["governance_log"] = log
    _save_state(session, row, state)
    return {"handle": item["handle"], **saved}


def get_action_tracking(session: Session):
    _, state = _read_state(session)
    scenario = next(item for item in SCENARIOS if item["id"] == state["selected_scenario"])
    updates = state["task_status"]

    tasks = []
    for item in TASKS:
        row = dict(item)
        row["status"] = updates.get(row["task_code"], row["status"])
        tasks.append(row)

    candidates = []
    for handle in scenario["kols"]:
        candidates.append({
            "handle": handle,
            "stage": "Quoting" if handle == "@Carwow" else "Contact Needed",
            "quote": "Unconfirmed",
            "schedule": "Unconfirmed",
            "conditions": "P30 approval conditions apply.",
            "blocker": "Confirm whether to include in supplemental amplification for the United Kingdom project." if handle == "@MobiliteVerte" else "None",
        })

    stages = {name: 0 for name in ["Contact Needed", "Quoting", "Schedule Confirmation", "Terms Confirmation", "Brief Preparation", "Contracting", "Confirmed", "Exited"]}
    for item in candidates:
        stages[item["stage"]] += 1

    return {
        "project": PROJECT,
        "source_plan": f"Scenario {scenario['id']} · {scenario['name']}",
        "expected_budget": scenario["cost"],
        "currency": PROJECT["currency"],
        "milestone": "Scenario selected; proceed with quotes and schedule confirmation.",
        "next_deadline": "2026-09-02",
        "owner": "Project Lead",
        "pipeline": stages,
        "candidates": candidates,
        "tasks": tasks,
        "writeback_note": "After execution, add final quotes, content packages, and confirmation results to the historical archive. Confirmed creators then enter in-project monitoring.",
    }


def update_action_status(session: Session, task_code: str, status: str):
    if status not in {"To Do", "In Progress", "Completed", "Blocked"}:
        raise ValueError("Invalid task status.")
    if task_code not in {item["task_code"] for item in TASKS}:
        raise LookupError("Task not found.")

    row, state = _read_state(session)
    task_status = dict(state["task_status"])
    task_status[task_code] = status
    state["task_status"] = task_status
    _save_state(session, row, state)
    return {"task_code": task_code, "status": status, "updated_at": _now().isoformat()}
