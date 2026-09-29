# -*- coding: utf-8 -*-
"""商业套餐权益与组织角色权限。后端是最终权限边界。"""
from dataclasses import dataclass

PLAN_ORDER = {"free": 0, "professional": 1, "enterprise": 2, "special_service": 3}
ROLE_ORDER = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}

PERMISSION_MIN_PLAN = {
    "project.view_exact": "professional",
    "project.create": "professional",
    "project.scoring_detail": "professional",
    "project.matching_detail": "professional",
    "sales_pack.download": "professional",
    "material.export": "professional",
    "reports.export": "professional",
    "task.create": "professional",
    "enterprise_profile.write": "free",
    "material.update": "enterprise",
    "partner.contact_request": "enterprise",
    "service_request.create": "special_service",
}

# 商业模式 Excel 的 H/P/R/RW/L/NA 被编码为可执行矩阵。
# P=模糊预览，L=展示升级入口；后端业务权限仍由 require_permission 最终裁决。
ACCESS_MATRIX = {
    "project.exact_info":       {"anonymous": "H",  "free": "P",  "professional": "R",  "enterprise": "R",  "special_service": "R"},
    "project.convert":          {"anonymous": "NA", "free": "L",  "professional": "R",  "enterprise": "R",  "special_service": "R"},
    "workspace.basic":          {"anonymous": "H",  "free": "P",  "professional": "R",  "enterprise": "R",  "special_service": "R"},
    "project.scoring":          {"anonymous": "H",  "free": "L",  "professional": "R",  "enterprise": "RW", "special_service": "RW"},
    "project.matching":         {"anonymous": "H",  "free": "L",  "professional": "R",  "enterprise": "RW", "special_service": "RW"},
    "solution.framework":       {"anonymous": "H",  "free": "L",  "professional": "R",  "enterprise": "RW", "special_service": "RW"},
    "material.details":         {"anonymous": "H",  "free": "L",  "professional": "R",  "enterprise": "RW", "special_service": "RW"},
    "partner.candidates":       {"anonymous": "H",  "free": "L",  "professional": "R",  "enterprise": "R",  "special_service": "RW"},
    "partner.contact":          {"anonymous": "H",  "free": "H",  "professional": "H",  "enterprise": "L",  "special_service": "R"},
    "task.create":              {"anonymous": "NA", "free": "NA", "professional": "R",  "enterprise": "RW", "special_service": "RW"},
    "report.export":            {"anonymous": "NA", "free": "NA", "professional": "R",  "enterprise": "R",  "special_service": "R"},
    "enterprise_profile.edit":  {"anonymous": "NA", "free": "RW", "professional": "RW", "enterprise": "RW", "special_service": "RW"},
    "service.request":          {"anonymous": "NA", "free": "NA", "professional": "L",  "enterprise": "R",  "special_service": "RW"},
    "source.audit":             {"anonymous": "H",  "free": "H",  "professional": "R",  "enterprise": "R",  "special_service": "R"},
}

PLAN_LABELS = {"anonymous": "游客", "free": "免费版", "professional": "专业版",
               "enterprise": "企业版", "special_service": "专项服务"}

PERMISSION_MIN_ROLE = {
    "project.create": "member",
    "enterprise_profile.write": "member",
    "material.update": "member",
    "intelligence.fetch": "admin",
    "regulation.manage": "admin",
}


@dataclass(frozen=True)
class Principal:
    user_id: int
    organization_id: int
    plan: str
    role: str
    is_platform_admin: bool = False


def can(principal: Principal | None, permission: str) -> bool:
    if principal is None:
        return False
    if principal.is_platform_admin:
        return True
    plan = PERMISSION_MIN_PLAN.get(permission)
    role = PERMISSION_MIN_ROLE.get(permission)
    if plan and PLAN_ORDER.get(principal.plan, -1) < PLAN_ORDER[plan]:
        return False
    if role and ROLE_ORDER.get(principal.role, -1) < ROLE_ORDER[role]:
        return False
    return permission in PERMISSION_MIN_PLAN or permission in PERMISSION_MIN_ROLE


def permission_list(principal: Principal) -> list[str]:
    all_permissions = set(PERMISSION_MIN_PLAN) | set(PERMISSION_MIN_ROLE)
    return sorted(p for p in all_permissions if can(principal, p))


def access_summary(principal: Principal | None) -> dict:
    plan = principal.plan if principal else "anonymous"
    capabilities = {}
    for name, states in ACCESS_MATRIX.items():
        state = "RW" if principal and principal.is_platform_admin else states[plan]
        required_plan = None
        if state in {"H", "P", "L", "NA"}:
            required_plan = next((candidate for candidate in ("professional", "enterprise", "special_service")
                                  if states[candidate] in {"R", "RW"}), None)
        capabilities[name] = {
            "state": state,
            "required_plan": required_plan,
            "required_plan_label": PLAN_LABELS.get(required_plan, ""),
        }
    return {"plan": plan, "plan_label": PLAN_LABELS.get(plan, plan),
            "role": principal.role if principal else "anonymous", "capabilities": capabilities}
