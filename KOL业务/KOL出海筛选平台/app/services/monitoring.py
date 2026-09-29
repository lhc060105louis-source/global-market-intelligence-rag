from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentRiskEvent, ContentTask, Kol


CAMPAIGN = "BYD 德国新车上市传播项目"
BRAND = "BYD"
MARKET = "DE"
DEMO_UPDATED_AT = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)


def _dt(day: int, hour: int = 10, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc)


def _brief_checks(ad_disclosure: bool = True) -> dict[str, bool]:
    return {
        "车型与版本": True,
        "核心卖点": True,
        "技术参数": True,
        "品牌语气": True,
        "广告披露": ad_disclosure,
        "CTA 与链接": True,
    }


def _final_checks(ad_disclosure: bool = True) -> dict[str, bool]:
    return {
        "Brief 一致性": True,
        "车型与参数": True,
        "品牌与竞品表述": True,
        "ADAS 安全声明": True,
        "广告披露": ad_disclosure,
        "字幕与落地链接": True,
    }


def _version_history(version: str = "V3") -> list[dict[str, str]]:
    records = [
        {"version": "V1", "time": "2026-08-05 10:20", "note": "首次送审"},
        {"version": "V2", "time": "2026-08-06 15:40", "note": "删除绝对化表述"},
        {"version": "V3", "time": "2026-08-07 09:15", "note": "补充官方续航数据来源"},
    ]
    if version == "V1":
        return records[:1]
    if version == "V2":
        return records[:2]
    return records


def _task_seed_rows() -> list[dict]:
    names = [
        ("@AutoVisionDE", "YouTube", "长视频", "BYD Seal U 德国首发深度评测"),
        ("@EVDailyDE", "Instagram", "Reel", "城市通勤体验：Seal U"),
        ("@CarTechBerlin", "TikTok", "短视频", "智能座舱 60 秒体验"),
        ("@GreenDriveDE", "YouTube", "长视频", "家庭用户视角续航评测"),
        ("@MobilityLabDE", "Instagram", "Carousel", "Seal U 设计细节图集"),
        ("@EVReviewUK", "Instagram", "Reel", "BYD Seal U 德国首发体验"),
        ("@AutoPaulDE", "YouTube", "Shorts", "快充速度实测"),
        ("@MiaDrives", "TikTok", "短视频", "泊车辅助体验"),
        ("@EVHeute", "Instagram", "Reel", "柏林道路试驾"),
        ("@RoadFutureDE", "YouTube", "长视频", "底盘与舒适性评测"),
        ("@NeueMobilitaet", "Instagram", "Story", "上市活动现场记录"),
        ("@TechAutoDE", "TikTok", "短视频", "后排空间快速展示"),
        ("@DriveEuropeDE", "YouTube", "长视频", "竞品对比：Seal U vs 同级 SUV"),
        ("@EVCompass", "Instagram", "Reel", "官方续航与真实场景说明"),
        ("@BerlinCars", "TikTok", "短视频", "夜间灯光体验"),
        ("@MotorTalkDE", "YouTube", "长视频", "德国高速道路体验"),
        ("@AutoNina", "Instagram", "Reel", "家庭出行空间体验"),
        ("@ChargePointDE", "YouTube", "Shorts", "充电网络使用演示"),
        ("@EVFocusDE", "TikTok", "短视频", "辅助驾驶功能演示"),
        ("@CarScopeDE", "Instagram", "Carousel", "内饰材质与配置解析"),
        ("@EVMotionDE", "YouTube", "长视频", "首轮脚本与拍摄计划"),
        ("@UrbanEVDE", "Instagram", "Reel", "城市道路首稿"),
        ("@AutoPulseDE", "TikTok", "短视频", "产品亮点初稿"),
        ("@MobilityNowDE", "YouTube", "长视频", "Brief 确认与选题规划"),
    ]

    rows: list[dict] = []
    for index, (handle, platform, content_type, title) in enumerate(names, start=1):
        if index <= 5 or 7 <= index <= 12:
            stage = "已发布/监测"
            review = "已通过"
            monitoring = "监测中"
            actual = _dt(2 + index, 18)
            planned = _dt(2 + index, 18)
        elif index in {13, 14, 15, 16}:
            stage = "待发布"
            review = "已通过"
            monitoring = "待发布"
            actual = None
            planned = _dt(index + 1, 18)
        elif index == 6 or 17 <= index <= 20:
            stage = "审核中"
            review = "待审核"
            monitoring = "未开始"
            actual = None
            planned = _dt(index + 2, 18) if index >= 17 else _dt(17, 18)
        elif 21 <= index <= 23:
            stage = "制作中"
            review = "未送审"
            monitoring = "未开始"
            actual = None
            planned = _dt(index + 2, 18)
        else:
            stage = "待确认 Brief"
            review = "未送审"
            monitoring = "未开始"
            actual = None
            planned = _dt(27, 18)

        risk_level = "无风险"
        if index == 6:
            risk_level = "高风险"
        elif index == 14:
            risk_level = "中风险"
        elif index == 21:
            risk_level = "中风险"

        on_time = index not in {6, 14, 21}
        ad_ok = index != 6
        metrics = {}
        if stage == "已发布/监测":
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
                "duration_seconds": 58 if content_type in {"Reel", "短视频", "Shorts"} else 420,
                "resolution": "1080×1920" if content_type in {"Reel", "短视频", "Shorts", "Story"} else "3840×2160",
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
            title="广告披露缺失",
            level="高",
            status="处理中",
            blocked=True,
            channel="Instagram Caption",
            detection_method="规则 + 语义模型",
            trigger_version="V3",
            impacted_node="终审 / 发布",
            evidence_excerpt="未检测到 Werbung、Anzeige 或 Bezahlte Partnerschaft 等商业合作披露标识。",
            confidence=96.0,
            rules=[
                {"name": "商业合作披露", "status": "失败", "detail": "未发现德语广告披露标识"},
                {"name": "品牌 Brief 4.2", "status": "失败", "detail": "商业合作内容必须显著披露"},
                {"name": "竞品与绝对化声明", "status": "通过", "detail": "未发现违规表述"},
            ],
            timeline=[
                {"time": "08-07 09:15", "event": "KOL 提交 V3"},
                {"time": "08-07 09:16", "event": "系统识别广告披露缺失"},
                {"time": "08-07 09:16", "event": "自动阻断发布"},
                {"time": "08-07 09:35", "event": "项目负责人确认"},
                {"time": "08-07 09:50", "event": "已发送修改要求"},
            ],
            owners={"项目负责人": "Lisa Zhang", "KOL 经理": "Felix Bauer", "合规复核": "Anna Keller", "升级对象": "Brand Legal"},
            remediation_steps=[
                {"key": "pause", "label": "暂停发布", "done": True},
                {"key": "notify", "label": "通知 KOL", "done": True},
                {"key": "new-version", "label": "补充商业披露", "done": False},
                {"key": "legal-review", "label": "品牌法务复核", "done": False},
                {"key": "recheck", "label": "重新检测并解除阻断", "done": False},
            ],
        ),
        ContentRiskEvent(
            risk_code="RISK-20260810-021",
            task_id=tasks["TASK-021"].id,
            title="初稿逾期",
            level="中",
            status="待处理",
            blocked=False,
            channel="内容任务",
            detection_method="排期规则",
            trigger_version="V1",
            impacted_node="制作 / 送审",
            evidence_excerpt="首稿提交时间晚于计划节点，可能压缩后续审核时间。",
            confidence=100.0,
            rules=[{"name": "首稿截止时间", "status": "失败", "detail": "已超过计划提交时间"}],
            timeline=[{"time": "08-10 18:00", "event": "系统标记首稿逾期"}],
            owners={"项目负责人": "Lisa Zhang", "KOL 经理": "Felix Bauer"},
            remediation_steps=[
                {"key": "notify", "label": "提醒 KOL", "done": False},
                {"key": "new-version", "label": "收到初稿", "done": False},
            ],
        ),
        ContentRiskEvent(
            risk_code="RISK-20260811-014",
            task_id=tasks["TASK-014"].id,
            title="产品续航表述待确认",
            level="中",
            status="复核中",
            blocked=False,
            channel="Instagram Caption",
            detection_method="参数规则 + 人工复核",
            trigger_version="V2",
            impacted_node="发布前复核",
            evidence_excerpt="文案使用 WLTP 续航数据，需确认车型版本与官方口径一致。",
            confidence=82.0,
            rules=[{"name": "续航参数来源", "status": "待确认", "detail": "需要品牌产品团队确认"}],
            timeline=[{"time": "08-11 14:20", "event": "参数规则触发人工复核"}],
            owners={"项目负责人": "Lisa Zhang", "产品复核": "Markus Weber"},
            remediation_steps=[
                {"key": "product-review", "label": "产品团队确认", "done": False},
                {"key": "recheck", "label": "重新检测", "done": False},
            ],
        ),
    ]
    session.add_all(risks)
    session.commit()
    _bind_existing_kols(session)


def _task_label(task: ContentTask) -> str:
    return task.kol_handle or task.kol_name or (f"KOL #{task.kol_id}" if task.kol_id else "未绑定 KOL")


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
            .where(ContentRiskEvent.status != "已关闭")
            .order_by(ContentRiskEvent.id)
        )
    )


def build_overview(session: Session) -> dict:
    tasks = list_tasks(session)
    risks = get_open_risks(session)
    published = [task for task in tasks if task.execution_stage == "已发布/监测"]
    on_time = sum(1 for task in tasks if task.on_time)

    stage_order = ["待确认 Brief", "制作中", "审核中", "要求修改", "待发布", "已发布/监测"]
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
            "market": "德国",
            "period": "2026-08-01 — 2026-08-31",
            "updated_at": DEMO_UPDATED_AT.isoformat(),
        },
        "metrics": {
            "total_tasks": len(tasks),
            "on_time_rate": round((on_time / len(tasks) * 100) if tasks else 0, 1),
            "pending_review": sum(1 for task in tasks if task.review_status == "待审核"),
            "pending_publish": sum(1 for task in tasks if task.execution_stage == "待发布"),
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
        raise ValueError("风险事件未关联内容任务")

    if action == "notify":
        _set_step(risk, "notify")
        _append_timeline(risk, "已向 KOL 发送处理提醒")
    elif action == "new-version":
        _set_step(risk, "new-version")
        task.version_label = "V4"
        if risk.risk_code == "RISK-20260804-017":
            task.caption = "Werbung | Der neue BYD Seal U im Alltagstest. Mehr Infos über den Link in Bio."
            brief = dict(task.brief_checks or {})
            brief["广告披露"] = True
            task.brief_checks = brief
            final = dict(task.final_checks or {})
            final["广告披露"] = True
            task.final_checks = final
        history = [dict(item) for item in (task.version_history or [])]
        history.append({"version": "V4", "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "note": "收到整改后新版本"})
        task.version_history = history
        _append_timeline(risk, "确认收到整改后新版本")
    elif action == "legal-review":
        if "legal-review" not in {step.get("key") for step in (risk.remediation_steps or [])}:
            raise ValueError("该风险无需品牌法务复核")
        if not _step_done(risk, "new-version"):
            raise ValueError("请先确认收到新版本")
        _set_step(risk, "legal-review")
        _append_timeline(risk, "品牌法务复核通过")
    elif action == "product-review":
        _set_step(risk, "product-review")
        _append_timeline(risk, "产品团队已确认参数口径")
    elif action == "recheck":
        required = [step.get("key") for step in (risk.remediation_steps or []) if step.get("key") != "recheck"]
        if any(not _step_done(risk, key) for key in required):
            raise ValueError("整改步骤尚未全部完成")
        _set_step(risk, "recheck")
        risk.blocked = False
        risk.status = "已关闭"
        task.risk_level = "无风险"
        _append_timeline(risk, "重新检测通过，风险事件已关闭")
    else:
        raise ValueError("不支持的风险操作")

    session.add_all([risk, task])
    session.commit()
    session.refresh(risk)


def request_task_changes(session: Session, task: ContentTask) -> None:
    task.execution_stage = "要求修改"
    task.review_status = "要求修改"
    task.monitoring_status = "未开始"
    session.add(task)
    session.commit()
    session.refresh(task)


def approve_task(session: Session, task: ContentTask) -> None:
    open_blocker = session.scalar(
        select(ContentRiskEvent.id)
        .where(
            ContentRiskEvent.task_id == task.id,
            ContentRiskEvent.blocked.is_(True),
            ContentRiskEvent.status != "已关闭",
        )
        .limit(1)
    )
    if open_blocker is not None:
        raise ValueError("当前存在阻断发布的风险事件")
    if not all(bool(value) for value in (task.brief_checks or {}).values()):
        raise ValueError("Brief 检查尚未全部通过")
    if not all(bool(value) for value in (task.final_checks or {}).values()):
        raise ValueError("终审检查尚未全部通过")
    task.execution_stage = "待发布"
    task.review_status = "已通过"
    task.monitoring_status = "待发布"
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
