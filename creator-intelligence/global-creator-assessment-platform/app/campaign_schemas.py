"""Validated request contracts for campaign setup and downstream handoffs.

Draft sections may be incomplete; the campaign service checks readiness before
submission. Request schemas enforce types, supported values and numeric bounds.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Market = Literal["DE", "GB"]
ActorRole = Literal[
    "project_owner", "business_analyst", "content_media", "brand_owner",
    "data_owner", "risk_compliance", "admin",
]
HandoffTarget = Literal[
    "kol_screening", "shortlists", "contracts", "monitoring",
    "post_campaign", "reinvestment",
]
ShortText = Annotated[str, Field(min_length=1, max_length=100)]
NonNegativeAmount = Annotated[float, Field(ge=0)]


class CampaignRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False,
    )


class ActorPayload(CampaignRequest):
    actor: ShortText = "Project Owner"
    actor_role: ActorRole = "project_owner"


class VersionedAction(ActorPayload):
    expected_revision: int = Field(ge=1)


class Milestone(CampaignRequest):
    name: ShortText
    planned_date: date
    owner: ShortText
    status: str = Field(default="pending", min_length=1, max_length=30)


class CampaignCreate(ActorPayload):
    project_name: ShortText
    campaign_code: str | None = Field(default=None, max_length=100)
    brand: str = Field(min_length=1, max_length=20)
    vehicle_model: ShortText
    markets: list[Market] = Field(min_length=1)
    primary_market: Market
    objectives: list[ShortText] = Field(default_factory=list)
    start_date: date
    end_date: date
    timezone: str | None = Field(default=None, min_length=1, max_length=50)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    budget_total: NonNegativeAmount
    owner: ShortText
    collaborators: list[ShortText] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope_and_period(self):
        if self.primary_market not in self.markets:
            raise ValueError("The primary market must be included in the target markets.")
        if self.start_date > self.end_date:
            raise ValueError("The campaign start date must not be after the end date.")
        return self


class CampaignPatch(VersionedAction):
    project_name: ShortText | None = None
    campaign_code: str | None = Field(default=None, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=20)
    vehicle_model: ShortText | None = None
    markets: list[Market] | None = Field(default=None, min_length=1)
    primary_market: Market | None = None
    objectives: list[ShortText] | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=50)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    budget_total: NonNegativeAmount | None = None
    owner: ShortText | None = None
    collaborators: list[ShortText] | None = None
    milestones: list[Milestone] | None = None

    @model_validator(mode="after")
    def validate_supplied_scope_and_period(self):
        if self.markets is not None and self.primary_market is not None:
            if self.primary_market not in self.markets:
                raise ValueError("The primary market must be included in the target markets.")
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("The campaign start date must not be after the end date.")
        return self


class Audience(CampaignRequest):
    name: ShortText
    market: Market
    language: str = Field(min_length=1, max_length=50)
    purchase_stage: ShortText
    priority: Literal["core", "secondary", "reach"] = "core"


class StrategyPayload(VersionedAction):
    audiences: list[Audience] = Field(default_factory=list)
    platforms: list[ShortText] = Field(default_factory=list)
    content_formats: list[ShortText] = Field(default_factory=list)
    message_pillars: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    cta: str | None = None
    disclosure_rule: str | None = None
    usage_rights_need: str | None = None
    competitor_exclusivity: str | None = None
    risk_reviewer: str | None = Field(default=None, max_length=100)


class MeasurementItem(CampaignRequest):
    metric_code: ShortText
    name: ShortText
    target_value: NonNegativeAmount | None = None
    unit: str | None = Field(default=None, max_length=50)
    formula: str | None = None
    data_source: str | None = None
    data_status: Literal["manual", "connected", "pending"] = "pending"
    observation_window: str | None = None
    owner: str | None = Field(default=None, max_length=100)
    refresh_frequency: str | None = Field(default=None, max_length=100)
    is_primary: bool = False


class MeasurementPlanPayload(VersionedAction):
    items: list[MeasurementItem] = Field(default_factory=list)


class KolRole(CampaignRequest):
    role_code: ShortText
    role_name: ShortText
    market: Market
    platform: str = Field(min_length=1, max_length=50)
    required_count: int = Field(ge=1)
    content_format: str | None = None
    audience_requirement: str | None = None
    score_preferences: list[str] = Field(default_factory=list)
    risk_threshold: str | None = None
    quote_min: NonNegativeAmount | None = None
    quote_cap: NonNegativeAmount | None = None
    estimated: bool = True


class BudgetItem(CampaignRequest):
    category: ShortText
    amount: NonNegativeAmount
    estimated: bool = True
    assumption: str | None = None


class KolRequirementsPayload(VersionedAction):
    roles: list[KolRole] = Field(default_factory=list)
    budget_items: list[BudgetItem] = Field(default_factory=list)


class DecisionPayload(VersionedAction):
    decision: Literal["approve", "return", "reject"]
    reason: str | None = None
    risk_signoff: bool = False


class PublishPayload(ActorPayload):
    version_number: int | None = Field(default=None, ge=1)
    targets: list[HandoffTarget] = Field(default_factory=lambda: [
        "kol_screening", "shortlists", "contracts", "monitoring",
        "post_campaign", "reinvestment",
    ], min_length=1)


class EntityLinkPayload(CampaignRequest):
    entity_type: str = Field(min_length=1, max_length=50)
    entity_id: ShortText
    version_number: int | None = Field(default=None, ge=1)
