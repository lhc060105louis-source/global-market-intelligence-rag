from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskInvestigationStart(AgentModel):
    risk_object_id: str = Field(min_length=1, max_length=36)
    request_key: str = Field(min_length=8, max_length=128)


class TaskDraft(AgentModel):
    owner_domain: Literal["C", "B", "KOL"]
    task_type: str = Field(min_length=1, max_length=64)
    assignee: str | None = Field(default=None, max_length=255)
    expected_output_type: str = Field(min_length=1, max_length=64)
    is_required: bool = True


class EvidenceCitation(AgentModel):
    record_id: str = Field(min_length=1, max_length=36)
    domain: Literal["c_current", "c_history", "b_business", "kol"]
    source_version: int = Field(ge=1)
    source_url: str | None = None
    business_date: str | None = None
    title: str = Field(max_length=500)
    preview: str = Field(max_length=500)
    field_path: str = Field(min_length=1, max_length=255)
    excerpt_hash: str = Field(min_length=16, max_length=128)


class RiskInvestigationDraft(AgentModel):
    summary: str = Field(min_length=1, max_length=5000)
    domain_impacts: dict[str, str] = Field(default_factory=dict)
    evidence: list[EvidenceCitation] = Field(default_factory=list, max_length=9)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    tasks: list[TaskDraft] = Field(min_length=1, max_length=12)


class RiskInvestigationDraftProposal(AgentModel):
    summary: str = Field(min_length=1, max_length=5000)
    domain_impacts: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=24)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    tasks: list[TaskDraft] = Field(min_length=1, max_length=12)


class AgentToolProposal(AgentModel):
    tool: Literal["get_risk_context", "get_record", "search_domain", "finish_investigation"]
    arguments: dict[str, Any]


class RiskInvestigationDecision(AgentModel):
    decision: Literal["approve", "reject"]
    expected_object_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)
    tasks: list[TaskDraft] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.decision == "reject" and not (self.reason or "").strip():
            raise ValueError("reason is required to reject a proposal")
        return self
