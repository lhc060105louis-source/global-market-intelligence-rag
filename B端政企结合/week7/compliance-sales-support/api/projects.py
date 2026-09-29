# -*- coding: utf-8 -*-
"""项目机会 API —— 项目列表 / 详情 / 评分"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db import load_projects, get_session
from models import Project, EntitlementUsage
from auth_service import optional_identity, current_identity, require_permission
from permissions import can
from rag_event_service import deliver_event, enqueue_and_deliver
from api.rag import project_event_payload

router = APIRouter(prefix="/api/projects", tags=["项目机会"])


def _normalize_project_name(name: str) -> str:
    """用于查重：忽略首尾/连续空白和英文大小写。"""
    return " ".join(name.split()).casefold()


def _preview(p: dict, exact: bool) -> dict:
    if exact: return p
    result = dict(p)
    result["project_name"] = f"{p.get('country','欧洲')} · {p.get('project_type') or '政企采购'}项目"
    result["contracting_authority"] = "升级后查看采购主体"
    result["source_url"] = ""
    result["description"] = (p.get("description") or "")[:60]
    value = p.get("contract_value") or 0
    result["contract_value"] = 0
    result["contract_value_range"] = "未公开" if not value else ("1000万欧元以上" if value >= 10_000_000 else "100万–1000万欧元" if value >= 1_000_000 else "100万欧元以下")
    return result


@router.get("")
def list_projects(identity=Depends(optional_identity)):
    """所有项目,按综合得分降序。"""
    exact = bool(identity and can(identity[1], "project.view_exact"))
    return [_preview(p, exact) for p in load_projects()]


@router.get("/{project_id}")
def project_detail(project_id: int, identity=Depends(optional_identity)):
    with get_session() as s:
        p = s.get(Project, project_id)
        if not p: raise HTTPException(404, f"项目 {project_id} 不存在")
        return _preview(p.to_dict(), bool(identity and can(identity[1], "project.view_exact")))


@router.get("/{project_id}/reveal")
def reveal_project(project_id: int, identity=Depends(current_identity)):
    """专业版直接查看；免费用户每月最多解锁3条精确线索。"""
    user, principal = identity
    with get_session() as s:
        p = s.get(Project, project_id)
        if not p: raise HTTPException(404, "项目不存在")
        if not can(principal, "project.view_exact"):
            period = datetime.now().strftime("%Y-%m")
            existing = s.query(EntitlementUsage).filter(
                EntitlementUsage.user_id == user.id,
                EntitlementUsage.entitlement == "project.monthly_reveal",
                EntitlementUsage.period == period,
            ).all()
            keys = {x.resource_key for x in existing}
            if str(project_id) not in keys:
                if len(keys) >= 3:
                    raise HTTPException(403, {"code": "quota_exceeded", "limit": 3, "period": period})
                s.add(EntitlementUsage(user_id=user.id, entitlement="project.monthly_reveal",
                                       period=period, resource_key=str(project_id)))
                s.commit()
        return p.to_dict()


@router.get("/stats/summary")
def project_summary():
    projs = load_projects()
    if not projs: return {"total": 0, "priority": 0, "watch": 0, "avg_score": 0, "countries": []}
    from collections import Counter
    countries = Counter(p["country"] for p in projs)
    return {
        "total": len(projs), "priority": sum(1 for p in projs if p["project_level"] == "优先跟进"),
        "watch": sum(1 for p in projs if p["project_level"] == "持续观察"),
        "avg_score": round(sum(p["total_score"] for p in projs) / len(projs), 1),
        "countries": [{"name": k, "count": v} for k, v in countries.most_common()],
    }


# 七维权重(对齐 eu-project-scoring-platform 评分模型)
SCORE_DIMS = [
    {"key": "scale_score", "name": "项目规模", "max": 15, "weight": 15},
    {"key": "authority_score", "name": "采购主体", "max": 10, "weight": 10},
    {"key": "technical_score", "name": "技术匹配度", "max": 20, "weight": 25},
    {"key": "compliance_score", "name": "合规可行性", "max": 15, "weight": 15},
    {"key": "local_score", "name": "本地合作可行性", "max": 10, "weight": 10},
    {"key": "conversion_score", "name": "商业转化潜力", "max": 20, "weight": 20},
    {"key": "competition_score", "name": "竞争格局", "max": 10, "weight": 5},
]


@router.get("/{project_id}/scoring")
def project_scoring(project_id: int, _=Depends(require_permission("project.scoring_detail"))):
    """七维评分明细 + 一票否决检查(对齐评分平台模型)。"""
    with get_session() as s:
        p = s.get(Project, project_id)
        if not p: raise HTTPException(404)
    dims = []
    for d in SCORE_DIMS:
        val = getattr(p, d["key"], 0) or 0
        dims.append({"name": d["name"], "score": val, "max": d["max"], "pct": round(val / d["max"] * 100)})
    # 一票否决
    veto = []
    if (p.compliance_score or 0) < 4: veto.append(f"合规可行性低于 4 分(当前 {p.compliance_score})")
    if (p.technical_score or 0) < 5: veto.append(f"技术匹配度低于 5 分(当前 {p.technical_score})")
    if (p.competition_score or 0) < 3: veto.append(f"竞争格局低于 3 分(当前 {p.competition_score})")
    return {
        "project_name": p.project_name, "total_score": p.total_score,
        "project_level": p.project_level, "has_veto": len(veto) > 0, "veto_reasons": veto,
        "dimensions": dims,
    }


# 评分标准详情(带每档说明)
SCORE_CRITERIA = {
    "scale_score": {"name": "项目规模", "max": 15,
        "options": {"15": "合同金额超过 1000 万欧元", "12": "500 万–1000 万欧元", "9": "100 万–500 万欧元", "6": "20 万–100 万欧元", "3": "低于 20 万欧元"}},
    "authority_score": {"name": "采购主体类型", "max": 10,
        "options": {"10": "欧盟机构或 NATO", "8": "国家部委", "6": "大区或省级机构", "4": "市级机构", "2": "学校、医院等基层机构"}},
    "technical_score": {"name": "技术匹配度", "max": 20,
        "options": {"20": "已有成熟方案,具备欧洲案例", "16": "核心需求匹配,仅需少量定制", "12": "方向匹配,需要较大改造", "8": "仅部分模块匹配", "4": "基本不匹配"}},
    "compliance_score": {"name": "合规可行性", "max": 15,
        "options": {"15": "认证齐全,可直接参与", "12": "缺少 1–2 项认证,短期可补", "9": "缺少 3 项以上认证", "6": "需依赖本地合作伙伴", "3": "存在非 EU 企业限制"}},
    "local_score": {"name": "本地合作可行性", "max": 10,
        "options": {"10": "无强制本地合作要求", "8": "建议开展本地合作", "6": "有分包要求,已有合作伙伴", "4": "有分包要求,需重新寻找", "2": "必须本地注册或成立合资公司"}},
    "conversion_score": {"name": "商业转化潜力", "max": 20,
        "options": {"20": "具备标杆、复购和生态带动价值", "16": "可形成标杆案例,较强复制价值", "12": "主要体现单个项目价值", "8": "与企业主营业务关联较弱", "4": "基本无后续商业价值"}},
    "competition_score": {"name": "竞争格局", "max": 10,
        "options": {"10": "预计投标 ≤3 家", "8": "预计 4–6 家,有差异化机会", "6": "预计 7–10 家,含头部企业", "4": "超过 10 家,竞争激烈", "2": "市场长期被少数企业控制"}},
}


@router.get("/criteria/options")
def scoring_criteria():
    """七维评分标准(供前端表单渲染)。"""
    return SCORE_CRITERIA


class ProjectCreate(BaseModel):
    project_name: str
    country: str
    project_type: str = ""
    contracting_authority: str
    contract_value: float = 0
    deadline: str = ""
    source_url: str = ""
    description: str = ""
    stage: str = "评估中"
    scale_score: int = 3
    authority_score: int = 3
    technical_score: int = 3
    compliance_score: int = 3
    local_score: int = 3
    conversion_score: int = 3
    competition_score: int = 3


@router.post("")
def create_project(data: ProjectCreate, _=Depends(require_permission("project.create"))):
    """新增项目,自动计算综合分+等级+一票否决(对齐评分平台模型)。"""
    if not data.project_name.strip() or not data.country.strip() or not data.contracting_authority.strip():
        raise HTTPException(422, "项目名称/国家/采购主体为必填")
    total = data.scale_score + data.authority_score + data.technical_score + data.compliance_score + \
            data.local_score + data.conversion_score + data.competition_score
    # 一票否决
    veto = (data.compliance_score < 4) or (data.technical_score < 5) or (data.competition_score < 3)
    if veto: level = "一票否决"
    elif total >= 70: level = "优先跟进"
    elif total >= 50: level = "持续观察"
    else: level = "暂缓投入"
    with get_session() as s:
        normalized_name = _normalize_project_name(data.project_name)
        duplicate = next(
            (p for p in s.query(Project.id, Project.project_name).all()
             if _normalize_project_name(p.project_name) == normalized_name),
            None,
        )
        if duplicate:
            raise HTTPException(
                409,
                f"项目名称已存在（ID: {duplicate.id}，名称: {duplicate.project_name}）",
            )
        p = Project(
            project_name=data.project_name.strip(), country=data.country.strip(),
            project_type=data.project_type, contracting_authority=data.contracting_authority.strip(),
            contract_value=data.contract_value, deadline=data.deadline, source_url=data.source_url,
            description=data.description, stage=data.stage,
            scale_score=data.scale_score, authority_score=data.authority_score,
            technical_score=data.technical_score, compliance_score=data.compliance_score,
            local_score=data.local_score, conversion_score=data.conversion_score,
            competition_score=data.competition_score,
            total_score=total, project_level=level,
            created_at=datetime.now().isoformat(timespec="seconds"),
            rag_status="draft", version_no=1,
        )
        s.add(p); s.commit(); s.refresh(p)
        return {"status": "created", "id": p.id, "total_score": total, "project_level": level}


@router.post("/{project_id}/publish")
def publish_project(project_id: int, _=Depends(require_permission("project.create"))):
    with get_session() as session:
        project = session.get(Project, project_id)
        if not project: raise HTTPException(404, "项目不存在")
        project.version_no = (project.version_no or 0) + (1 if project.rag_status == "published" else 0)
        project.rag_status = "published"
        project.published_at = datetime.now(timezone.utc)
        event_id = enqueue_and_deliver(session, project_event_payload(project))
        version_no = project.version_no
        session.commit()
    delivery = deliver_event(event_id)
    return {"status": "published", "id": project_id, "version_no": f"v{version_no}", "rag_event": delivery}


@router.post("/{project_id}/archive")
def archive_project(project_id: int, _=Depends(require_permission("project.create"))):
    with get_session() as session:
        project = session.get(Project, project_id)
        if not project: raise HTTPException(404, "项目不存在")
        project.version_no = (project.version_no or 0) + 1
        project.rag_status = "archived"
        event_id = enqueue_and_deliver(session, project_event_payload(project, "archive"))
        version_no = project.version_no
        session.commit()
    delivery = deliver_event(event_id)
    return {"status": "archived", "id": project_id, "version_no": f"v{version_no}", "rag_event": delivery}
