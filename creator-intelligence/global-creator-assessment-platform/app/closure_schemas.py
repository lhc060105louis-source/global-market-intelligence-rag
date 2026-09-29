from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ActorRole = Literal[
    "project_owner", "business_analyst", "data_owner", "brand_owner", "admin"
]


class ClosureCreate(BaseModel):
    actor: str = Field(default="Project Owner", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"


class ClosureCheckUpdate(BaseModel):
    check_key: str = Field(min_length=1, max_length=60)
    status: Literal["Passed", "Unconfirmed", "Blocked"]
    note: str | None = Field(default=None, max_length=1000)


class ClosureChecksPayload(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="Project Owner", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    items: list[ClosureCheckUpdate] = Field(min_length=1)


class ClosureIssueCreate(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="Project Owner", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    issue_type: Literal["Data", "Contract", "Payment", "Content", "Risk", "Asset", "Other"]
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=2, max_length=2000)
    severity: Literal["Critical", "Important", "Standard"]
    owner: str = Field(min_length=1, max_length=100)
    due_date: date
    source_reference: str | None = Field(default=None, max_length=255)


class ClosureIssuePatch(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="Project Owner", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    status: Literal["Not Started", "In Progress", "Resolved", "Accept Open Items"]
    resolution_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_resolution(self):
        if self.status in {"Resolved", "Accept Open Items"} and not (self.resolution_note or "").strip():
            raise ValueError("A resolution note is required when resolving or accepting an open item.")
        return self


class ClosureSummaryPayload(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="Business Analyst", min_length=1, max_length=100)
    actor_role: ActorRole = "business_analyst"
    objective_result: Literal["Achieved", "Partially Achieved", "Not Achieved", "Unconfirmed"]
    executive_summary: str = Field(min_length=10, max_length=3000)
    key_results: str = Field(min_length=2, max_length=3000)
    top_kols: str = Field(min_length=2, max_length=2000)
    risk_kols: str = Field(min_length=2, max_length=2000)
    lessons_learned: str = Field(min_length=2, max_length=3000)
    next_action: str = Field(min_length=2, max_length=3000)


class ClosureActionPayload(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="Project Owner", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    reason: str | None = Field(default=None, max_length=2000)


class ClosureDecisionPayload(ClosureActionPayload):
    decision: Literal["Confirm Closure", "Return for More Information"]

    @model_validator(mode="after")
    def require_return_reason(self):
        if self.decision == "Return for More Information" and not (self.reason or "").strip():
            raise ValueError("A reason is required when returning the closure for more information.")
        return self
