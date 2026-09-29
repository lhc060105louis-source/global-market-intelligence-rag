# -*- coding: utf-8 -*-
"""SQLAlchemy ORM models for regulations, materials, projects, and related data.

These models replace raw sqlite3 access and share the data layer with the creator
intelligence application.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for RSS and audit records."""
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
    status = Column(String, default="Unconfirmed")
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
    project_level = Column(String, default="On Hold")
    owner = Column(String)
    stage = Column(String, default="Under Evaluation")
    created_at = Column(String)
    rag_status = Column(String(20), nullable=False, default="draft")
    version_no = Column(Integer, nullable=False, default=1)
    published_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class IntelligenceItem(Base):
    """RSS intelligence item matching the intelligence_items table in rss_fetcher.py."""
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
    """Organization-level intelligence monitors; alert frequency is a schedule, not a sent notification."""
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
    """Company capability profile aligned with the project matching design (six field groups)."""
    __tablename__ = "enterprise_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String(200), default="Demo Company")
    # 1. Company profile and preferences
    target_countries = Column(Text, default="")          # JSON array: ["DE","FR","UK"]
    target_client_types = Column(Text, default="")       # JSON array
    acceptable_scale = Column(String(100), default="")   # For example, €1 million–€50 million
    # 2. Products and technology
    vehicle_types = Column(Text, default="")             # JSON: ["Electric bus", "Electric truck", "Passenger car"]
    powertrain_types = Column(Text, default="")          # JSON: ["Battery electric", "Plug-in hybrid"]
    charging_capability = Column(Text, default="")       # 800V fast charging / battery passport data
    software_capability = Column(Text, default="")       # OTA / connected vehicles / driver assistance
    # ③ Certification and Materials
    existing_certs = Column(Text, default="")            # JSON: ["WVTA","CSMS","Euro NCAP"]
    cert_expiry = Column(String, default="")
    available_materials = Column(Text, default="")       # JSON: ["Battery passport", "Carbon footprint report"]
    # 4. Local capabilities
    has_eu_entity = Column(String, default="")           # "Yes" / "No"
    local_after_sales = Column(Text, default="")         # JSON: ["Germany","United Kingdom"]
    local_partners = Column(Text, default="")
    # 5. Commercial constraints
    delivery_cycle = Column(String, default="")
    cooperation_mode = Column(String, default="")        # Vehicle exports / technology licensing / joint tenders / local manufacturing
    risk_preference = Column(String, default="Moderate")  # Conservative / Moderate / Aggressive
    # 6. Governance fields
    completeness = Column(Integer, default=0)            # Profile completeness, 0–100
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
    """Organization-level project task created by an eligibility gap or a user action."""
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
    owner_role = Column(String(100), nullable=False, default="Project Manager")
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
    """Fetch log recording each RSS fetch operation, rather than an item's ingestion time."""
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
    """Application for a 14-day project sprint, an optional service outside subscription plans."""
    __tablename__ = "sprint_applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_no = Column(String(40), nullable=False, unique=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    company_name = Column(String(200), nullable=False)
    company_type = Column(String(100), nullable=False, default="Vehicle Manufacturer")
    target_region = Column(String(100), nullable=False, default="Europe")
    project_stage = Column(String(100), nullable=False, default="Opportunity Assessment")
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
    """Phase tasks generated when a sprint starts."""
    __tablename__ = "sprint_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("sprint_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    phase = Column(String(80), nullable=False)
    title = Column(String(200), nullable=False)
    owner = Column(String(100), nullable=False, default="Project Consultant")
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
    """RAG Hub event recorded in the business transaction before delivery."""
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
