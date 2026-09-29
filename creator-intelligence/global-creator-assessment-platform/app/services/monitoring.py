from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentRiskEvent, ContentTask, Kol


CAMPAIGN = "BYD Germany New Vehicle Launch Reach Campaign"
BRAND = "BYD"
MARKET = "DE"
DEMO_UPDATED_AT = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)


def _dt(day: int, hour: int = 10, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc)


def _brief_checks(ad_disclosure: bool = True) -> dict[str, bool]:
    return {
        "Vehicle Model and Trim": True,
        "Key Selling Points": True,
        "Technical Specifications": True,
        "Brand Tone": True,
        "Advertising Disclosure": ad_disclosure,
        "CTA and Link": True,
    }


def _final_checks(ad_disclosure: bool = True) -> dict[str, bool]:
    return {
        "Brief Consistency": True,
        "Vehicle Model and Specifications": True,
        "Brand and Competitor Claims": True,
        "ADAS Safety Claims": True,
        "Advertising Disclosure": ad_disclosure,
        "Captions and Landing Page Link": True,
    }


def _version_history(version: str = "V3") -> list[dict[str, str]]:
    records = [
        {"version": "V1", "time": "2026-08-05 10:20", "note": "First review submission"},
        {"version": "V2", "time": "2026-08-06 15:40", "note": "Removed absolute claims"},
        {"version": "V3", "time": "2026-08-07 09:15", "note": "Added the official driving-range source"},
    ]
    if version == "V1":
        return records[:1]
    if version == "V2":
        return records[:2]
    return records


def _task_seed_rows() -> list[dict]:
    names = [
        ("@AutoVisionDE", "YouTube", "Long-form Video", "BYD Seal U Germany Launch: In-depth Review"),
        ("@EVDailyDE", "Instagram", "Reel", "Seal U City Commuting Experience"),
        ("@CarTechBerlin", "TikTok", "Short-form Video", "60-second Smart Cockpit Overview"),
        ("@GreenDriveDE", "YouTube", "Long-form Video", "Driving-range Review from a Family Perspective"),
        ("@MobilityLabDE", "Instagram", "Carousel", "Seal U Design Details"),
        ("@EVReviewUK", "Instagram", "Reel", "BYD Seal U Germany Launch Experience"),
        ("@AutoPaulDE", "YouTube", "Shorts", "Fast-Charging Speed Test"),
        ("@MiaDrives", "TikTok", "Short-form Video", "Parking Assistance Experience"),
        ("@EVHeute", "Instagram", "Reel", "Berlin Road Test Drive"),
        ("@RoadFutureDE", "YouTube", "Long-form Video", "Chassis and Ride Comfort Review"),
        ("@NeueMobilitaet", "Instagram", "Story", "Launch Event Coverage"),
        ("@TechAutoDE", "TikTok", "Short-form Video", "Quick Look at Rear-seat Space"),
        ("@DriveEuropeDE", "YouTube", "Long-form Video", "Seal U vs. Comparable SUVs"),
        ("@EVCompass", "Instagram", "Reel", "Official Driving Range in Real-world Conditions"),
        ("@BerlinCars", "TikTok", "Short-form Video", "Nighttime Lighting Experience"),
        ("@MotorTalkDE", "YouTube", "Long-form Video", "Germany Highway Driving Experience"),
        ("@AutoNina", "Instagram", "Reel", "Family Travel and Cabin Space"),
        ("@ChargePointDE", "YouTube", "Shorts", "Public Charging Network Demonstration"),
        ("@EVFocusDE", "TikTok", "Short-form Video", "Driver Assistance Feature Demonstration"),
        ("@CarScopeDE", "Instagram", "Carousel", "Interior Materials and Equipment Overview"),
        ("@EVMotionDE", "YouTube", "Long-form Video", "Initial Script and Filming Plan"),
        ("@UrbanEVDE", "Instagram", "Reel", "First Draft: City Driving"),
        ("@AutoPulseDE", "TikTok", "Short-form Video", "First Draft: Product Highlights"),
        ("@MobilityNowDE", "YouTube", "Long-form Video", "Brief Confirmation and Topic Planning"),
    ]

    rows: list[dict] = []
    for index, (handle, platform, content_type, title) in enumerate(names, start=1):
        if index <= 5 or 7 <= index <= 12:
            stage = "Published / Monitoring"
            review = "Passed"
            monitoring = "Monitoring"
            actual = _dt(2 + index, 18)
            planned = _dt(2 + index, 18)
        elif index in {13, 14, 15, 16}:
            stage = "Pending Publication"
            review = "Passed"
            monitoring = "Pending Publication"
            actual = None
            planned = _dt(index + 1, 18)
        elif index == 6 or 17 <= index <= 20:
            stage = "Under Review"
            review = "Pending Review"
            monitoring = "Not Started"
            actual = None
            planned = _dt(index + 2, 18) if index >= 17 else _dt(17, 18)
        elif 21 <= index <= 23:
            stage = "In Production"
            review = "Not Submitted for Review"
            monitoring = "Not Started"
            actual = None
            planned = _dt(index + 2, 18)
        else:
            stage = "Unconfirmed Brief"
            review = "Not Submitted for Review"
            monitoring = "Not Started"
            actual = None
            planned = _dt(27, 18)

        risk_level = "No Risk"
        if index == 6:
            risk_level = "High Risk"
        elif index == 14:
            risk_level = "Medium Risk"
        elif index == 21:
            risk_level = "Medium Risk"

        on_time = index not in {6, 14, 21}
        ad_ok = index != 6
        metrics = {}
        if stage == "Published / Monitoring":
            metrics = {
                "impressions": 105000 + index * 14500,
                "engagement_rate": round(3.7 + (index % 5) * 0.45, 2),
                "positive_sentiment": 68 + (index % 6) * 2,
            }

        rows.append(
            {
                "task_code": f"TASK-{index:03d}",
                "campaign": CAMPAIGN,
                "brand": BRAND,
                "market": MARKET,
                "kol_name": handle.lstrip("@"),
                "kol_handle": handle,
                "platform": platform,
                "content_type": content_type,
                "title": title,
                "execution_stage": stage,
                "planned_publish_at": planned,
                "actual_publish_at": actual,
                "on_time": on_time,
                "review_status": review,
                "monitoring_status": monitoring,
                "risk_level": risk_level,
                "version_label": "V3" if index == 6 else "V2",
                "content_url": f"https://example.invalid/content/{index}",
                "caption": (
                    "Der neue BYD Seal U im Alltagstest. Mehr Infos über den Link in Bio."
                    if index == 6
                    else f"{title}｜BYD Seal U Deutschland"
                ),
                "duration_seconds": 58 if content_type in {"Reel", "Short-form Video", "Shorts"} else 420,
                "resolution": "1080×1920" if content_type in {"Reel", "Short-form Video", "Shorts", "Story"} else "3840×2160",
                "brief_checks": _brief_checks(ad_ok),
                "version_history": _version_history("V3" if index == 6 else "V2"),
                "final_checks": _final_checks(ad_ok),
                "metrics": metrics,
            }
        )
    return rows


def _match_existing_kol(session: Session, handle: str) -> Kol | None:
    return session.scalar(select(Kol).where(Kol.handle == handle, Kol.deleted_at.is_(None)))


def _bind_existing_kols(session: Session) -> None:
    changed = False
    unbound = session.scalars(select(ContentTask).where(ContentTask.kol_id.is_(None))).all()
    for task in unbound:
        if not task.kol_handle:
            continue
        kol = _match_existing_kol(session, task.kol_handle)
        if kol is None:
            continue
        task.kol_id = kol.id
        task.kol_name = kol.name or task.kol_name
        task.platform = kol.platform or task.platform
        changed = True
    if changed:
        session.commit()


def ensure_monitoring_seed(session: Session) -> None:
    if session.scalar(select(ContentTask.id).limit(1)) is not None:
        _bind_existing_kols(session)
        return

    tasks: dict[str, ContentTask] = {}
    for row in _task_seed_rows():
        kol = _match_existing_kol(session, row["kol_handle"])
        if kol is not None:
            row["kol_id"] = kol.id
            row["kol_name"] = kol.name or row["kol_name"]
            row["platform"] = kol.platform or row["platform"]
        task = ContentTask(**row)
        session.add(task)
        session.flush()
        tasks[task.task_code] = task

    risks = [
        ContentRiskEvent(
            risk_code="RISK-20260804-017",
            task_id=tasks["TASK-006"].id,
            title="Missing Advertising Disclosure",
            level="High",
            status="In Progress",
            blocked=True,
            channel="Instagram Caption",
            detection_method="Rules and Semantic Model",
            trigger_version="V3",
            impacted_node="Final Review / Publication",
            evidence_excerpt="No commercial partnership disclosure label such as Werbung, Anzeige, or Bezahlte Partnerschaft was detected.",
            confidence=96.0,
            rules=[
                {"name": "Commercial Partnership Disclosure", "status": "Failed", "detail": "No German advertising disclosure label was found."},
                {"name": "Brand Brief 4.2", "status": "Failed", "detail": "Commercial partnership content must include a prominent disclosure."},
                {"name": "Competitor and Absolute Claims", "status": "Passed", "detail": "No non-compliant claims were found."},
            ],
            timeline=[
                {"time": "08-07 09:15", "event": "Creator submitted V3."},
                {"time": "08-07 09:16", "event": "System detected a missing advertising disclosure."},
                {"time": "08-07 09:16", "event": "Publication was automatically blocked."},
                {"time": "08-07 09:35", "event": "Project lead confirmed the issue."},
                {"time": "08-07 09:50", "event": "Revision request sent."},
            ],
            owners={"Project Lead": "Lisa Zhang", "Creator Manager": "Felix Bauer", "Compliance Reviewer": "Anna Keller", "Escalation Contact": "Brand Legal"},
            remediation_steps=[
                {"key": "pause", "label": "Pause publication", "done": True},
                {"key": "notify", "label": "Notify creator", "done": True},
                {"key": "new-version", "label": "Add commercial disclosure", "done": False},
                {"key": "legal-review", "label": "Brand legal review", "done": False},
                {"key": "recheck", "label": "Recheck and lift publication block", "done": False},
            ],
        ),
        ContentRiskEvent(
            risk_code="RISK-20260810-021",
            task_id=tasks["TASK-021"].id,
            title="First Draft Overdue",
            level="Medium",
            status="Pending",
            blocked=False,
            channel="Content Task",
            detection_method="Scheduling Rule",
            trigger_version="V1",
            impacted_node="Production / Review Submission",
            evidence_excerpt="The first draft was submitted after the scheduled date, which may reduce the time available for subsequent review.",
            confidence=100.0,
            rules=[{"name": "First Draft Deadline", "status": "Failed", "detail": "The scheduled submission date has passed."}],
            timeline=[{"time": "08-10 18:00", "event": "System flagged the first draft as overdue."}],
            owners={"Project Lead": "Lisa Zhang", "Creator Manager": "Felix Bauer"},
            remediation_steps=[
                {"key": "notify", "label": "Remind creator", "done": False},
                {"key": "new-version", "label": "Receive first draft", "done": False},
            ],
        ),
        ContentRiskEvent(
            risk_code="RISK-20260811-014",
            task_id=tasks["TASK-014"].id,
            title="Unconfirmed Product Driving-Range Claim",
            level="Medium",
            status="Under Review",
            blocked=False,
            channel="Instagram Caption",
            detection_method="Specification Rule and Manual Review",
            trigger_version="V2",
            impacted_node="Pre-publication Review",
            evidence_excerpt="The caption uses WLTP driving-range data; confirm that the vehicle model trim and official wording match.",
            confidence=82.0,
            rules=[{"name": "Driving-Range Specification Source", "status": "Unconfirmed", "detail": "Confirmation from the brand product team is required."}],
            timeline=[{"time": "08-11 14:20", "event": "Specification rule triggered a manual review."}],
            owners={"Project Lead": "Lisa Zhang", "Product Reviewer": "Markus Weber"},
            remediation_steps=[
                {"key": "product-review", "label": "Product team confirmation", "done": False},
                {"key": "recheck", "label": "Recheck", "done": False},
            ],
        ),
    ]
    session.add_all(risks)
    session.commit()
    _bind_existing_kols(session)


def _task_label(task: ContentTask) -> str:
    return task.kol_handle or task.kol_name or (f"Creator #{task.kol_id}" if task.kol_id else "Unassigned Creator")


def serialize_task(task: ContentTask, *, include_detail: bool = False) -> dict:
    payload = {
        "id": task.id,
        "task_code": task.task_code,
        "kol_id": task.kol_id,
        "kol": _task_label(task),
        "kol_name": task.kol_name,
        "kol_handle": task.kol_handle,
        "campaign": task.campaign,
        "brand": task.brand,
        "market": task.market,
        "platform": task.platform,
        "content_type": task.content_type,
        "title": task.title,
        "execution_stage": task.execution_stage,
        "planned_publish_at": task.planned_publish_at.isoformat() if task.planned_publish_at else None,
        "actual_publish_at": task.actual_publish_at.isoformat() if task.actual_publish_at else None,
        "on_time": task.on_time,
        "review_status": task.review_status,
        "monitoring_status": task.monitoring_status,
        "risk_level": task.risk_level,
        "version_label": task.version_label,
    }
    if include_detail:
        payload.update(
            {
                "content_url": task.content_url,
                "caption": task.caption,
                "duration_seconds": task.duration_seconds,
                "resolution": task.resolution,
                "brief_checks": task.brief_checks or {},
                "version_history": task.version_history or [],
                "final_checks": task.final_checks or {},
                "metrics": task.metrics or {},
            }
        )
    return payload


def serialize_risk(risk: ContentRiskEvent, *, include_detail: bool = False) -> dict:
    payload = {
        "id": risk.id,
        "risk_code": risk.risk_code,
        "task_id": risk.task_id,
        "task_code": risk.task.task_code if risk.task else None,
        "title": risk.title,
        "level": risk.level,
        "status": risk.status,
        "blocked": risk.blocked,
        "channel": risk.channel,
        "updated_at": risk.updated_at.isoformat() if risk.updated_at else None,
    }
    if include_detail:
        payload.update(
            {
                "detection_method": risk.detection_method,
                "trigger_version": risk.trigger_version,
                "impacted_node": risk.impacted_node,
                "evidence_excerpt": risk.evidence_excerpt,
                "confidence": risk.confidence,
                "rules": risk.rules or [],
                "timeline": risk.timeline or [],
                "owners": risk.owners or {},
                "remediation_steps": risk.remediation_steps or [],
            }
        )
    return payload


def list_tasks(session: Session) -> list[ContentTask]:
    ensure_monitoring_seed(session)
    return list(session.scalars(select(ContentTask).order_by(ContentTask.task_code)))


def get_task(session: Session, task_code: str) -> ContentTask | None:
    ensure_monitoring_seed(session)
    return session.scalar(select(ContentTask).where(ContentTask.task_code == task_code))


def get_risk(session: Session, risk_code: str) -> ContentRiskEvent | None:
    ensure_monitoring_seed(session)
    return session.scalar(select(ContentRiskEvent).where(ContentRiskEvent.risk_code == risk_code))


def get_open_risks(session: Session) -> list[ContentRiskEvent]:
    ensure_monitoring_seed(session)
    return list(
        session.scalars(
            select(ContentRiskEvent)
            .where(ContentRiskEvent.status != "Closed")
            .order_by(ContentRiskEvent.id)
        )
    )


def build_overview(session: Session) -> dict:
    tasks = list_tasks(session)
    risks = get_open_risks(session)
    published = [task for task in tasks if task.execution_stage == "Published / Monitoring"]
    on_time = sum(1 for task in tasks if task.on_time)

    stage_order = ["Unconfirmed Brief", "In Production", "Under Review", "Changes Requested", "Pending Publication", "Published / Monitoring"]
    stages = [{"name": stage, "count": sum(1 for task in tasks if task.execution_stage == stage)} for stage in stage_order]

    upcoming = sorted(
        [task for task in tasks if task.actual_publish_at is None and task.planned_publish_at is not None],
        key=lambda task: task.planned_publish_at,
    )[:6]

    impressions = sum((task.metrics or {}).get("impressions", 0) for task in published)
    rates = [(task.metrics or {}).get("engagement_rate") for task in published if (task.metrics or {}).get("engagement_rate") is not None]
    sentiment = [(task.metrics or {}).get("positive_sentiment") for task in published if (task.metrics or {}).get("positive_sentiment") is not None]

    return {
        "project": {
            "name": CAMPAIGN,
            "brand": BRAND,
            "market": "Germany",
            "period": "2026-08-01 — 2026-08-31",
            "updated_at": DEMO_UPDATED_AT.isoformat(),
        },
        "metrics": {
            "total_tasks": len(tasks),
            "on_time_rate": round((on_time / len(tasks) * 100) if tasks else 0, 1),
            "pending_review": sum(1 for task in tasks if task.review_status == "Pending Review"),
            "pending_publish": sum(1 for task in tasks if task.execution_stage == "Pending Publication"),
            "published": len(published),
            "open_risks": len(risks),
        },
        "stages": stages,
        "upcoming": [serialize_task(task) for task in upcoming],
        "risks": [serialize_risk(risk) for risk in risks],
        "performance": {
            "impressions": impressions,
            "average_engagement_rate": round(sum(rates) / len(rates), 2) if rates else 0,
            "positive_sentiment": round(sum(sentiment) / len(sentiment), 1) if sentiment else 0,
        },
    }


def _set_step(risk: ContentRiskEvent, key: str, done: bool = True) -> None:
    steps = [dict(step) for step in (risk.remediation_steps or [])]
    for step in steps:
        if step.get("key") == key:
            step["done"] = done
    risk.remediation_steps = steps


def _step_done(risk: ContentRiskEvent, key: str) -> bool:
    return any(step.get("key") == key and bool(step.get("done")) for step in (risk.remediation_steps or []))


def _append_timeline(risk: ContentRiskEvent, event: str) -> None:
    timeline = [dict(item) for item in (risk.timeline or [])]
    timeline.append({"time": datetime.now(timezone.utc).strftime("%m-%d %H:%M"), "event": event})
    risk.timeline = timeline


def apply_risk_action(session: Session, risk: ContentRiskEvent, action: str) -> None:
    task = risk.task
    if task is None:
        raise ValueError("Risk event is not linked to a content task.")

    if action == "notify":
        _set_step(risk, "notify")
        _append_timeline(risk, "Resolution reminder sent to the creator.")
    elif action == "new-version":
        _set_step(risk, "new-version")
        task.version_label = "V4"
        if risk.risk_code == "RISK-20260804-017":
            task.caption = "Werbung | Der neue BYD Seal U im Alltagstest. Mehr Infos über den Link in Bio."
            brief = dict(task.brief_checks or {})
            brief["Advertising Disclosure"] = True
            task.brief_checks = brief
            final = dict(task.final_checks or {})
            final["Advertising Disclosure"] = True
            task.final_checks = final
        history = [dict(item) for item in (task.version_history or [])]
        history.append({"version": "V4", "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "note": "Received a revised version."})
        task.version_history = history
        _append_timeline(risk, "Confirmed receipt of the revised version.")
    elif action == "legal-review":
        if "legal-review" not in {step.get("key") for step in (risk.remediation_steps or [])}:
            raise ValueError("This risk does not require brand legal review.")
        if not _step_done(risk, "new-version"):
            raise ValueError("Confirm receipt of the revised version first.")
        _set_step(risk, "legal-review")
        _append_timeline(risk, "Brand legal review passed.")
    elif action == "product-review":
        _set_step(risk, "product-review")
        _append_timeline(risk, "The product team confirmed the specifications.")
    elif action == "recheck":
        required = [step.get("key") for step in (risk.remediation_steps or []) if step.get("key") != "recheck"]
        if any(not _step_done(risk, key) for key in required):
            raise ValueError("Complete all remediation steps first.")
        _set_step(risk, "recheck")
        risk.blocked = False
        risk.status = "Closed"
        task.risk_level = "No Risk"
        _append_timeline(risk, "Recheck passed; risk event closed.")
    else:
        raise ValueError("Unsupported risk action.")

    session.add_all([risk, task])
    session.commit()
    session.refresh(risk)


def request_task_changes(session: Session, task: ContentTask) -> None:
    task.execution_stage = "Changes Requested"
    task.review_status = "Changes Requested"
    task.monitoring_status = "Not Started"
    session.add(task)
    session.commit()
    session.refresh(task)


def approve_task(session: Session, task: ContentTask) -> None:
    open_blocker = session.scalar(
        select(ContentRiskEvent.id)
        .where(
            ContentRiskEvent.task_id == task.id,
            ContentRiskEvent.blocked.is_(True),
            ContentRiskEvent.status != "Closed",
        )
        .limit(1)
    )
    if open_blocker is not None:
        raise ValueError("An open risk event is blocking publication.")
    if not all(bool(value) for value in (task.brief_checks or {}).values()):
        raise ValueError("Not all brief checks have passed.")
    if not all(bool(value) for value in (task.final_checks or {}).values()):
        raise ValueError("Not all final review checks have passed.")
    task.execution_stage = "Pending Publication"
    task.review_status = "Passed"
    task.monitoring_status = "Pending Publication"
    session.add(task)
    session.commit()
    session.refresh(task)


def filter_tasks(
    tasks: Iterable[ContentTask],
    *,
    query: str = "",
    stage: str = "",
    platform: str = "",
    risk: str = "",
) -> list[ContentTask]:
    query_lower = query.strip().lower()
    result = []
    for task in tasks:
        haystack = " ".join(filter(None, [task.task_code, task.kol_name, task.kol_handle, task.title])).lower()
        if query_lower and query_lower not in haystack:
            continue
        if stage and task.execution_stage != stage:
            continue
        if platform and task.platform != platform:
            continue
        if risk and task.risk_level != risk:
            continue
        result.append(task)
    return result
