# -*- coding: utf-8 -*-
"""Password hashing, JWTs, refresh tokens, and current-user resolution."""
import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import get_session
from models import User, OrganizationMember, Subscription, RefreshToken
from permissions import Principal, can

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
REFRESH_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt64, digest64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        salt = base64.urlsafe_b64decode(salt64.encode())
        expected = base64.urlsafe_b64decode(digest64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User, principal: Principal) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id), "org": principal.organization_id, "ver": user.token_version,
        "iat": now, "exp": now + timedelta(minutes=ACCESS_MINUTES), "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def issue_refresh_token(session, user_id: int) -> str:
    raw = secrets.token_urlsafe(48)
    session.add(RefreshToken(
        user_id=user_id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS),
    ))
    return raw


def _principal_for(session, user: User, organization_id: int | None = None) -> Principal:
    q = session.query(OrganizationMember).filter(OrganizationMember.user_id == user.id)
    if organization_id is not None:
        q = q.filter(OrganizationMember.organization_id == organization_id)
    member = q.order_by(OrganizationMember.id).first()
    if not member:
        raise HTTPException(403, "User does not belong to an organization")
    subscription = session.query(Subscription).filter(
        Subscription.organization_id == member.organization_id,
        Subscription.status == "active",
    ).first()
    return Principal(user.id, member.organization_id, subscription.plan if subscription else "free",
                     member.role, bool(user.is_platform_admin))


def current_identity(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if not credentials:
        raise HTTPException(401, "Please first Sign In", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access": raise jwt.InvalidTokenError()
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Sign-in credentials are invalid or expired", headers={"WWW-Authenticate": "Bearer"})
    with get_session() as session:
        user = session.get(User, user_id)
        if not user or not user.is_active or user.token_version != payload.get("ver"):
            raise HTTPException(401, "User account is disabled or sign-in has been revoked")
        principal = _principal_for(session, user, payload.get("org"))
        return user, principal


def optional_identity(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if not credentials:
        return None
    return current_identity(credentials)


def require_permission(permission: str):
    def dependency(identity=Depends(current_identity)):
        user, principal = identity
        if not can(principal, permission):
            raise HTTPException(403, {"code": "permission_denied", "permission": permission,
                                      "plan": principal.plan, "role": principal.role})
        return identity
    return dependency


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def utc_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
