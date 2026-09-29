# -*- coding: utf-8 -*-
"""Project tasks that turn market-access gaps into trackable workspace items."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_service import require_permission
from db import get_session
from models import EnterpriseProfile, Project, ProjectTask
import matching_service as matching


router = APIRouter(prefix="/api/tasks", tags=["projectTask"])


OWNER_BY_CATEGORY = {
    "Qualification and Market Access": "Certification and Regulation Owner",
    "Product and Project Fit": "Product Owner",
    "Technology and Solution Fit": "Technical Solution Owner",
    "Compliance and Material Readiness": "Compliance Materials Owner",
    "Localization and Delivery Capability": "European Operations Owner",
    "Commercial Attractiveness": "Commercial and Finance Owner",
    "Timing and Execution Feasibility": "Project Manager",
}
DUE_DAYS = {"P0": 3, "P1": 7, "P2": 14, "P3": 21}
VALID_STATUSES = {"pending", "in_progress", "completed"}


class GapTaskCreate(BaseModel):
    profile_id: int = 1
    gap_codes: list[str] = Field(default_factory=list, max_length=7)


class ProjectTaskUpdate(BaseModel):
    status: str


def _serialize(session, task: ProjectTask) -> dict:
    result = task.to_dict()
    project = session.get(Project, task.project_id)
    profile = session.get(EnterpriseProfile, task.profile_id)
    result["project_name"] = project.project_name if project else "Project deleted"
    result["profile_name"] = profile.org_name if profile else "Company profile deleted"
    return result


def _task_for(session, task_id: int, principal) -> ProjectTask:
    task = session.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(404, "Project task not found")
    if not principal.is_platform_admin and task.organization_id != principal.organization_id:
        raise HTTPException(403, "You do not have access to this organization's project task")
    return task


@router.get("")
def list_project_tasks(project_id: int | None = None,
                       identity=Depends(require_permission("project.matching_detail"))):
    _, principal = identity
    with get_session() as session:
        query = session.query(ProjectTask)
        if not principal.is_platform_admin:
            query = query.filter(ProjectTask.organization_id == principal.organization_id)
        if project_id is not None:
            query = query.filter(ProjectTask.project_id == project_id)
        tasks = query.order_by(ProjectTask.status, ProjectTask.priority, ProjectTask.due_date, ProjectTask.id).all()
        return [_serialize(session, task) for task in tasks]


@router.post("/from-gaps/{project_id}", status_code=201)
def create_tasks_from_gaps(project_id: int, data: GapTaskCreate,
                           identity=Depends(require_permission("task.create"))):
    """Convert open market-access gaps into tasks, creating only one per organization, project, profile, and gap."""
    _, principal = identity
    with get_session() as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        profile = session.get(EnterpriseProfile, data.profile_id)
        if not profile:
            raise HTTPException(404, "Company profile not found")
        admission = matching.match_project(profile.to_dict(), project.to_dict())
        unresolved = [row for row in admission["requirement_gap_matrix"] if row["status"] != "satisfied"]
        available_codes = {row["code"] for row in unresolved}
        requested = set(data.gap_codes)
        unknown = requested - available_codes
        if unknown:
            raise HTTPException(422, {"code": "invalid_gap_codes", "gap_codes": sorted(unknown)})
        selected = [row for row in unresolved if not requested or row["code"] in requested]
        now = datetime.now(timezone.utc)
        created, skipped = [], []
        for row in selected:
            existing = session.query(ProjectTask).filter(
                ProjectTask.organization_id == principal.organization_id,
                ProjectTask.project_id == project.id,
                ProjectTask.profile_id == profile.id,
                ProjectTask.gap_code == row["code"],
            ).first()
            if existing:
                skipped.append(existing)
                continue
            priority = row.get("severity") or "P2"
            task = ProjectTask(
                organization_id=principal.organization_id,
                project_id=project.id,
                profile_id=profile.id,
                gap_code=row["code"],
                category=row["category"],
                title=f"Close {priority} Gap: {row['category']}",
                description=f"Project requirement: {row['requirement']}\nCurrent assessment: {row['assessment']}\nAction: {row['action']}",
                priority=priority,
                owner_role=OWNER_BY_CATEGORY.get(row["category"], "Project Manager"),
                status="pending",
                due_date=(now.date() + timedelta(days=DUE_DAYS.get(priority, 14))).isoformat(),
            )
            session.add(task)
            session.flush()
            created.append(task)
        session.commit()
        tasks = created + skipped
        return {
            "project_id": project.id,
            "profile_id": profile.id,
            "created_count": len(created),
            "skipped_count": len(skipped),
            "task_count": len(tasks),
            "tasks": [_serialize(session, task) for task in tasks],
            "message": f"Created {len(created)} tasks" + (f"; skipped {len(skipped)} duplicates" if skipped else ""),
        }


@router.patch("/{task_id}")
def update_project_task(task_id: int, data: ProjectTaskUpdate,
                        identity=Depends(require_permission("task.create"))):
    if data.status not in VALID_STATUSES:
        raise HTTPException(422, "Unsupported task status")
    _, principal = identity
    with get_session() as session:
        task = _task_for(session, task_id, principal)
        task.status = data.status
        task.updated_at = datetime.now(timezone.utc)
        session.flush()
        result = _serialize(session, task)
        session.commit()
        return result
