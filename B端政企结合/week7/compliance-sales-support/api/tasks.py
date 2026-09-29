# -*- coding: utf-8 -*-
"""项目任务：把准入缺口转成可跟踪的工作台任务。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_service import require_permission
from db import get_session
from models import EnterpriseProfile, Project, ProjectTask
import matching_service as matching


router = APIRouter(prefix="/api/tasks", tags=["项目任务"])


OWNER_BY_CATEGORY = {
    "资格与准入": "认证与法规负责人",
    "需求与产品匹配": "产品负责人",
    "技术与方案匹配": "技术方案负责人",
    "合规与材料准备度": "合规材料负责人",
    "本地化与交付能力": "欧洲业务负责人",
    "商业吸引力": "商务与财务负责人",
    "时间与执行可行性": "项目经理",
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
    result["project_name"] = project.project_name if project else "项目已删除"
    result["profile_name"] = profile.org_name if profile else "企业档案已删除"
    return result


def _task_for(session, task_id: int, principal) -> ProjectTask:
    task = session.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(404, "项目任务不存在")
    if not principal.is_platform_admin and task.organization_id != principal.organization_id:
        raise HTTPException(403, "无权访问该组织的项目任务")
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
    """把当前未关闭准入缺口转为任务；同组织/项目/档案/缺口只创建一次。"""
    _, principal = identity
    with get_session() as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        profile = session.get(EnterpriseProfile, data.profile_id)
        if not profile:
            raise HTTPException(404, "企业档案不存在")
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
                title=f"关闭{priority}缺口：{row['category']}",
                description=f"项目要求：{row['requirement']}\n当前判断：{row['assessment']}\n行动：{row['action']}",
                priority=priority,
                owner_role=OWNER_BY_CATEGORY.get(row["category"], "项目经理"),
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
            "message": f"已创建 {len(created)} 项任务" + (f"，跳过 {len(skipped)} 项重复任务" if skipped else ""),
        }


@router.patch("/{task_id}")
def update_project_task(task_id: int, data: ProjectTaskUpdate,
                        identity=Depends(require_permission("task.create"))):
    if data.status not in VALID_STATUSES:
        raise HTTPException(422, "不支持的任务状态")
    _, principal = identity
    with get_session() as session:
        task = _task_for(session, task_id, principal)
        task.status = data.status
        task.updated_at = datetime.now(timezone.utc)
        session.flush()
        result = _serialize(session, task)
        session.commit()
        return result
