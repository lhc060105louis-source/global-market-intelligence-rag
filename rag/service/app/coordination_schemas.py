from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CoordinationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(CoordinationModel):
    record_id: str = Field(min_length=1)
    source_version: int = Field(ge=1)
    field_path: str = Field(min_length=1, max_length=255)
    excerpt_hash: str = Field(min_length=16, max_length=128)
    captured_at: datetime
    source_url_snapshot: str | None = None
    excerpt_preview: str | None = Field(default=None, max_length=500)


class DomainEventCreate(CoordinationModel):
    push_id: str = Field(min_length=1, max_length=255)
    source_domain: Literal["C", "B", "KOL"]
    source_record_id: str = Field(min_length=1)
    source_knowledge_record_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1, max_length=64)
    source_record_version: int = Field(ge=1)
    subject: str = Field(min_length=1, max_length=2000)
    severity: str = Field(min_length=1, max_length=32)
    occurred_at: datetime
    professional_status: str = Field(min_length=1, max_length=32)
    related_record_ids: list[str] = Field(default_factory=list, max_length=100)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    created_by: str = Field(min_length=1, max_length=255)
    execution_mode: Literal["real", "human", "demo"] = "real"
    is_simulated: bool = False


class DomainEventCorrection(DomainEventCreate):
    expected_event_version: int = Field(ge=1)
    expected_object_version: int = Field(ge=1)
    change_reason: str = Field(min_length=1, max_length=2000)


class EventRetraction(CoordinationModel):
    push_id: str = Field(min_length=1, max_length=255)
    expected_event_version: int = Field(ge=1)
    expected_object_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    actor_id: str = Field(min_length=1, max_length=255)


class AssociationSuggestionCreate(CoordinationModel):
    source_event_id: str = Field(min_length=1)
    related_record_ids: list[str] = Field(default_factory=list, max_length=100)
    correlation_basis: list[str] = Field(min_length=1, max_length=20)
    confidence_score: float = Field(ge=0, le=1)
    confidence_explanation: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    rule_version: str = Field(min_length=1, max_length=64)
    submitted_by: str = Field(min_length=1, max_length=255)


class CandidateDecision(CoordinationModel):
    status: Literal["accepted", "rejected", "expired"]
    reason: str = Field(min_length=1, max_length=2000)
    expected_object_version: int = Field(ge=1)
    actor_id: str = Field(min_length=1, max_length=255)


class CaseCreate(CoordinationModel):
    candidate_id: str = Field(min_length=1)
    scenario_type: str = Field(min_length=1, max_length=64)
    priority: str = Field(default="normal", max_length=32)
    created_by: str = Field(min_length=1, max_length=255)
    execution_mode: Literal["real", "human", "demo"] = "real"
    is_simulated: bool = False


class CloseDecision(CoordinationModel):
    decision: Literal["allow", "deny"]
    case_id: str = Field(min_length=1)
    scenario_type: str = Field(min_length=1, max_length=64)
    rule_version: str = Field(min_length=1, max_length=64)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    evaluated_by: str = Field(min_length=1, max_length=255)


class CaseStatusChange(CoordinationModel):
    status: Literal["confirmed", "in_progress", "monitoring", "resolved", "closed", "cancelled"]
    expected_object_version: int = Field(ge=1)
    actor_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2000)
    close_decision: CloseDecision | None = None


class DomainImpactCreate(CoordinationModel):
    case_id: str = Field(min_length=1)
    domain: Literal["C", "B", "KOL"]
    assessment_status: Literal["received", "no_impact", "needs_confirmation"]
    impact_summary: str | None = Field(default=None, max_length=5000)
    source_analysis_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    source_version: int | None = Field(default=None, ge=1)
    assessed_by: str = Field(min_length=1, max_length=255)
    is_simulated: bool = False


class TaskCreate(CoordinationModel):
    owner_domain: Literal["C", "B", "KOL"]
    task_type: str = Field(min_length=1, max_length=64)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    is_required: bool = True
    assignee: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    input_evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    expected_output_type: str = Field(min_length=1, max_length=64)
    verification_rule: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Literal["real", "human", "demo"] = "real"
    created_by: str = Field(min_length=1, max_length=255)


class TaskStatusChange(CoordinationModel):
    status: Literal["assigned", "accepted", "in_progress", "blocked", "cancelled"]
    expected_object_version: int = Field(ge=1)
    actor_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2000)


class ExecutionResultCreate(CoordinationModel):
    result_push_id: str | None = Field(default=None, min_length=1, max_length=255)
    task_id: str = Field(min_length=1)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    result_status: Literal["simulated", "auto_verified_simulation", "human_verified", "rejected"]
    execution_mode: Literal["real", "human", "demo"]
    actor_type: Literal["operator", "domain_service", "system", "scenario_engine", "demo_driver"]
    actor_id: str | None = None
    is_simulated: bool = False
    verification_mode: Literal["human", "rule_engine", "simulator"] | None = None
    verified_by: str | None = None
    verification_rule_version: str | None = None
    fallback_reason: str | None = None


class MonitoringSnapshotCreate(CoordinationModel):
    snapshot_push_id: str | None = Field(default=None, min_length=1, max_length=255)
    case_id: str = Field(min_length=1)
    domain: Literal["C", "B", "KOL"]
    metric_payload: dict[str, Any] = Field(default_factory=dict)
    domain_judgement: str | None = Field(default=None, max_length=5000)
    source_version: int | None = Field(default=None, ge=1)
    rule_version: str | None = Field(default=None, max_length=64)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    is_simulated: bool = False
    captured_at: datetime | None = None
    submitted_by: str = Field(min_length=1, max_length=255)


class RetrospectiveCreate(CoordinationModel):
    case_id: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=10000)
    timeline_refs: list[str] = Field(default_factory=list, max_length=200)
    result_refs: list[str] = Field(default_factory=list, max_length=200)
    lessons: list[str] = Field(default_factory=list, max_length=100)
    follow_up_items: list[str] = Field(default_factory=list, max_length=100)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    generated_by: str = Field(min_length=1, max_length=255)
    approval_mode: Literal["human", "simulated", "auto"] | None = None
    approved_by: str | None = Field(default=None, max_length=255)
    is_simulated: bool = False
