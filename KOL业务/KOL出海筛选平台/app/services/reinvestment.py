from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignReview, ContentTask, Kol, KolCrisisEvent, PerformanceReview

STATE_KEY = "__asset_reinvestment__"

PROJECT = {
    "name": "XPENG G6 英国试驾传播",
    "brand": "XPENG",
    "model": "G6",
    "market": "英国",
    "market_code": "GB",
    "platforms": ["YouTube", "Instagram", "TikTok"],
    "objective": "试驾传播、深度认知与高意向线索",
    "budget": 60000,
    "currency": "GBP",
    "period": "2026 Q4",
}

ASSETS = [
    {"handle": "@AutoBildDE", "name": "AutoBildDE", "country": "DE", "market": "德国", "platform": "YouTube", "followers": 1420000, "collaborations": 4, "recent_project": "BYD Seal U 德国上市传播", "recent_score": 91, "list_status": "优选", "risk": "无重大风险", "major_risk": False, "data_completeness": 96, "last_collaboration": "2026-08", "content_assets": 13, "avg_engagement": 8.6, "conversions": 3240, "content_quality": 92},
    {"handle": "@EVReviewUK", "name": "EVReviewUK", "country": "GB", "market": "英国", "platform": "Instagram", "followers": 865000, "collaborations": 3, "recent_project": "BYD 英国试驾传播", "recent_score": 88, "list_status": "条件", "risk": "低风险", "major_risk": False, "data_completeness": 92, "last_collaboration": "2026-07", "content_assets": 9, "avg_engagement": 8.1, "conversions": 2380, "content_quality": 90},
    {"handle": "@Carwow", "name": "Carwow", "country": "GB", "market": "英国", "platform": "YouTube", "followers": 9700000, "collaborations": 5, "recent_project": "XPENG G9 英国传播", "recent_score": 90, "list_status": "优选", "risk": "无重大风险", "major_risk": False, "data_completeness": 98, "last_collaboration": "2026-06", "content_assets": 17, "avg_engagement": 7.8, "conversions": 2140, "content_quality": 94},
    {"handle": "@MobiliteVerte", "name": "MobiliteVerte", "country": "FR", "market": "法国", "platform": "TikTok", "followers": 612000, "collaborations": 2, "recent_project": "BYD 欧洲短视频传播", "recent_score": 76, "list_status": "观察", "risk": "普通负面评论", "major_risk": False, "data_completeness": 84, "last_collaboration": "2026-05", "content_assets": 6, "avg_engagement": 6.5, "conversions": 1310, "content_quality": 82},
    {"handle": "@EVMotionDE", "name": "EVMotionDE", "country": "DE", "market": "德国", "platform": "YouTube", "followers": 740000, "collaborations": 2, "recent_project": "BYD 德国新车上市传播", "recent_score": 71, "list_status": "暂停", "risk": "重大主体风险待核验", "major_risk": True, "data_completeness": 80, "last_collaboration": "2026-08", "content_assets": 7, "avg_engagement": 6.9, "conversions": 980, "content_quality": 78},
]

ARCHIVES = {
    "@AutoBildDE": {
        "markets": ["德国", "英国"],
        "project_history": [
            {"project": "BYD Seal U 德国上市传播", "date": "2026-08", "platform": "YouTube", "result": "目标完成 128%", "score": 91, "note": "长视频互动和转化表现稳定"},
            {"project": "XPENG G9 欧洲试驾", "date": "2026-03", "platform": "YouTube", "result": "目标完成 116%", "score": 88, "note": "专业评测内容可复用"},
            {"project": "BYD Atto 3 产品教育", "date": "2025-10", "platform": "YouTube", "result": "目标完成 104%", "score": 84, "note": "参数说明清晰，交付准时"},
            {"project": "欧洲 EV 选购专题", "date": "2025-05", "platform": "YouTube", "result": "目标完成 97%", "score": 79, "note": "样本较早，仅作趋势参考"},
        ],
        "reusable_assets": ["Seal U 德国首发体验长视频", "车型参数问答素材", "德语试驾口播结构"],
        "risks": ["2026-08 广告披露补录：已修正", "未发现已确认的重大主体风险"],
        "audit": ["2026-08-20 后期复盘写回", "2026-08-21 数据完整度复核", "2026-08-25 进入复投评估候选"],
    },
    "@EVReviewUK": {
        "markets": ["英国"],
        "project_history": [
            {"project": "BYD 英国试驾传播", "date": "2026-07", "platform": "Instagram", "result": "目标完成 119%", "score": 88, "note": "短视频互动效率较高"},
            {"project": "XPENG P7 英国社媒合作", "date": "2026-02", "platform": "Instagram", "result": "目标完成 109%", "score": 84, "note": "档期配合稳定"},
            {"project": "欧洲新能源车专题", "date": "2025-09", "platform": "YouTube", "result": "目标完成 102%", "score": 81, "note": "评论质量较好"},
        ],
        "reusable_assets": ["英国用户试驾问答", "竖屏车型亮点模板"],
        "risks": ["未发现已确认的重大主体风险"],
        "audit": ["2026-07-30 后期复盘写回", "2026-08-25 复投候选更新"],
    },
}

EVALUATIONS = {
    "@AutoBildDE": {"score": 82, "status": "有条件继续合作", "quote_cap": 18000, "content_format": "1 条 YouTube 深度试驾 + 1 条短切片", "schedule": "上市前 10 天锁定脚本，上市周发布", "exclusivity": "同级竞品 30 天软排他", "dimensions": [88, 76, 92, 74, 86, 94]},
    "@EVReviewUK": {"score": 87, "status": "优先", "quote_cap": 15000, "content_format": "2 条 Instagram Reels + Stories", "schedule": "试驾后 7 天内发布", "exclusivity": "同级竞品 14 天软排他", "dimensions": [94, 88, 89, 82, 86, 84]},
    "@Carwow": {"score": 91, "status": "优先", "quote_cap": 28000, "content_format": "1 条 YouTube 核心试驾", "schedule": "上市周核心档期", "exclusivity": "按合同确认", "dimensions": [96, 94, 95, 76, 91, 93]},
    "@MobiliteVerte": {"score": 68, "status": "观察", "quote_cap": 8000, "content_format": "2 条 TikTok 短视频", "schedule": "上市后扩散", "exclusivity": "无强制排他", "dimensions": [55, 72, 76, 78, 73, 80]},
    "@EVMotionDE": {"score": 64, "status": "暂停评估", "quote_cap": 0, "content_format": "待风险核验后再定义", "schedule": "暂停", "exclusivity": "—", "dimensions": [62, 70, 72, 69, 74, 38]},
}

DIMENSIONS = [
    ("受众匹配", "结合历史市场覆盖与目标项目受众结构"),
    ("内容适配", "结合历史内容质量、车型题材与可复用资产"),
    ("平台表现", "结合平台历史互动与内容表现"),
    ("商业效率", "结合历史报价、转化和项目预算约束"),
    ("执行可靠性", "结合交付、Brief 配合与档期记录"),
    ("品牌安全", "结合主体风险、披露与历史合规记录"),
]

SCENARIOS = [
    {"id": "A", "name": "核心覆盖", "kols": ["@Carwow", "@EVReviewUK"], "cost": 52000, "reach_range": "1.8M–2.4M", "engagement_range": "120K–170K", "confidence": "中高", "note": "优先英国核心受众，预算留有机动空间"},
    {"id": "B", "name": "专业背书", "kols": ["@Carwow", "@AutoBildDE"], "cost": 58000, "reach_range": "2.0M–2.7M", "engagement_range": "130K–180K", "confidence": "中", "note": "专业影响力强，但跨市场内容需确认英国受众占比"},
    {"id": "C", "name": "社交扩散", "kols": ["@EVReviewUK", "@MobiliteVerte"], "cost": 34000, "reach_range": "1.2M–1.8M", "engagement_range": "90K–145K", "confidence": "中", "note": "成本低、短内容覆盖高，深度认知能力较弱"},
    {"id": "D", "name": "平衡方案", "kols": ["@Carwow", "@EVReviewUK", "@MobiliteVerte"], "cost": 60000, "reach_range": "2.3M–3.0M", "engagement_range": "155K–215K", "confidence": "中", "note": "预算刚好用满，需保留报价变动预案"},
]

TASKS = [
    {"task_code": "ACT-001", "kol": "@Carwow", "task": "确认报价与内容包", "owner": "商务负责人", "due_at": "2026-09-02", "status": "进行中", "dependency": "无"},
    {"task_code": "ACT-002", "kol": "@Carwow", "task": "锁定试驾与发布档期", "owner": "项目经理", "due_at": "2026-09-04", "status": "待办", "dependency": "ACT-001"},
    {"task_code": "ACT-003", "kol": "@EVReviewUK", "task": "确认 Reels 内容形式", "owner": "内容负责人", "due_at": "2026-09-03", "status": "待办", "dependency": "无"},
    {"task_code": "ACT-004", "kol": "@EVReviewUK", "task": "准备 Brief 与披露要求", "owner": "内容负责人", "due_at": "2026-09-06", "status": "待办", "dependency": "ACT-003"},
    {"task_code": "ACT-005", "kol": "@MobiliteVerte", "task": "确认是否纳入补充扩散", "owner": "媒介负责人", "due_at": "2026-09-05", "status": "待办", "dependency": "方案审批"},
    {"task_code": "ACT-006", "kol": "项目组", "task": "完成名单风险复核", "owner": "品牌安全", "due_at": "2026-09-01", "status": "进行中", "dependency": "无"},
]


def _now():
    return datetime.now(timezone.utc)


def _read_state(session: Session):
    row = session.scalar(select(CampaignReview).where(CampaignReview.campaign == STATE_KEY))
    if row is None:
        row = CampaignReview(
            campaign=STATE_KEY,
            status="系统状态",
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
    crises = list(session.scalars(select(KolCrisisEvent).where(KolCrisisEvent.status != "已关闭")))

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
            item["risk"] = "存在未关闭的主体级重大风险事件"
            item["major_risk"] = True
            item["list_status"] = "暂停"

    _, state = _read_state(session)
    for item in assets:
        saved = state["governance"].get(item["handle"])
        if not saved:
            continue
        item["list_status"] = saved.get("status", item["list_status"])
        item["risk"] = saved.get("reason") or item["risk"]
        if item["list_status"] in {"暂停", "禁止"}:
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

    counts = {name: sum(1 for item in assets if item["list_status"] == name) for name in ["优选", "条件", "观察", "暂停", "禁止"]}
    attention = [{"type": "风险", "text": f"{item['handle']}：{item['risk']}"} for item in assets if item["major_risk"]]
    attention += [{"type": "资料", "text": f"{item['handle']} 数据完整度 {item['data_completeness']}%，建议复投前补齐"} for item in assets if item["data_completeness"] < 85]

    by_market = {}
    by_platform = {}
    for item in assets:
        by_market[item["market"]] = by_market.get(item["market"], 0) + 1
        by_platform[item["platform"]] = by_platform.get(item["platform"], 0) + 1

    return {
        "context": "历史合作资产池",
        "metrics": {
            "total": len(assets),
            "preferred": counts["优选"],
            "conditional": counts["条件"],
            "watch": counts["观察"],
            "blocked": counts["暂停"] + counts["禁止"],
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
                {"project": item["recent_project"], "date": item["last_collaboration"], "platform": item["platform"], "result": f"复盘分 {item['recent_score']}", "score": item["recent_score"], "note": "保留最近一次合作结果"},
                {"project": "历史合作记录", "date": "2025-12", "platform": item["platform"], "result": "历史样本", "score": max(0, item["recent_score"] - 5), "note": "仅用于档案追溯"},
            ],
            "reusable_assets": ["历史内容素材", "合作 Brief 与执行记录"],
            "risks": [item["risk"]],
            "audit": [f"{item['last_collaboration']} 最近合作记录写回"],
        }

    if item.get("kol_id"):
        records = list(session.scalars(select(PerformanceReview).where(PerformanceReview.kol_id == item["kol_id"], PerformanceReview.deleted_at.is_(None)).order_by(PerformanceReview.created_at.desc())))
        if records:
            archive["project_history"] = [
                {
                    "project": row.campaign,
                    "date": row.created_at.strftime("%Y-%m"),
                    "platform": item["platform"],
                    "result": f"曝光 {row.impressions if row.impressions is not None else '未取得'} / 互动 {row.engagements if row.engagements is not None else '未取得'} / 转化 {row.conversions if row.conversions is not None else '未取得'}",
                    "score": None,
                    "note": "来自原有合作效果记录",
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
        "trend_note": "趋势仅反映历史项目，不代表下一项目表现" if score_count >= 3 else "样本不足时保留单次结果，不生成趋势",
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
    blocked = item["major_risk"] or item["list_status"] in {"暂停", "禁止"}
    dimensions = []

    for i, (name, evidence) in enumerate(DIMENSIONS):
        limitation = "无关键缺失" if item["data_completeness"] >= 90 else "部分历史样本不足，需补充后再确认"
        if name == "品牌安全" and blocked:
            limitation = "存在主体级风险阻断，需先人工核验"
        dimensions.append({"name": name, "score": seed["dimensions"][i], "evidence": evidence, "limitation": limitation})

    approval = state["approvals"].get(item["handle"], {"decision": "待审批", "note": "", "updated_at": None})
    return {
        "kol": {"handle": item["handle"], "name": item["name"], "market": item["market"], "platform": item["platform"]},
        "project": PROJECT,
        "suggestion_score": seed["score"],
        "suggestion_status": "暂停评估" if blocked else seed["status"],
        "data_completeness": item["data_completeness"],
        "major_risk": blocked,
        "dimensions": dimensions,
        "conditions": {
            "quote_cap": seed["quote_cap"],
            "currency": PROJECT["currency"],
            "content_format": seed["content_format"],
            "schedule": seed["schedule"],
            "disclosure": "按英国商业合作披露要求执行",
            "exclusivity": seed["exclusivity"],
            "data_required": "发布后回传平台截图、基础互动与转化数据",
        },
        "approval": approval,
        "note": "建议分用于当前项目比较，重大风险和人工审批单独处理。",
    }


def save_evaluation_approval(session: Session, key: str, decision: str, note=None):
    if decision not in {"批准复投", "有条件批准", "退回补充", "不批准"}:
        raise ValueError("无效的复投审批决定")
    item = _find_asset(session, key)
    if item is None:
        raise LookupError("KOL 不存在")

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
            "availability": "可协调",
            "risk": item["risk"],
            "blocked": evaluation["major_risk"],
        })

    scenarios = []
    for item in SCENARIOS:
        row = dict(item)
        row["selected"] = row["id"] == selected
        row["budget_usage"] = round(row["cost"] / PROJECT["budget"] * 100, 1)
        row["assumption"] = "基于历史样本和当前报价上限估算"
        scenarios.append(row)

    current = next(item for item in scenarios if item["selected"])
    return {
        "project": PROJECT,
        "candidates": candidates,
        "scenarios": scenarios,
        "selected_scenario": selected,
        "checks": [
            {"name": "预算", "status": "通过" if current["cost"] <= PROJECT["budget"] else "超预算", "detail": f"{current['cost']:,} / {PROJECT['budget']:,} {PROJECT['currency']}"},
            {"name": "角色覆盖", "status": "通过", "detail": "核心覆盖与扩散角色均有候选"},
            {"name": "受众重叠", "status": "提示", "detail": "历史样本估算约 18%，仅作方案比较"},
            {"name": "主体风险", "status": "通过", "detail": "当前方案未包含暂停或禁止对象"},
        ],
        "prediction_note": "触达与互动为参考区间，不作为实际业绩承诺。",
    }


def select_portfolio_scenario(session: Session, scenario_id: str):
    if scenario_id not in {item["id"] for item in SCENARIOS}:
        raise ValueError("未知的组合方案")
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
            "scope": saved.get("scope") or "欧洲汽车合作项目",
            "reason": saved.get("reason") or item["risk"],
            "affected_projects": 3 if item["major_risk"] else 0,
            "owner": saved.get("owner") or "品牌安全 / 项目组",
            "recent_change": saved.get("updated_at") or item["last_collaboration"],
            "review_at": saved.get("review_at") or "按项目复核",
            "major_risk": item["major_risk"],
        })

    counts = {name: sum(1 for item in rows if item["status"] == name) for name in ["优选", "条件", "观察", "暂停", "禁止"]}
    risk_row = next((item for item in rows if item["major_risk"]), None)
    return {
        "metrics": {**counts, "pending_approval": sum(1 for item in rows if item["status"] in {"条件", "观察", "暂停"})},
        "risk_banner": {
            "visible": risk_row is not None,
            "title": "重大主体风险需先核验，再决定合作资格" if risk_row else "当前无重大主体风险",
            "kol": risk_row["handle"] if risk_row else None,
            "fact": "当前仅记录风险信号和暂停动作，最终结论仍需人工确认" if risk_row else "",
        },
        "rows": rows,
        "timeline": state["governance_log"][-12:],
        "rule": "名单状态用于跨项目合作资格，普通内容表现不直接等同主体级风险。",
    }


def update_governance(session: Session, key: str, status: str, reason: str, scope=None, review_at=None):
    if status not in {"优选", "条件", "观察", "暂停", "禁止"}:
        raise ValueError("无效的名单状态")
    if not reason.strip():
        raise ValueError("状态调整必须填写原因")

    item = _find_asset(session, key)
    if item is None:
        raise LookupError("KOL 不存在")

    row, state = _read_state(session)
    governance = dict(state["governance"])
    log = list(state["governance_log"])
    saved = {
        "status": status,
        "reason": reason.strip(),
        "scope": scope or "欧洲汽车合作项目",
        "review_at": review_at or "按项目复核",
        "owner": "品牌安全 / 项目组",
        "updated_at": _now().isoformat(),
    }
    governance[item["handle"]] = saved
    log.append({"time": saved["updated_at"], "kol": item["handle"], "event": f"名单状态调整为“{status}”", "reason": reason.strip()})
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
            "stage": "询价" if handle == "@Carwow" else "待联系",
            "quote": "待确认",
            "schedule": "待确认",
            "conditions": "沿用 P30 审批条件",
            "blocker": "需确认是否纳入英国项目补充扩散" if handle == "@MobiliteVerte" else "无",
        })

    stages = {name: 0 for name in ["待联系", "询价", "档期确认", "条件确认", "Brief 准备", "合同中", "已确认", "退出"]}
    for item in candidates:
        stages[item["stage"]] += 1

    return {
        "project": PROJECT,
        "source_plan": f"方案 {scenario['id']} · {scenario['name']}",
        "expected_budget": scenario["cost"],
        "currency": PROJECT["currency"],
        "milestone": "方案已选，进入询价与档期确认",
        "next_deadline": "2026-09-02",
        "owner": "项目负责人",
        "pipeline": stages,
        "candidates": candidates,
        "tasks": tasks,
        "writeback_note": "最终报价、内容包和确认结果在执行后写回历史档案；已确认对象再进入中期监控。",
    }


def update_action_status(session: Session, task_code: str, status: str):
    if status not in {"待办", "进行中", "已完成", "阻塞"}:
        raise ValueError("无效的任务状态")
    if task_code not in {item["task_code"] for item in TASKS}:
        raise LookupError("任务不存在")

    row, state = _read_state(session)
    task_status = dict(state["task_status"])
    task_status[task_code] = status
    state["task_status"] = task_status
    _save_state(session, row, state)
    return {"task_code": task_code, "status": status, "updated_at": _now().isoformat()}
