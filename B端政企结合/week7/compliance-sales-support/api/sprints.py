# -*- coding: utf-8 -*-
"""14天项目冲刺：申请、审核启动与任务推进。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_service import current_identity
from db import get_session
from models import Project, SprintApplication, SprintTask

router = APIRouter(prefix="/api/sprints", tags=["14天项目冲刺"])


class SprintApplicationCreate(BaseModel):
    project_id: int
    company_name: str = Field(min_length=2, max_length=200)
    company_type: str = Field(default="整车企业", max_length=100)
    target_region: str = Field(default="欧洲", max_length=100)
    project_stage: str = Field(default="机会评估", max_length=100)
    support_needs: list[str] = Field(default_factory=list, max_length=8)
    current_challenge: str = Field(default="", max_length=2000)
    expected_result: str = Field(default="", max_length=2000)
    materials_ready: list[str] = Field(default_factory=list, max_length=4)
    target_deadline: str = Field(default="", max_length=30)
    resource_commitment: str = Field(default="", max_length=500)
    scope_confirmed: bool = False
    cooperation_confirmed: bool = False
    contact_name: str = Field(min_length=1, max_length=100)
    contact_info: str = Field(min_length=3, max_length=200)


class SprintTaskUpdate(BaseModel):
    status: str


TASK_TEMPLATES = (
    ("诊断与定标", "完成项目资格与目标诊断", "项目顾问", "high", 2),
    ("方案与匹配", "输出法规与技术差距清单", "合规顾问", "high", 5),
    ("方案与匹配", "完成本地伙伴初筛", "行业顾问", "normal", 7),
    ("材料与行动", "形成投标材料行动包", "交付经理", "high", 11),
    ("评审与交付", "完成联合评审与下一步计划", "项目顾问", "normal", 14),
)


def _application_for(session, application_id: int, principal) -> SprintApplication:
    application = session.get(SprintApplication, application_id)
    if not application:
        raise HTTPException(404, "冲刺申请不存在")
    if not principal.is_platform_admin and application.organization_id != principal.organization_id:
        raise HTTPException(403, "无权访问该组织的冲刺申请")
    return application


def _serialize(session, application: SprintApplication, include_tasks: bool = True) -> dict:
    data = application.to_dict()
    project = session.get(Project, application.project_id)
    data["project"] = {
        "id": project.id,
        "project_name": project.project_name,
        "country": project.country,
        "project_type": project.project_type,
    } if project else None
    data["tasks"] = [task.to_dict() for task in session.query(SprintTask).filter(
        SprintTask.application_id == application.id
    ).order_by(SprintTask.sort_order, SprintTask.id).all()] if include_tasks else []
    return data


@router.post("", status_code=201)
def create_application(data: SprintApplicationCreate, identity=Depends(current_identity)):
    user, principal = identity
    if not data.scope_confirmed or not data.cooperation_confirmed:
        raise HTTPException(422, {"code": "service_terms_not_confirmed",
                                  "message": "请确认单项目范围和客户配合规则"})
    with get_session() as session:
        project = session.get(Project, data.project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        duplicate = session.query(SprintApplication).filter(
            SprintApplication.organization_id == principal.organization_id,
            SprintApplication.project_id == data.project_id,
            SprintApplication.status.in_(["submitted", "active"]),
        ).first()
        if duplicate:
            raise HTTPException(409, {"code": "sprint_already_exists", "application_id": duplicate.id})
        now = datetime.now(timezone.utc)
        application = SprintApplication(
            application_no=f"SPR-{now:%Y%m%d}-{principal.organization_id:04d}-{uuid.uuid4().hex[:6].upper()}",
            organization_id=principal.organization_id,
            user_id=user.id,
            project_id=data.project_id,
            company_name=data.company_name.strip(),
            company_type=data.company_type.strip(),
            target_region=data.target_region.strip(),
            project_stage=data.project_stage.strip(),
            support_needs=json.dumps([item.strip() for item in data.support_needs if item.strip()], ensure_ascii=False),
            current_challenge=data.current_challenge.strip(),
            expected_result=data.expected_result.strip(),
            materials_ready=json.dumps([item.strip() for item in data.materials_ready if item.strip()], ensure_ascii=False),
            target_deadline=data.target_deadline.strip(),
            resource_commitment=data.resource_commitment.strip(),
            scope_confirmed=data.scope_confirmed,
            cooperation_confirmed=data.cooperation_confirmed,
            contact_name=data.contact_name.strip(),
            contact_info=data.contact_info.strip(),
        )
        session.add(application)
        session.flush()
        result = _serialize(session, application)
        session.commit()
        return result


@router.get("")
def list_applications(identity=Depends(current_identity)):
    _, principal = identity
    with get_session() as session:
        query = session.query(SprintApplication)
        if not principal.is_platform_admin:
            query = query.filter(SprintApplication.organization_id == principal.organization_id)
        rows = query.order_by(SprintApplication.created_at.desc(), SprintApplication.id.desc()).all()
        return [_serialize(session, row) for row in rows]


@router.get("/{application_id}")
def get_application(application_id: int, identity=Depends(current_identity)):
    _, principal = identity
    with get_session() as session:
        return _serialize(session, _application_for(session, application_id, principal))


@router.post("/{application_id}/start")
def start_application(application_id: int, identity=Depends(current_identity)):
    _, principal = identity
    if not principal.is_platform_admin:
        raise HTTPException(403, "仅平台管理员可审核并启动冲刺")
    with get_session() as session:
        application = _application_for(session, application_id, principal)
        if application.status != "submitted":
            raise HTTPException(409, "只有待审核申请可以启动")
        now = datetime.now(timezone.utc)
        application.status = "active"
        application.reviewed_at = now
        application.started_at = now
        application.current_day = 1
        for order, (phase, title, owner, priority, due_day) in enumerate(TASK_TEMPLATES, 1):
            session.add(SprintTask(
                application_id=application.id, phase=phase, title=title, owner=owner,
                priority=priority, due_day=due_day, sort_order=order,
                status="in_progress" if order == 1 else "pending",
            ))
        session.flush()
        result = _serialize(session, application)
        session.commit()
        return result


@router.patch("/{application_id}/tasks/{task_id}")
def update_task(application_id: int, task_id: int, data: SprintTaskUpdate,
                identity=Depends(current_identity)):
    _, principal = identity
    if data.status not in {"pending", "in_progress", "completed"}:
        raise HTTPException(422, "不支持的任务状态")
    with get_session() as session:
        application = _application_for(session, application_id, principal)
        if application.status != "active":
            raise HTTPException(409, "冲刺尚未启动")
        task = session.get(SprintTask, task_id)
        if not task or task.application_id != application.id:
            raise HTTPException(404, "冲刺任务不存在")
        task.status = data.status
        task.updated_at = datetime.now(timezone.utc)
        session.flush()
        tasks = session.query(SprintTask).filter(SprintTask.application_id == application.id).all()
        completed = sum(item.status == "completed" for item in tasks)
        application.progress = round(completed / max(1, len(tasks)) * 100)
        if completed == len(tasks):
            application.status = "completed"
            application.current_day = 14
        else:
            active_due_days = [item.due_day for item in tasks if item.status != "completed"]
            application.current_day = min(active_due_days or [14])
        session.flush()
        result = _serialize(session, application)
        session.commit()
        return result
