# -*- coding: utf-8 -*-
"""Project opportunity API for listings, details, and scoring."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db import load_projects, get_session
from models import Project, EntitlementUsage
from auth_service import optional_identity, current_identity, require_permission
from permissions import can
from rag_event_service import deliver_event, enqueue_and_deliver
from api.rag import project_event_payload

router = APIRouter(prefix="/api/projects", tags=["Project Opportunities"])


def _normalize_project_name(name: str) -> str:
    """Normalize whitespace and case for duplicate detection."""
    return " ".join(name.split()).casefold()


def _preview(p: dict, exact: bool) -> dict:
    if exact: return p
    result = dict(p)
    result["project_name"] = f"{p.get('country','Europe')} · {p.get('project_type') or 'Public Procurement'} Project"
    result["contracting_authority"] = "View Contracting Authority after upgrade"
    result["source_url"] = ""
    result["description"] = (p.get("description") or "")[:60]
    value = p.get("contract_value") or 0
    result["contract_value"] = 0
    result["contract_value_range"] = "Not Disclosed" if not value else ("Over €10 million" if value >= 10_000_000 else "€1 million–€10 million" if value >= 1_000_000 else "Under €1 million")
    return result


@router.get("")
def list_projects(identity=Depends(optional_identity)):
    """Return all projects sorted by overall score in descending order."""
    exact = bool(identity and can(identity[1], "project.view_exact"))
    return [_preview(p, exact) for p in load_projects()]


@router.get("/{project_id}")
def project_detail(project_id: int, identity=Depends(optional_identity)):
    with get_session() as s:
        p = s.get(Project, project_id)
        if not p: raise HTTPException(404, f"Project {project_id} not found")
        return _preview(p.to_dict(), bool(identity and can(identity[1], "project.view_exact")))


@router.get("/{project_id}/reveal")
def reveal_project(project_id: int, identity=Depends(current_identity)):
    """Return exact project details to Professional users; free users can unlock up to three per month."""
    user, principal = identity
    with get_session() as s:
        p = s.get(Project, project_id)
        if not p: raise HTTPException(404, "Project not found")
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
        "total": len(projs), "priority": sum(1 for p in projs if p["project_level"] == "Priority Follow-up"),
        "watch": sum(1 for p in projs if p["project_level"] == "Monitoring"),
        "avg_score": round(sum(p["total_score"] for p in projs) / len(projs), 1),
        "countries": [{"name": k, "count": v} for k, v in countries.most_common()],
    }


# Seven scoring dimensions aligned with the project scoring model.
SCORE_DIMS = [
    {"key": "scale_score", "name": "Project Scale", "max": 15, "weight": 15},
    {"key": "authority_score", "name": "Contracting Authority", "max": 10, "weight": 10},
    {"key": "technical_score", "name": "TechnologyMatch", "max": 20, "weight": 25},
    {"key": "compliance_score", "name": "Compliance Feasibility", "max": 15, "weight": 15},
    {"key": "local_score", "name": "Local Partnership Feasibility", "max": 10, "weight": 10},
    {"key": "conversion_score", "name": "Commercial Potential", "max": 20, "weight": 20},
    {"key": "competition_score", "name": "Competitive Landscape", "max": 10, "weight": 5},
]


@router.get("/{project_id}/scoring")
def project_scoring(project_id: int, _=Depends(require_permission("project.scoring_detail"))):
    """Return the seven-dimension score breakdown and veto checks."""
    with get_session() as s:
        p = s.get(Project, project_id)
        if not p: raise HTTPException(404)
    dims = []
    for d in SCORE_DIMS:
        val = getattr(p, d["key"], 0) or 0
        dims.append({"name": d["name"], "score": val, "max": d["max"], "pct": round(val / d["max"] * 100)})
    # Apply disqualifying thresholds.
    veto = []
    if (p.compliance_score or 0) < 4: veto.append(f"Compliance feasibility is below 4 (current: {p.compliance_score})")
    if (p.technical_score or 0) < 5: veto.append(f"Technical match is below 5 (current: {p.technical_score})")
    if (p.competition_score or 0) < 3: veto.append(f"Competitive landscape score is below 3 (current: {p.competition_score})")
    return {
        "project_name": p.project_name, "total_score": p.total_score,
        "project_level": p.project_level, "has_veto": len(veto) > 0, "veto_reasons": veto,
        "dimensions": dims,
    }


# Scoring standards and level descriptions.
SCORE_CRITERIA = {
    "scale_score": {"name": "Project Scale", "max": 15,
        "options": {"15": "Contract value over €10 million", "12": "€5 million–€10 million", "9": "€1 million–€5 million", "6": "€200,000–€1 million", "3": "Under €200,000"}},
    "authority_score": {"name": "Contracting AuthorityType", "max": 10,
        "options": {"10": "European Union or NATO agency", "8": "National ministry", "6": "Regional or provincial authority", "4": "Municipal authority", "2": "Local institution such as a school or hospital"}},
    "technical_score": {"name": "TechnologyMatch", "max": 20,
        "options": {"20": "Proven solution with European references", "16": "Strong match with minor customization", "12": "Partial match requiring major adaptation", "8": "Only some modules match", "4": "Poor technical fit"}},
    "compliance_score": {"name": "Compliance Feasibility", "max": 15,
        "options": {"15": "All certifications are ready for bidding", "12": "One or two certifications can be obtained soon", "9": "Three or more certifications are missing", "6": "A local partner is required", "3": "Restrictions apply to non-EU companies"}},
    "local_score": {"name": "Local Partnership Feasibility", "max": 10,
        "options": {"10": "No local partnership requirement", "8": "Local partnership is recommended", "6": "Subcontracting is required and a partner is available", "4": "Subcontracting is required and a partner must be found", "2": "Local registration or a joint venture is required"}},
    "conversion_score": {"name": "Commercial Potential", "max": 20,
        "options": {"20": "Reference project, repeat business, and ecosystem potential", "16": "Strong reference and replication potential", "12": "Value is mainly limited to this project", "8": "Weak connection to core business", "4": "Little follow-on commercial value"}},
    "competition_score": {"name": "Competitive Landscape", "max": 10,
        "options": {"10": "Three or fewer expected bidders", "8": "Four to six bidders with room to differentiate", "6": "Seven to ten bidders, including market leaders", "4": "More than ten bidders and intense competition", "2": "Market dominated by a small number of companies"}},
}


@router.get("/criteria/options")
def scoring_criteria():
    """Return scoring standards for the frontend form."""
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
    stage: str = "Under Evaluation"
    scale_score: int = 3
    authority_score: int = 3
    technical_score: int = 3
    compliance_score: int = 3
    local_score: int = 3
    conversion_score: int = 3
    competition_score: int = 3


@router.post("")
def create_project(data: ProjectCreate, _=Depends(require_permission("project.create"))):
    """Add a project and calculate its overall score, level, and veto status."""
    if not data.project_name.strip() or not data.country.strip() or not data.contracting_authority.strip():
        raise HTTPException(422, "Project name, country, and contracting authority are required")
    total = data.scale_score + data.authority_score + data.technical_score + data.compliance_score + \
            data.local_score + data.conversion_score + data.competition_score
    # Apply disqualifying thresholds.
    veto = (data.compliance_score < 4) or (data.technical_score < 5) or (data.competition_score < 3)
    if veto: level = "Disqualified"
    elif total >= 70: level = "Priority Follow-up"
    elif total >= 50: level = "Monitoring"
    else: level = "On Hold"
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
                f"A project with this name already exists (ID: {duplicate.id}, name: {duplicate.project_name})",
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
        if not project: raise HTTPException(404, "Project not found")
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
        if not project: raise HTTPException(404, "Project not found")
        project.version_no = (project.version_no or 0) + 1
        project.rag_status = "archived"
        event_id = enqueue_and_deliver(session, project_event_payload(project, "archive"))
        version_no = project.version_no
        session.commit()
    delivery = deliver_event(event_id)
    return {"status": "archived", "id": project_id, "version_no": f"v{version_no}", "rag_event": delivery}
