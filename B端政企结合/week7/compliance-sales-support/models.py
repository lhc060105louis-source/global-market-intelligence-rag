# -*- coding: utf-8 -*-
"""SQLAlchemy ORM 模型 —— 映射现有三张表(regulations / material_status / projects)。
替换 raw sqlite3,与 KOL 端统一数据层。"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    """统一生成带时区的 UTC 时间，供 RSS 与审计模型复用。"""
    return datetime.now(timezone.utc)


class Regulation(Base):
    __tablename__ = "regulations"

    regulation_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    official_number = Column(String)
    issuer = Column(String)
    type = Column(String)
    scope = Column(String)
    applicable_product = Column(Text)   # JSON array stored as text
    effective_date = Column(String)
    impact_level = Column(String)
    core_requirement = Column(Text)
    official_source = Column(String)
    last_verified_at = Column(String)
    status = Column(String)
    version = Column(String)
    rag_version = Column(Integer, nullable=False, default=1)
    rag_status = Column(String(20), nullable=False, default="draft")
    published_at = Column(DateTime(timezone=True), nullable=True)
    provide = Column(Text)              # JSON list of [name, priority] pairs
    local_duty = Column(Text)
    gap = Column(Text)
    scenarios = Column(Text)            # JSON array

    def to_dict(self) -> dict:
        import json
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        d["applicable_product"] = json.loads(d["applicable_product"] or "[]")
        d["provide"] = [tuple(x) for x in json.loads(d["provide"] or "[]")]
        d["scenarios"] = json.loads(d["scenarios"] or "[]")
        return d


class MaterialStatus(Base):
    __tablename__ = "material_status"

    mkey = Column(String, primary_key=True)
    regulation_id = Column(String)
    material_name = Column(String)
    priority = Column(String)
    status = Column(String, default="待确认")
    owner = Column(String)
    due_date = Column(String)
    note = Column(String)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String, nullable=False)
    country = Column(String, nullable=False)
    project_type = Column(String)
    contracting_authority = Column(String, nullable=False)
    contract_value = Column(Float, default=0)
    deadline = Column(String)
    source_url = Column(String)
    description = Column(Text)
    scale_score = Column(Integer, default=3)
    authority_score = Column(Integer, default=3)
    technical_score = Column(Integer, default=3)
    compliance_score = Column(Integer, default=3)
    local_score = Column(Integer, default=3)
    conversion_score = Column(Integer, default=3)
    competition_score = Column(Integer, default=3)
    total_score = Column(Integer, default=0)
    project_level = Column(String, default="暂缓投入")
    owner = Column(String)
    stage = Column(String, default="评估中")
    created_at = Column(String)
    rag_status = Column(String(20), nullable=False, default="draft")
    version_no = Column(Integer, nullable=False, default=1)
    published_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class IntelligenceItem(Base):
    """RSS 情报条目(对齐 rss_fetcher.py 的 intelligence_items 表)。"""
    __tablename__ = "intelligence_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False, index=True)
    title = Column(String(1000), nullable=False)
    link = Column(String(2000), nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=False, default="")
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    review_status = Column(String(20), nullable=False, default="draft", index=True)
    version_no = Column(Integer, nullable=False, default=1)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    published_at_rag = Column(DateTime(timezone=True), nullable=True)
    review_region = Column(String(50), nullable=False, default="")

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SavedIntelligenceSearch(Base):
    """组织级情报监控条件；提醒频率仅表示计划，不伪装成已发送通知。"""
    __tablename__ = "saved_intelligence_searches"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_saved_search_org_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    keyword = Column(String(200), nullable=False, default="")
    country = Column(String(80), nullable=False, default="")
    source = Column(String(100), nullable=False, default="")
    frequency = Column(String(20), nullable=False, default="daily")
    enabled = Column(Boolean, nullable=False, default=True)
    last_notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for key in ("last_notified_at", "created_at", "updated_at"):
            if data[key]:
                data[key] = data[key].isoformat()
        return data


class EnterpriseProfile(Base):
    """企业能力档案(对齐 Week6 企业档案与项目匹配设计 §1,6组字段)。"""
    __tablename__ = "enterprise_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String(200), default="演示企业")
    # ① 基础与偏好
    target_countries = Column(Text, default="")          # JSON array: ["DE","FR","UK"]
    target_client_types = Column(Text, default="")       # JSON array
    acceptable_scale = Column(String(100), default="")   # 如 "100万-5000万€"
    # ② 产品与技术
    vehicle_types = Column(Text, default="")             # JSON: ["电动客车","电动货车","乘用车"]
    powertrain_types = Column(Text, default="")          # JSON: ["纯电","插混"]
    charging_capability = Column(Text, default="")       # 800V快充/电池护照数据
    software_capability = Column(Text, default="")       # OTA/车联网/智驾
    # ③ 认证与材料
    existing_certs = Column(Text, default="")            # JSON: ["WVTA","CSMS","Euro NCAP"]
    cert_expiry = Column(String, default="")
    available_materials = Column(Text, default="")       # JSON: ["电池护照","碳足迹报告"]
    # ④ 本地化能力
    has_eu_entity = Column(String, default="")           # "是" / "否"
    local_after_sales = Column(Text, default="")         # JSON: ["德国","英国"]
    local_partners = Column(Text, default="")
    # ⑤ 商业约束
    delivery_cycle = Column(String, default="")
    cooperation_mode = Column(String, default="")        # 整车出口/技术授权/联合投标/本地制造
    risk_preference = Column(String, default="中性")     # 保守/中性/进取
    # ⑥ 治理字段
    completeness = Column(Integer, default=0)            # 完整度 0-100
    version = Column(Integer, default=1)
    confirmed_by = Column(String, default="")
    confirmed_at = Column(String, default="")

    def to_dict(self) -> dict:
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        import json
        for k in ['target_countries','target_client_types','vehicle_types','powertrain_types',
                  'existing_certs','available_materials','local_after_sales']:
            try: d[k] = json.loads(d[k])
            except: d[k] = []
        return d


class ProjectTask(Base):
    """由准入缺口或人工操作生成的组织级项目任务。"""
    __tablename__ = "project_tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "profile_id", "gap_code",
                         name="uq_project_task_gap"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("enterprise_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(40), nullable=False, default="admission_gap")
    gap_code = Column(String(40), nullable=False)
    category = Column(String(100), nullable=False)
    title = Column(String(240), nullable=False)
    description = Column(Text, nullable=False, default="")
    priority = Column(String(10), nullable=False, default="P2", index=True)
    owner_role = Column(String(100), nullable=False, default="项目经理")
    status = Column(String(30), nullable=False, default="pending", index=True)
    due_date = Column(String(20), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for key in ("created_at", "updated_at"):
            if data[key]:
                data[key] = data[key].isoformat()
        return data


class FetchLog(Base):
    """抓取日志——记录每次 RSS 抓取动作(非单条数据入库时间)。"""
    __tablename__ = "fetch_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime(timezone=True), nullable=False)
    sources = Column(String(200), nullable=False, default="")
    new_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    status = Column(String(20), default="ok")

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    display_name = Column(String(100), nullable=False, default="")
    password_hash = Column(String(500), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_platform_admin = Column(Boolean, nullable=False, default=False)
    token_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    plan = Column(String(30), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")
    starts_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    ends_at = Column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class EntitlementUsage(Base):
    __tablename__ = "entitlement_usage"
    __table_args__ = (UniqueConstraint("user_id", "entitlement", "period", "resource_key", name="uq_entitlement_usage"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entitlement = Column(String(100), nullable=False)
    period = Column(String(7), nullable=False)
    resource_key = Column(String(200), nullable=False, default="")
    used_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class SprintApplication(Base):
    """14天项目冲刺申请；订阅套餐之外的独立专项服务。"""
    __tablename__ = "sprint_applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_no = Column(String(40), nullable=False, unique=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    company_name = Column(String(200), nullable=False)
    company_type = Column(String(100), nullable=False, default="整车企业")
    target_region = Column(String(100), nullable=False, default="欧洲")
    project_stage = Column(String(100), nullable=False, default="机会评估")
    support_needs = Column(Text, nullable=False, default="[]")
    current_challenge = Column(Text, nullable=False, default="")
    expected_result = Column(Text, nullable=False, default="")
    materials_ready = Column(Text, nullable=False, default="[]")
    target_deadline = Column(String(30), nullable=False, default="")
    resource_commitment = Column(String(500), nullable=False, default="")
    scope_confirmed = Column(Boolean, nullable=False, default=False)
    cooperation_confirmed = Column(Boolean, nullable=False, default=False)
    contact_name = Column(String(100), nullable=False)
    contact_info = Column(String(200), nullable=False)
    status = Column(String(30), nullable=False, default="submitted", index=True)
    current_day = Column(Integer, nullable=False, default=0)
    progress = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        import json
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for key in ("support_needs", "materials_ready"):
            try:
                data[key] = json.loads(data[key] or "[]")
            except (TypeError, json.JSONDecodeError):
                data[key] = []
        for key in ("created_at", "reviewed_at", "started_at"):
            if data[key]:
                data[key] = data[key].isoformat()
        return data


class SprintTask(Base):
    """冲刺启动后生成的阶段任务。"""
    __tablename__ = "sprint_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("sprint_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    phase = Column(String(80), nullable=False)
    title = Column(String(200), nullable=False)
    owner = Column(String(100), nullable=False, default="项目顾问")
    priority = Column(String(20), nullable=False, default="normal")
    status = Column(String(30), nullable=False, default="pending", index=True)
    due_day = Column(Integer, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if data["updated_at"]:
            data["updated_at"] = data["updated_at"].isoformat()
        return data


class RagEventOutbox(Base):
    """业务事务内落库的 RAG Hub 待投递事件。"""
    __tablename__ = "rag_event_outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(100), nullable=False, unique=True, index=True)
    upstream_id = Column(String(200), nullable=False, index=True)
    upstream_version = Column(String(50), nullable=False)
    event_type = Column(String(20), nullable=False)
    payload = Column(Text, nullable=False)
    delivery_status = Column(String(20), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=False, default="")
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
