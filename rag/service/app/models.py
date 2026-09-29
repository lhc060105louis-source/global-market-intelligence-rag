from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def uuid_string() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Persist UTC in SQLite and always return timezone-aware UTC values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware value")
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class KnowledgeRecord(Base):
    __tablename__ = "knowledge_records"
    __table_args__ = (
        UniqueConstraint("source_system", "record_type", "business_key", "record_mode", name="uq_knowledge_business"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    source_system: Mapped[str] = mapped_column(String(8), index=True)
    source_record_id: Mapped[str] = mapped_column(String(255), index=True)
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    record_mode: Mapped[str] = mapped_column(String(16), index=True)
    business_key: Mapped[str] = mapped_column(String(768))
    source_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime())
    source_updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    retrieval_text: Mapped[str] = mapped_column(Text, default="")
    target_knowledge_base: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    sync_tasks: Mapped[list["RagSyncTask"]] = relationship(back_populates="record")


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    push_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str] = mapped_column(String(8))
    source_record_id: Mapped[str] = mapped_column(String(255))
    source_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(40))
    record_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_records.id"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    ingestion_kind: Mapped[str] = mapped_column(String(32), default="knowledge_record")
    target_object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_object_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    last_conflict_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RagDocumentMapping(Base):
    __tablename__ = "rag_document_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"), unique=True)
    target_knowledge_base: Mapped[str] = mapped_column(String(32))
    external_knowledge_base_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapped_source_version: Mapped[int] = mapped_column(Integer)
    external_is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class RagSyncTask(Base):
    __tablename__ = "rag_sync_tasks"
    __table_args__ = (
        UniqueConstraint("record_id", "source_version", "operation", name="uq_sync_record_version_operation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"), index=True)
    source_version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    external_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    record: Mapped[KnowledgeRecord] = relationship(back_populates="sync_tasks")


class RiskObject(Base):
    __tablename__ = "risk_objects"
    __table_args__ = (
        UniqueConstraint("vehicle_model", "part", "region", "risk_type", name="uq_risk_business"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    vehicle_model: Mapped[str] = mapped_column(String(255))
    part: Mapped[str] = mapped_column(String(255))
    region: Mapped[str] = mapped_column(String(255))
    risk_type: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    episodes: Mapped[list["RiskEpisode"]] = relationship(back_populates="risk_object")


class RiskEpisode(Base):
    __tablename__ = "risk_episodes"
    __table_args__ = (
        Index("uq_one_open_episode", "risk_object_id", unique=True, sqlite_where=text("status = 'open'")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    risk_object_id: Mapped[str] = mapped_column(ForeignKey("risk_objects.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    current_value: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    risk_object: Mapped[RiskObject] = relationship(back_populates="episodes")
    trend_points: Mapped[list["RiskTrendPoint"]] = relationship(back_populates="episode")


class RiskTrendPoint(Base):
    __tablename__ = "risk_trend_points"
    __table_args__ = (
        UniqueConstraint("episode_id", "business_time", "source_version", name="uq_risk_trend_point"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    episode_id: Mapped[str] = mapped_column(ForeignKey("risk_episodes.id"), index=True)
    business_time: Mapped[datetime] = mapped_column(UTCDateTime())
    hit_value: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"))
    source_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    episode: Mapped[RiskEpisode] = relationship(back_populates="trend_points")


class RecordAnnotation(Base):
    __tablename__ = "record_annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"), index=True)
    annotation_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class MaintenanceOperation(Base):
    __tablename__ = "maintenance_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    operation: Mapped[str] = mapped_column(String(32))
    operator: Mapped[str] = mapped_column(String(255))
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class DomainEvent(Base):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("source_domain", "source_knowledge_record_id", "event_type", name="uq_domain_event_identity"),
        Index("ix_domain_events_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    source_domain: Mapped[str] = mapped_column(String(8), index=True)
    source_record_id: Mapped[str] = mapped_column(String(255), index=True)
    source_knowledge_record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), default="real")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    current_event_version: Mapped[int] = mapped_column(Integer, default=1)
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    revisions: Mapped[list["DomainEventRevision"]] = relationship(back_populates="domain_event")


class DomainEventRevision(Base):
    __tablename__ = "domain_event_revisions"
    __table_args__ = (
        UniqueConstraint("domain_event_id", "event_version", name="uq_domain_event_revision_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    domain_event_id: Mapped[str] = mapped_column(ForeignKey("domain_events.id"), index=True)
    event_version: Mapped[int] = mapped_column(Integer)
    event_action: Mapped[str] = mapped_column(String(16))
    execution_mode: Mapped[str] = mapped_column(String(32), default="real")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    source_record_version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    professional_status: Mapped[str] = mapped_column(String(32))
    related_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    payload_hash: Mapped[str] = mapped_column(String(64))
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    domain_event: Mapped[DomainEvent] = relationship(back_populates="revisions")


class AssociationCandidate(Base):
    __tablename__ = "association_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_key", "rule_version", name="uq_association_candidate_rule"),
        Index("ix_association_candidates_status_expires", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    candidate_key: Mapped[str] = mapped_column(String(1024))
    source_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    correlation_basis: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence_score: Mapped[float] = mapped_column()
    confidence_explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
    generated_by: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(64))
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)


class CoordinationCase(Base):
    __tablename__ = "coordination_cases"
    __table_args__ = (
        Index("ix_coordination_cases_status_scenario_updated", "status", "scenario_type", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    scenario_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="triaging", index=True)
    trigger_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    association_candidate_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    correlation_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    execution_mode: Mapped[str] = mapped_column(String(32), default="real")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reopened_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class CaseDomainImpact(Base):
    __tablename__ = "case_domain_impacts"
    __table_args__ = (
        UniqueConstraint("case_id", "domain", "assessment_sequence", name="uq_case_domain_impact_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    case_id: Mapped[str] = mapped_column(ForeignKey("coordination_cases.id"), index=True)
    domain: Mapped[str] = mapped_column(String(8))
    assessment_sequence: Mapped[int] = mapped_column(Integer)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    assessment_status: Mapped[str] = mapped_column(String(32), default="waiting")
    impact_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_analysis_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    assessed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class CoordinationTask(Base):
    __tablename__ = "coordination_tasks"
    __table_args__ = (
        Index("ix_coordination_tasks_case_status_due", "case_id", "status", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    case_id: Mapped[str] = mapped_column(ForeignKey("coordination_cases.id"), index=True)
    owner_domain: Mapped[str] = mapped_column(String(8))
    task_type: Mapped[str] = mapped_column(String(64))
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    input_evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    expected_output_type: Mapped[str] = mapped_column(String(64))
    verification_rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_mode: Mapped[str] = mapped_column(String(32), default="real")
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class ExecutionResult(Base):
    __tablename__ = "execution_results"
    __table_args__ = (
        UniqueConstraint("task_id", "result_sequence", name="uq_execution_result_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    result_push_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("coordination_tasks.id"), index=True)
    result_sequence: Mapped[int] = mapped_column(Integer)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_status: Mapped[str] = mapped_column(String(32))
    execution_mode: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class MonitoringSnapshot(Base):
    __tablename__ = "monitoring_snapshots"
    __table_args__ = (
        UniqueConstraint("case_id", "domain", "snapshot_sequence", name="uq_monitoring_snapshot_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    snapshot_push_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("coordination_cases.id"), index=True)
    domain: Mapped[str] = mapped_column(String(8))
    snapshot_sequence: Mapped[int] = mapped_column(Integer)
    metric_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    domain_judgement: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    object_version: Mapped[int] = mapped_column(Integer, default=1)


class Retrospective(Base):
    __tablename__ = "retrospectives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    case_id: Mapped[str] = mapped_column(ForeignKey("coordination_cases.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    summary: Mapped[str] = mapped_column(Text)
    timeline_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    result_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    lessons: Mapped[list[str]] = mapped_column(JSON, default=list)
    follow_up_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    generated_by: Mapped[str] = mapped_column(String(255))
    approval_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class CoordinationAuditEvent(Base):
    __tablename__ = "coordination_audit_events"
    __table_args__ = (Index("ix_coordination_audit_aggregate", "aggregate_type", "aggregate_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64))
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
