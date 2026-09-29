# -*- coding: utf-8 -*-
"""用户注册、登录、令牌刷新、退出和当前身份。"""
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from auth_service import (create_access_token, current_identity, hash_password, issue_refresh_token,
                          token_hash, utc_aware, verify_password, _principal_for, optional_identity)
from db import get_session
from models import User, Organization, OrganizationMember, Subscription, RefreshToken
from permissions import permission_list, access_summary

router = APIRouter(prefix="/api/auth", tags=["用户权限"])


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    organization_name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class DemoModeRequest(BaseModel):
    mode: str


def _email(value: str) -> str:
    value = value.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise HTTPException(422, "邮箱格式不正确")
    return value


def _response(user, principal, access_token, refresh_token=None):
    data = {
        "access_token": access_token, "token_type": "bearer", "expires_in": 30 * 60,
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name},
        "organization_id": principal.organization_id, "role": principal.role, "plan": principal.plan,
        "permissions": permission_list(principal), "access": access_summary(principal),
    }
    if refresh_token: data["refresh_token"] = refresh_token
    return data


@router.post("/demo-mode")
def demo_mode(data: DemoModeRequest):
    """演示环境快捷身份：保留真实 JWT 与后端权限校验，不需要密码。"""
    modes = {
        "professional": ("professional", "member", False, "专业版演示"),
        "enterprise": ("enterprise", "member", False, "企业版演示"),
        "admin": ("enterprise", "admin", True, "管理员演示"),
    }
    if data.mode not in modes:
        raise HTTPException(422, "不支持的演示身份")
    plan, role, platform_admin, display_name = modes[data.mode]
    email = f"demo-{data.mode}@local.invalid"
    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, display_name=display_name,
                        password_hash=hash_password(secrets.token_urlsafe(24)),
                        is_platform_admin=platform_admin)
            org = Organization(name=f"{display_name}组织")
            session.add_all([user, org]); session.flush()
            session.add_all([
                OrganizationMember(organization_id=org.id, user_id=user.id, role=role),
                Subscription(organization_id=org.id, plan=plan, status="active"),
            ])
        else:
            user.display_name = display_name
            user.is_platform_admin = platform_admin
            member = session.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).first()
            member.role = role
            subscription = session.query(Subscription).filter(
                Subscription.organization_id == member.organization_id,
                Subscription.status == "active",
            ).first()
            subscription.plan = plan
        session.flush()
        principal = _principal_for(session, user)
        access = create_access_token(user, principal)
        session.commit()
        return _response(user, principal, access)


@router.post("/register", status_code=201)
def register(data: RegisterRequest):
    email = _email(data.email)
    with get_session() as session:
        if session.query(User).filter(User.email == email).first():
            raise HTTPException(409, "该邮箱已注册")
        try:
            user = User(email=email, display_name=data.display_name.strip(), password_hash=hash_password(data.password))
            org = Organization(name=data.organization_name.strip() or f"{data.display_name.strip() or email}的组织")
            session.add_all([user, org]); session.flush()
            session.add_all([
                OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"),
                Subscription(organization_id=org.id, plan="free", status="active"),
            ])
            session.flush()
            principal = _principal_for(session, user, org.id)
            refresh = issue_refresh_token(session, user.id)
            access = create_access_token(user, principal)
            session.commit()
            return _response(user, principal, access, refresh)
        except IntegrityError:
            session.rollback(); raise HTTPException(409, "该邮箱已注册")


@router.post("/login")
def login(data: LoginRequest):
    email = _email(data.email)
    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, "邮箱或密码错误")
        if not user.is_active: raise HTTPException(403, "用户已被禁用")
        principal = _principal_for(session, user)
        refresh = issue_refresh_token(session, user.id)
        access = create_access_token(user, principal)
        session.commit()
        return _response(user, principal, access, refresh)


@router.post("/refresh")
def refresh(data: RefreshRequest):
    with get_session() as session:
        stored = session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash(data.refresh_token)).first()
        now = datetime.now(timezone.utc)
        if not stored or stored.revoked_at or utc_aware(stored.expires_at) <= now:
            raise HTTPException(401, "刷新凭证无效或已过期")
        user = session.get(User, stored.user_id)
        if not user or not user.is_active: raise HTTPException(401, "用户不可用")
        stored.revoked_at = now
        principal = _principal_for(session, user)
        new_refresh = issue_refresh_token(session, user.id)
        access = create_access_token(user, principal)
        session.commit()
        return _response(user, principal, access, new_refresh)


@router.post("/logout", status_code=204)
def logout(data: RefreshRequest):
    with get_session() as session:
        stored = session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash(data.refresh_token)).first()
        if stored and not stored.revoked_at:
            stored.revoked_at = datetime.now(timezone.utc); session.commit()


@router.get("/me")
def me(identity=Depends(current_identity)):
    user, principal = identity
    return _response(user, principal, "")


@router.get("/access")
def access(identity=Depends(optional_identity)):
    return access_summary(identity[1] if identity else None)
