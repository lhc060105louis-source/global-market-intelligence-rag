from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignReview, ContentTask, Kol, KolCrisisEvent, PerformanceReview

CAMPAIGN = "BYD Germany New Vehicle Launch Reach Campaign"
CRISIS_CODE = "CRISIS-20260815-001"
CRISIS_KOL = "@EVMotionDE"

ALLOWED_REVIEW_DECISIONS = {
    "Recommend Continuing the Partnership",
    "Continue with Conditions",
    "Adjust the Partnership Approach",
    "Do Not Continue Yet",
}
ALLOWED_CRISIS_DECISIONS = {
    "Continue Monitoring",
    "Limit Exposure",
    "Pause All Partnerships",
    "Terminate and Disassociate",
}

OVERVIEW_DATA = {
    "impressions": 8_420_000,
    "engagements": 623_000,
    "conversions": 11_480,
    "engagement_rate": 7.4,
    "target_completion": 112,
}

TARGET_DATA = {
    "impressions": {"target": 7_500_000, "actual": 8_420_000},
    "engagements": {"target": 550_000, "actual": 623_000},
    "conversions": {"target": 10_000, "actual": 11_480},
    "positive_sentiment": {"target": 70, "actual": 76},
}

PLATFORM_DATA = [
    {"name": "YouTube", "impressions": 3_820_000, "engagement_rate": 8.8},
    {"name": "Instagram", "impressions": 2_910_000, "engagement_rate": 7.1},
    {"name": "TikTok", "impressions": 1_690_000, "engagement_rate": 5.9},
]

KOL_RANKING = [
    {"kol": "@AutoBildDE", "platform": "YouTube", "impressions": 2_140_000, "engagement_rate": 8.6, "conversions": 3240, "completion": 128},
    {"kol": "@EVReviewUK", "platform": "Instagram", "impressions": 1_690_000, "engagement_rate": 8.1, "conversions": 2380, "completion": 119},
    {"kol": "@Carwow", "platform": "YouTube", "impressions": 1_520_000, "engagement_rate": 7.8, "conversions": 2140, "completion": 114},
    {"kol": "@MobiliteVerte", "platform": "TikTok", "impressions": 1_080_000, "engagement_rate": 6.5, "conversions": 1310, "completion": 103},
]

CONTENT_HIGHLIGHTS = [
    {"type": "Top-Performing Content", "title": "Seal U Germany Launch Experience", "note": "Long-form videos delivered consistent engagement and conversions."},
    {"type": "Needs Improvement", "title": "TikTok Short-Form Content", "note": "Conversions were low; strengthen the CTA and landing-page journey in the next campaign."},
]

AUTOBILD_DETAIL = {
    "name": "AutoBildDE",
    "handle": "@AutoBildDE",
    "platform": "YouTube",
    "impressions": 2_140_000,
    "engagements": 184_000,
    "conversions": 3240,
    "target_completion": 128,
    "content_quality": 92,
    "contribution": 25.4,
    "conversion_rate": 0.15,
    "contents": [
        {"title": "Seal U Germany Launch Experience", "platform": "YouTube", "impressions": 860000, "engagement_rate": 9.1, "conversions": 1420, "result": "Top-Performing Content"},
        {"title": "Seal U Urban Commuting Experience", "platform": "Instagram", "impressions": 510000, "engagement_rate": 8.4, "conversions": 760, "result": "Stable"},
        {"title": "Smart Cockpit Feature Demonstration", "platform": "Instagram", "impressions": 430000, "engagement_rate": 7.9, "conversions": 620, "result": "Stable"},
        {"title": "Charging and Driving-Range Q&A", "platform": "YouTube", "impressions": 340000, "engagement_rate": 6.8, "conversions": 440, "result": "Needs Improvement"},
    ],
    "trend": [38, 67, 91, 116, 138, 151, 164],
    "benchmarks": [
        {"name": "Engagement Rate", "kol": 8.6, "project": 7.4, "industry": 6.2},
        {"name": "Conversion Rate", "kol": 0.15, "project": 0.14, "industry": 0.11},
        {"name": "Video Completion Rate", "kol": 48, "project": 43, "industry": 39},
    ],
    "execution": {
        "Brief Consistency": "Good",
        "On-Time Delivery": "Good",
        "Brand Safety": "Good",
        "Advertising Disclosure": "Corrected",
        "Partnership Recommendation": "Recommend Continuing the Partnership",
    },
}

SENTIMENT_DATA = {
    "sample_size": 18_426,
    "positive": 76,
    "neutral": 18,
    "negative": 6,
    "topics": [
        {"name": "Interior Space", "share": 31, "sentiment": "Positive"},
        {"name": "Driving Range and Charging", "share": 24, "sentiment": "Neutral"},
        {"name": "Smart Cockpit", "share": 18, "sentiment": "Positive"},
        {"name": "Price and Value", "share": 15, "sentiment": "Neutral"},
        {"name": "Design and Styling", "share": 12, "sentiment": "Positive"},
    ],
    "vehicle_feedback": [
        {"name": "Space and Practicality", "score": 89, "note": "Strong customer approval"},
        {"name": "Driving Range and Charging", "score": 72, "note": "Some users remain concerned about highway range and charging convenience"},
        {"name": "Technology and Software", "score": 84, "note": "Cockpit experience received positive feedback"},
        {"name": "Design and Quality", "score": 88, "note": "Styling and perceived quality received positive feedback"},
    ],
    "brand_attitude": {"before": 32, "after": 41},
    "risk_items": [
        {"name": "Advertising Disclosure Added", "status": "Completed"},
        {"name": "Charging-Speed Concern", "status": "Addressed"},
        {"name": "Specification Citation Corrected", "status": "Corrected"},
    ],
}

REVIEW_DATA = {
    "scores": {
        "Objective Achievement": 112,
        "Content Reach": 91,
        "User Feedback": 86,
        "Execution Quality": 88,
        "Risk Control": 94,
        "Commercial Value": 89,
    },
    "overall_score": 91,
    "summary": "The campaign met its objectives overall, with long-form content from leading creators making the strongest contribution.",
    "strengths": ["Core content generated strong engagement", "Leading creators delivered consistent conversions", "Key content risks were addressed"],
    "issues": ["TikTok conversions remain relatively low", "Some content CTAs and landing-page journeys need improvement"],
    "recommendations": ["Continue using in-depth long-form reviews in the next campaign", "Make CTAs clearer for high-intent content", "Retain the advertising-disclosure check before publication"],
}

CRISIS_DETAILS = {
    "kol_handle": CRISIS_KOL,
    "brand": "BYD",
    "market": "Germany",
    "owner": "Project Owner",
    "response_deadline": "Within 2 hours",
    "impact": {
        "projects": 3,
        "blocked_contents": 9,
        "published_contents": 12,
        "open_tasks": 11,
    },
    "evidence": [
        {"source": "News Coverage", "status": "Collected", "note": "Awaiting cross-source verification"},
        {"source": "Trending-Topic Screenshot", "status": "Collected", "note": "For use as a public-sentiment signal only"},
        {"source": "Creator Statement", "status": "Needs Verification", "note": "Not yet confirmed"},
        {"source": "Police Information", "status": "Needs Verification", "note": "Awaiting an official source"},
    ],
    "actions": [
        {"key": "pause-content", "label": "Pause content pending publication", "done": True},
        {"key": "stop-media", "label": "Stop expanding paid media placements", "done": True},
        {"key": "check-whitelist", "label": "Verify whitelist authorization", "done": False},
        {"key": "hold-payment", "label": "Pause payment and request commercial approval", "done": False},
        {"key": "legal-review", "label": "Submit for legal review", "done": False},
    ],
    "timeline": [
        {"time": "08-15 09:10", "event": "Trending-topic signal detected"},
        {"time": "08-15 09:25", "event": "Cross-source fact-check started"},
        {"time": "08-15 09:40", "event": "Related content pending publication was paused"},
    ],
}


def _analysis_seed() -> dict:
    return {
        "overview": OVERVIEW_DATA,
        "targets": TARGET_DATA,
        "platforms": PLATFORM_DATA,
        "ranking": KOL_RANKING,
        "highlights": CONTENT_HIGHLIGHTS,
        "kol_details": {"@AutoBildDE": AUTOBILD_DETAIL},
        "sentiment": SENTIMENT_DATA,
        "review": REVIEW_DATA,
    }

def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_post_campaign_seed(session: Session) -> None:
    review = session.scalar(
        select(CampaignReview).where(CampaignReview.campaign == CAMPAIGN)
    )
    if review is None:
        session.add(
            CampaignReview(
                campaign=CAMPAIGN,
                analysis_data=_analysis_seed()
            )
        )

    crisis = session.scalar(
        select(KolCrisisEvent).where(
            KolCrisisEvent.crisis_code == CRISIS_CODE
        )
    )

    kol = session.scalar(
        select(Kol).where(Kol.handle == CRISIS_KOL)
    )

    if crisis is None:
        crisis = KolCrisisEvent(
            crisis_code=CRISIS_CODE,
            kol_id=kol.id if kol else None,
            title="Creator accused of illegal conduct trends online",
            level="Critical",
            status="In Progress",
            verified=False,
            details=CRISIS_DETAILS,
        )
        session.add(crisis)
    else:
        crisis.kol_id = kol.id if kol else None
        crisis.details = {
            **(crisis.details or {}),
            "kol_handle": CRISIS_KOL,
        }

    session.commit()


def _review(session: Session) -> CampaignReview:
    ensure_post_campaign_seed(session)
    review = session.scalar(select(CampaignReview).where(CampaignReview.campaign == CAMPAIGN))
    if review is None:
        raise RuntimeError("campaign review seed missing")
    return review


def _active_performance_reviews(session: Session) -> list[PerformanceReview]:
    return list(
        session.scalars(
            select(PerformanceReview).where(
                PerformanceReview.campaign == CAMPAIGN,
                PerformanceReview.deleted_at.is_(None),
            )
        )
    )


def get_campaign_overview(session: Session) -> dict:
    review = _review(session)
    data = review.analysis_data or {}
    fallback = data.get("overview", {})
    records = _active_performance_reviews(session)

    if records:
        impressions = sum(item.impressions or 0 for item in records)
        engagements = sum(item.engagements or 0 for item in records)
        conversions = sum(item.conversions or 0 for item in records)
        engagement_rate = round(engagements / impressions * 100, 1) if impressions else 0
    else:
        impressions = fallback.get("impressions", 0)
        engagements = fallback.get("engagements", 0)
        conversions = fallback.get("conversions", 0)
        engagement_rate = fallback.get("engagement_rate", 0)

    return {
        "campaign": CAMPAIGN,
        "brand": "BYD",
        "market": "Germany",
        "metrics": {
            "impressions": impressions,
            "engagements": engagements,
            "conversions": conversions,
            "engagement_rate": engagement_rate,
            "target_completion": fallback.get("target_completion", 112),
        },
        "targets": data.get("targets", {}),
        "platforms": data.get("platforms", []),
        "ranking": data.get("ranking", []),
        "highlights": data.get("highlights", []),
        "updated_at": review.updated_at.isoformat(),
    }


def _find_kol(session: Session, key: str) -> Kol | None:
    if key.isdigit():
        return session.get(Kol, int(key))
    return session.scalar(select(Kol).where(Kol.handle == key))


def get_kol_performance(session: Session, key: str) -> dict | None:
    review = _review(session)
    data = review.analysis_data or {}
    kol = _find_kol(session, key)
    handle = kol.handle if kol and kol.handle else key
    fallback = (data.get("kol_details") or {}).get(handle)

    perf = None
    tasks: list[ContentTask] = []
    if kol is not None:
        perf = session.scalar(
            select(PerformanceReview)
            .where(
                PerformanceReview.kol_id == kol.id,
                PerformanceReview.campaign == CAMPAIGN,
                PerformanceReview.deleted_at.is_(None),
            )
            .order_by(PerformanceReview.created_at.desc())
        )
        tasks = list(session.scalars(select(ContentTask).where(ContentTask.kol_id == kol.id)))

    if fallback is None and perf is None:
        return None

    result = dict(fallback or {})
    result["kol_id"] = kol.id if kol else None
    result["name"] = (kol.name if kol else None) or result.get("name") or handle.lstrip("@")
    result["handle"] = handle
    result["platform"] = (kol.platform if kol else None) or result.get("platform") or "—"

    if perf is not None:
        result["impressions"] = perf.impressions or 0
        result["engagements"] = perf.engagements or 0
        result["conversions"] = perf.conversions or 0

    if tasks:
        result["contents"] = [
            {
                "title": task.title,
                "platform": task.platform,
                "impressions": (task.metrics or {}).get("impressions", 0),
                "engagement_rate": (task.metrics or {}).get("engagement_rate", 0),
                "conversions": (task.metrics or {}).get("conversions", 0),
                "result": "Published" if task.execution_stage == "Published / Monitoring" else task.execution_stage,
            }
            for task in tasks[:8]
        ]
    return result


def get_sentiment_analysis(session: Session) -> dict:
    review = _review(session)
    data = review.analysis_data or {}
    return {
        "campaign": CAMPAIGN,
        "kol": "@AutoBildDE",
        "content": "Seal U Germany Launch Experience",
        **data.get("sentiment", {}),
    }


def get_campaign_review(session: Session) -> dict:
    review = _review(session)
    data = review.analysis_data or {}
    return {
        "campaign": review.campaign,
        "decision": review.decision,
        "status": review.status,
        "notes": review.notes,
        **data.get("review", {}),
        "updated_at": review.updated_at.isoformat(),
    }


def save_campaign_decision(session: Session, decision: str, notes: str | None = None) -> CampaignReview:
    if decision not in ALLOWED_REVIEW_DECISIONS:
        raise ValueError("Invalid partnership decision")
    review = _review(session)
    review.decision = decision
    review.status = "Confirmed"
    if notes is not None:
        review.notes = notes
    review.updated_at = _now()
    session.commit()
    session.refresh(review)
    return review


def list_crises(session: Session, include_closed: bool = False) -> list[KolCrisisEvent]:
    ensure_post_campaign_seed(session)
    statement = select(KolCrisisEvent).order_by(KolCrisisEvent.created_at.desc())
    records = list(session.scalars(statement))
    if include_closed:
        return records
    return [item for item in records if item.status != "Closed"]


def get_crisis(session: Session, crisis_code: str) -> KolCrisisEvent | None:
    ensure_post_campaign_seed(session)
    return session.scalar(select(KolCrisisEvent).where(KolCrisisEvent.crisis_code == crisis_code))


def serialize_crisis(crisis: KolCrisisEvent, include_detail: bool = False) -> dict:
    details = crisis.details or {}
    payload = {
        "crisis_code": crisis.crisis_code,
        "kol_id": crisis.kol_id,
        "kol": crisis.kol.handle if crisis.kol and crisis.kol.handle else details.get("kol_handle", "—"),
        "title": crisis.title,
        "level": crisis.level,
        "status": crisis.status,
        "verified": crisis.verified,
        "decision": crisis.decision,
        "impact": details.get("impact", {}),
        "created_at": crisis.created_at.isoformat(),
        "updated_at": crisis.updated_at.isoformat(),
    }
    if include_detail:
        payload.update(
            {
                "brand": details.get("brand", ""),
                "market": details.get("market", ""),
                "owner": details.get("owner", ""),
                "response_deadline": details.get("response_deadline", ""),
                "evidence": details.get("evidence", []),
                "actions": details.get("actions", []),
                "timeline": details.get("timeline", []),
            }
        )
    return payload


def apply_crisis_action(session: Session, crisis: KolCrisisEvent, action: str) -> None:
    details = dict(crisis.details or {})
    actions = [dict(item) for item in details.get("actions", [])]
    matched = False
    for item in actions:
        if item.get("key") == action:
            item["done"] = True
            matched = True
            break
    if not matched:
        raise ValueError("Unknown incident-response action")

    timeline = [dict(item) for item in details.get("timeline", [])]
    label = next((item.get("label") for item in actions if item.get("key") == action), action)
    timeline.append({"time": _now().strftime("%m-%d %H:%M"), "event": f"Completed: {label}"})
    details["actions"] = actions
    details["timeline"] = timeline
    crisis.details = details
    if action == "legal-review":
        crisis.verified = True
    crisis.updated_at = _now()
    session.commit()


def save_crisis_decision(session: Session, crisis: KolCrisisEvent, decision: str) -> None:
    if decision not in ALLOWED_CRISIS_DECISIONS:
        raise ValueError("Invalid incident resolution")
    crisis.decision = decision
    crisis.status = "Decision Recorded"
    details = dict(crisis.details or {})
    timeline = [dict(item) for item in details.get("timeline", [])]
    timeline.append({"time": _now().strftime("%m-%d %H:%M"), "event": f"Management decision: {decision}"})
    details["timeline"] = timeline
    crisis.details = details
    crisis.updated_at = _now()
    session.commit()


def close_crisis(session: Session, crisis: KolCrisisEvent) -> None:
    if not crisis.decision:
        raise ValueError("Record a resolution before closing the incident")
    crisis.status = "Closed"
    details = dict(crisis.details or {})
    timeline = [dict(item) for item in details.get("timeline", [])]
    timeline.append({"time": _now().strftime("%m-%d %H:%M"), "event": "Incident closed"})
    details["timeline"] = timeline
    crisis.details = details
    crisis.updated_at = _now()
    session.commit()


def active_crisis_for_task(session: Session, task: ContentTask) -> KolCrisisEvent | None:
    for crisis in list_crises(session):
        handle = (crisis.details or {}).get("kol_handle")
        if task.kol_id is not None and crisis.kol_id == task.kol_id:
            return crisis
        if handle and task.kol_handle == handle:
            return crisis
    return None
