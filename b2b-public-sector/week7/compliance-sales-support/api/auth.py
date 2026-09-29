# -*- coding: utf-8 -*-
"""User registration, sign-in, token refresh, sign-out, and current identity."""
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

router = APIRouter(prefix="/api/auth", tags=["User Authentication"])


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
        raise HTTPException(422, "Invalid email address")
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
    """Issue a demo identity with real JWTs and server-side permission checks."""
    modes = {
        "professional": ("professional", "member", False, "Professional Demo"),
        "enterprise": ("enterprise", "member", False, "Enterprise Demo"),
        "admin": ("enterprise", "admin", True, "Administrator Demo"),
    }
    if data.mode not in modes:
        raise HTTPException(422, "Unsupported demo identity")
    plan, role, platform_admin, display_name = modes[data.mode]
    email = f"demo-{data.mode}@local.invalid"
    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, display_name=display_name,
                        password_hash=hash_password(secrets.token_urlsafe(24)),
                        is_platform_admin=platform_admin)
            org = Organization(name=f"{display_name} Organization")
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
            raise HTTPException(409, "This email address is already registered")
        try:
            user = User(email=email, display_name=data.display_name.strip(), password_hash=hash_password(data.password))
            org = Organization(name=data.organization_name.strip() or f"{data.display_name.strip() or email}'s Organization")
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
            session.rollback(); raise HTTPException(409, "This email address is already registered")


@router.post("/login")
def login(data: LoginRequest):
    email = _email(data.email)
    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, "Incorrect email address or password")
        if not user.is_active: raise HTTPException(403, "This user account has been disabled")
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
            raise HTTPException(401, "Refresh token is invalid or expired")
        user = session.get(User, stored.user_id)
        if not user or not user.is_active: raise HTTPException(401, "User account is unavailable")
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
