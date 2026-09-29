# -*- coding: utf-8 -*-
"""Company profile and project matching API."""
from fastapi import APIRouter, HTTPException, Depends
from db import get_session, load_projects
from models import EnterpriseProfile
import matching_service as ms
import partner_service as ps
from case_service import get_admission_demo_case
import json
from auth_service import current_identity, require_permission

router = APIRouter(prefix="/api/matching", tags=["Company Matching"])

JSON_FIELDS = {"target_countries", "target_client_types", "vehicle_types", "powertrain_types",
               "existing_certs", "available_materials", "local_after_sales"}
EDITABLE_FIELDS = {"org_name", "acceptable_scale", "charging_capability", "software_capability",
                   "cert_expiry", "has_eu_entity", "local_partners", "delivery_cycle",
                   "cooperation_mode", "risk_preference"} | JSON_FIELDS
REQUIRED_FIELDS = ("org_name", "target_countries", "target_client_types", "vehicle_types",
                   "powertrain_types", "existing_certs", "has_eu_entity")


@router.get("/demo-case")
def admission_demo_case(_=Depends(require_permission("project.matching_detail"))):
    """Return a one-page business case demo for Week 7."""
    return get_admission_demo_case()


def _completion(data: dict) -> tuple[int, list[str]]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value in (None, "", [], "Unconfirmed"):
            missing.append(field)
    return round((len(REQUIRED_FIELDS) - len(missing)) / len(REQUIRED_FIELDS) * 100), missing


def _profile_response(profile: EnterpriseProfile) -> dict:
    data = profile.to_dict()
    data["completeness"], data["missing_required"] = _completion(data)
    return data


@router.get("/profiles")
def list_profiles(_=Depends(current_identity)):
    with get_session() as s:
        return [_profile_response(p) for p in s.query(EnterpriseProfile).order_by(EnterpriseProfile.id).all()]


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: int, _=Depends(current_identity)):
    with get_session() as s:
        p = s.get(EnterpriseProfile, profile_id)
        if not p: raise HTTPException(404)
        return _profile_response(p)


@router.post("/profiles")
def create_profile(data: dict, _=Depends(require_permission("enterprise_profile.write"))):
    completeness, _missing = _completion(data)
    with get_session() as s:
        p = EnterpriseProfile(
            org_name=data.get("org_name", "Demo Company"),
            target_countries=json.dumps(data.get("target_countries", []), ensure_ascii=False),
            target_client_types=json.dumps(data.get("target_client_types", []), ensure_ascii=False),
            acceptable_scale=data.get("acceptable_scale", ""),
            vehicle_types=json.dumps(data.get("vehicle_types", []), ensure_ascii=False),
            powertrain_types=json.dumps(data.get("powertrain_types", []), ensure_ascii=False),
            charging_capability=data.get("charging_capability", ""),
            existing_certs=json.dumps(data.get("existing_certs", []), ensure_ascii=False),
            available_materials=json.dumps(data.get("available_materials", []), ensure_ascii=False),
            has_eu_entity=data.get("has_eu_entity", "No"),
            local_after_sales=json.dumps(data.get("local_after_sales", []), ensure_ascii=False),
            cooperation_mode=data.get("cooperation_mode", ""),
            delivery_cycle=data.get("delivery_cycle", ""),
            risk_preference=data.get("risk_preference", "Medium"),
            completeness=completeness,
        )
        s.add(p); s.commit(); s.refresh(p)
        return _profile_response(p)


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: int, data: dict, _=Depends(require_permission("enterprise_profile.write"))):
    with get_session() as session:
        profile = session.get(EnterpriseProfile, profile_id)
        if not profile:
            raise HTTPException(404, "Company profile not found")
        for field in EDITABLE_FIELDS:
            if field not in data:
                continue
            value = data[field]
            if field in JSON_FIELDS:
                value = json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)
            setattr(profile, field, value)
        current = profile.to_dict()
        profile.completeness, _missing = _completion(current)
        profile.version = (profile.version or 0) + 1
        s = session
        s.commit(); s.refresh(profile)
        return _profile_response(profile)


@router.get("/match/{project_id}")
def match_project(project_id: int, profile_id: int = 1, _=Depends(require_permission("project.matching_detail"))):
    """Compare a project with a company profile using seven scores, decision gates, and evidence gaps."""
    projs = load_projects()
    proj = next((p for p in projs if p["id"] == project_id), None)
    if not proj: raise HTTPException(404, "Project not found")
    with get_session() as s:
        profile = s.get(EnterpriseProfile, profile_id)
        if not profile: raise HTTPException(404, "Company profile not found. Create a profile first.")
    return ms.match_project(profile.to_dict(), proj)


@router.get("/partner-recommendations/{project_id}")
def partner_recommendations(project_id: int, profile_id: int = 1,
                            _=Depends(require_permission("project.matching_detail"))):
    """Return partner candidates with public evidence and verification limits for project access gaps."""
    projects = load_projects()
    project = next((item for item in projects if item["id"] == project_id), None)
    if not project:
        raise HTTPException(404, "Project not found")
    with get_session() as session:
        profile = session.get(EnterpriseProfile, profile_id)
        if not profile:
            raise HTTPException(404, "Company profile not found. Create a profile first.")
        profile_data = profile.to_dict()
    admission = ms.match_project(profile_data, project)
    return ps.recommend_partners(admission, project)
