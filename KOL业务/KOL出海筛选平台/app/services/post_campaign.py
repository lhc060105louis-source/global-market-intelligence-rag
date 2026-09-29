from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignReview, ContentTask, Kol, KolCrisisEvent, PerformanceReview

CAMPAIGN = "BYD 德国新车上市传播项目"
CRISIS_CODE = "CRISIS-20260815-001"
CRISIS_KOL = "@EVMotionDE"

ALLOWED_REVIEW_DECISIONS = {
    "推荐继续合作",
    "有条件继续合作",
    "调整合作方式",
    "暂不继续合作",
}
ALLOWED_CRISIS_DECISIONS = {
    "继续观察",
    "限制露出",
    "暂停全部合作",
    "终止并切割",
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
    {"type": "最佳内容", "title": "Seal U 德国首发体验", "note": "长视频互动和转化表现稳定。"},
    {"type": "待优化", "title": "TikTok 短内容", "note": "转化偏低，下一轮需要加强 CTA 和落地页承接。"},
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
        {"title": "Seal U 德国首发体验", "platform": "YouTube", "impressions": 860000, "engagement_rate": 9.1, "conversions": 1420, "result": "最佳内容"},
        {"title": "Seal U 城市通勤体验", "platform": "Instagram", "impressions": 510000, "engagement_rate": 8.4, "conversions": 760, "result": "稳定"},
        {"title": "智能座舱功能演示", "platform": "Instagram", "impressions": 430000, "engagement_rate": 7.9, "conversions": 620, "result": "稳定"},
        {"title": "充电与续航问答", "platform": "YouTube", "impressions": 340000, "engagement_rate": 6.8, "conversions": 440, "result": "待优化"},
    ],
    "trend": [38, 67, 91, 116, 138, 151, 164],
    "benchmarks": [
        {"name": "互动率", "kol": 8.6, "project": 7.4, "industry": 6.2},
        {"name": "转化率", "kol": 0.15, "project": 0.14, "industry": 0.11},
        {"name": "完播率", "kol": 48, "project": 43, "industry": 39},
    ],
    "execution": {
        "Brief 一致性": "良好",
        "交付及时性": "良好",
        "品牌安全": "良好",
        "广告披露": "已修正",
        "合作建议": "建议继续合作",
    },
}

SENTIMENT_DATA = {
    "sample_size": 18_426,
    "positive": 76,
    "neutral": 18,
    "negative": 6,
    "topics": [
        {"name": "空间表现", "share": 31, "sentiment": "正向"},
        {"name": "续航与补能", "share": 24, "sentiment": "中性"},
        {"name": "智能座舱", "share": 18, "sentiment": "正向"},
        {"name": "价格价值", "share": 15, "sentiment": "中性"},
        {"name": "设计外观", "share": 12, "sentiment": "正向"},
    ],
    "vehicle_feedback": [
        {"name": "空间 / 实用性", "score": 89, "note": "认可度高"},
        {"name": "续航 / 补能", "score": 72, "note": "高速续航和补能便利性仍有疑虑"},
        {"name": "智能 / 软件", "score": 84, "note": "座舱体验反馈较好"},
        {"name": "设计 / 品质", "score": 88, "note": "外观和质感评价积极"},
    ],
    "brand_attitude": {"before": 32, "after": 41},
    "risk_items": [
        {"name": "广告披露补录", "status": "已完成"},
        {"name": "充电速度质疑", "status": "已回应"},
        {"name": "参数引用偏差", "status": "已修正"},
    ],
}

REVIEW_DATA = {
    "scores": {
        "目标达成": 112,
        "内容传播": 91,
        "用户反馈": 86,
        "执行质量": 88,
        "风险控制": 94,
        "商业价值": 89,
    },
    "overall_score": 91,
    "summary": "项目整体达到预期，头部 KOL 的长视频内容贡献最明显。",
    "strengths": ["核心内容互动质量较高", "头部 KOL 转化表现稳定", "主要内容风险已完成处理"],
    "issues": ["TikTok 转化仍偏低", "部分内容 CTA 和落地页承接需要加强"],
    "recommendations": ["下一轮继续使用长视频深度评测", "提高高意向内容的 CTA 清晰度", "在发布前保留广告披露检查"],
}

CRISIS_DETAILS = {
    "kol_handle": CRISIS_KOL,
    "brand": "BYD",
    "market": "德国",
    "owner": "项目负责人",
    "response_deadline": "2 小时内",
    "impact": {
        "projects": 3,
        "blocked_contents": 9,
        "published_contents": 12,
        "open_tasks": 11,
    },
    "evidence": [
        {"source": "新闻报道", "status": "已收集", "note": "等待跨来源核验"},
        {"source": "热搜截图", "status": "已收集", "note": "仅作为舆情信号"},
        {"source": "KOL 声明", "status": "待核验", "note": "尚未确认"},
        {"source": "警方信息", "status": "待核验", "note": "等待官方来源"},
    ],
    "actions": [
        {"key": "pause-content", "label": "暂停待发布内容", "done": True},
        {"key": "stop-media", "label": "停止新增媒介扩量", "done": True},
        {"key": "check-whitelist", "label": "核查白名单授权", "done": False},
        {"key": "hold-payment", "label": "暂停付款并提交商务确认", "done": False},
        {"key": "legal-review", "label": "提交法务复核", "done": False},
    ],
    "timeline": [
        {"time": "08-15 09:10", "event": "监测到热搜信号"},
        {"time": "08-15 09:25", "event": "启动跨来源事实核查"},
        {"time": "08-15 09:40", "event": "暂停关联待发布内容"},
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
            title="KOL 涉嫌违法事件登上热搜",
            level="重大",
            status="处理中",
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
        "market": "德国",
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
                "result": "已发布" if task.execution_stage == "已发布/监测" else task.execution_stage,
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
        "content": "Seal U 德国首发体验",
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
        raise ValueError("无效的合作决策")
    review = _review(session)
    review.decision = decision
    review.status = "已确认"
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
    return [item for item in records if item.status != "已关闭"]


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
        raise ValueError("未知的应急任务")

    timeline = [dict(item) for item in details.get("timeline", [])]
    label = next((item.get("label") for item in actions if item.get("key") == action), action)
    timeline.append({"time": _now().strftime("%m-%d %H:%M"), "event": f"完成：{label}"})
    details["actions"] = actions
    details["timeline"] = timeline
    crisis.details = details
    if action == "legal-review":
        crisis.verified = True
    crisis.updated_at = _now()
    session.commit()


def save_crisis_decision(session: Session, crisis: KolCrisisEvent, decision: str) -> None:
    if decision not in ALLOWED_CRISIS_DECISIONS:
        raise ValueError("无效的处置决定")
    crisis.decision = decision
    crisis.status = "已决定"
    details = dict(crisis.details or {})
    timeline = [dict(item) for item in details.get("timeline", [])]
    timeline.append({"time": _now().strftime("%m-%d %H:%M"), "event": f"管理决定：{decision}"})
    details["timeline"] = timeline
    crisis.details = details
    crisis.updated_at = _now()
    session.commit()


def close_crisis(session: Session, crisis: KolCrisisEvent) -> None:
    if not crisis.decision:
        raise ValueError("请先确认处置决定")
    crisis.status = "已关闭"
    details = dict(crisis.details or {})
    timeline = [dict(item) for item in details.get("timeline", [])]
    timeline.append({"time": _now().strftime("%m-%d %H:%M"), "event": "事件关闭"})
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
