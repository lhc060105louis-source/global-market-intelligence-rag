from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, StrictFloat, StrictInt, TypeAdapter, field_validator, model_validator


C_RECORD_TYPES = {
    "consumer_journey_sentiment": "journey_sentiment",
    "consumer_nps_prediction": "nps_prediction",
    "consumer_key_complaints": "key_complaints",
    "consumer_brand_attitude": "brand_attitude",
    "consumer_recall_risk": "recall_risk",
    "consumer_legal_risk": "legal_risk",
}
B_RECORD_TYPES = {
    "business_policy": "policy",
    "business_procurement": "procurement",
    "business_market": "market",
    "business_customer_partner": "customer_partner",
}
KOL_RECORD_TYPES = {"kol_current_assessment", "kol_cooperation_result"}
RISK_RECORD_TYPES = {"consumer_recall_risk", "consumer_legal_risk"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Complaint(StrictModel):
    topic_id: str
    topic_name: str
    part: str
    frequency: StrictInt = Field(ge=0)
    average_sentiment_intensity: StrictFloat
    trend_direction: str


class ConsumerResult(StrictModel):
    model_config = ConfigDict(extra="allow")
    positive_ratio: StrictFloat | None = None
    negative_ratio: StrictFloat | None = None
    neutral_ratio: StrictFloat | None = None
    trend_direction: str | None = None
    granularity: str | None = None
    nps_value: StrictFloat | None = None
    change_from_previous: StrictFloat | None = None
    promoter_ratio: StrictFloat | None = None
    passive_ratio: StrictFloat | None = None
    detractor_ratio: StrictFloat | None = None
    complaints: list[Complaint] | None = None
    attitude: str | None = None
    part: str | None = None
    risk_type: str | None = None
    hit_count: StrictInt | None = Field(default=None, ge=0)
    threshold: StrictInt | None = Field(default=None, ge=0)
    threshold_exceeded: StrictBool | None = None
    first_hit_at: datetime | None = None
    risk_status: str | None = None
    risk_level: str | None = None

    @field_validator("first_hit_at")
    @classmethod
    def first_hit_at_aware(cls, value: datetime | None) -> datetime | None:
        return validate_aware(value, "first_hit_at") if value else value


RESULT_REQUIRED = {
    "consumer_journey_sentiment": {"positive_ratio", "negative_ratio", "neutral_ratio", "trend_direction", "granularity"},
    "consumer_nps_prediction": {"nps_value", "change_from_previous", "promoter_ratio", "passive_ratio", "detractor_ratio"},
    "consumer_key_complaints": {"complaints"},
    "consumer_brand_attitude": {"attitude", "positive_ratio", "negative_ratio", "neutral_ratio", "trend_direction"},
    "consumer_recall_risk": {"part", "risk_type", "hit_count", "threshold", "threshold_exceeded", "first_hit_at", "risk_status"},
    "consumer_legal_risk": {"part", "risk_type", "hit_count", "threshold", "threshold_exceeded", "risk_level", "risk_status"},
}


class ConsumerPayload(StrictModel):
    scope_id: str = Field(min_length=1)
    dimension: Literal["journey_sentiment", "nps_prediction", "key_complaints", "brand_attitude", "recall_risk", "legal_risk"]
    brand: str
    vehicle_model: str
    region: str
    journey_stage: str
    channel: str
    language: str
    period_start: datetime
    period_end: datetime
    business_date: date
    signal_count: StrictInt = Field(ge=0)
    emotion_distribution: dict[str, Any]
    result: ConsumerResult

    @model_validator(mode="after")
    def validate_period(self):
        validate_aware(self.period_start, "period_start")
        validate_aware(self.period_end, "period_end")
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self


class RelatedEntity(StrictModel):
    type: str | None = None
    standard_name: str | None = None
    stable_id: str | None = None


class ExternalSource(StrictModel):
    name: str
    url: HttpUrl


class BusinessPayload(StrictModel):
    entry_id: str
    entry_type: Literal["policy", "procurement", "market", "customer_partner"]
    title: str
    published_summary: str
    regions: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    business_impact: str | None = None
    recommended_action: str | None = None
    external_sources: list[ExternalSource] = Field(default_factory=list)
    publication_status: str
    published_at: datetime

    @field_validator("publication_status")
    @classmethod
    def published_only(cls, value: str) -> str:
        if value != "published":
            raise ValueError("publication_status must be published")
        return value

    @field_validator("published_at")
    @classmethod
    def published_at_aware(cls, value: datetime) -> datetime:
        return validate_aware(value, "published_at")


class KolAssessmentPayload(StrictModel):
    kol_id: str
    display_name: str
    primary_platform: str
    content_categories: list[str] = Field(default_factory=list)
    audience_regions: list[str] = Field(default_factory=list)
    commercial_score: StrictFloat
    commercial_dimensions: dict[str, Any] = Field(default_factory=dict)
    risk_score: StrictFloat
    risk_level: str
    risk_tags: list[str] = Field(default_factory=list)
    cooperation_conclusion: str


class KolCooperationPayload(StrictModel):
    cooperation_id: str
    kol_id: str
    project_id: str
    project_name: str
    brand: str | None = None
    vehicle_model: str | None = None
    final_stage: str = Field(min_length=1)
    distribution_conclusion: str | None = None
    performance_summary: str | None = None
    public_opinion_conclusion: str | None = None
    review_conclusion: str
    cooperation_start: datetime | None = None
    cooperation_end: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.cooperation_start:
            validate_aware(self.cooperation_start, "cooperation_start")
        if self.cooperation_end:
            validate_aware(self.cooperation_end, "cooperation_end")
        if self.cooperation_start and self.cooperation_end and self.cooperation_start > self.cooperation_end:
            raise ValueError("cooperation_start must not be after cooperation_end")
        return self


def validate_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value


class IngestionEnvelope(StrictModel):
    source_system: Literal["C", "B", "KOL"]
    source_record_id: str = Field(min_length=1)
    record_type: str
    event_type: Literal["update_current", "create_snapshot", "archive", "restore", "risk_recovery"]
    source_version: StrictInt = Field(ge=1)
    effective_at: datetime
    source_updated_at: datetime
    source_url: HttpUrl | None = None
    push_id: str = Field(min_length=1)
    is_mock: StrictBool
    payload: dict[str, Any]

    @field_validator("effective_at", "source_updated_at")
    @classmethod
    def aware_datetime(cls, value: datetime, info):
        return validate_aware(value, info.field_name)

    def validated_payload(self) -> StrictModel:
        if self.source_system == "C":
            model = TypeAdapter(ConsumerPayload).validate_python(self.payload)
            if self.record_type not in C_RECORD_TYPES:
                raise ValueError("record_type is invalid for C")
            if model.dimension != C_RECORD_TYPES[self.record_type]:
                raise ValueError("dimension does not match record_type")
            missing = [name for name in RESULT_REQUIRED[self.record_type] if getattr(model.result, name) is None]
            if missing:
                raise ValueError(f"result is missing required fields: {', '.join(sorted(missing))}")
            return model
        if self.source_system == "B":
            model = TypeAdapter(BusinessPayload).validate_python(self.payload)
            if self.record_type not in B_RECORD_TYPES or model.entry_type != B_RECORD_TYPES[self.record_type]:
                raise ValueError("entry_type does not match record_type")
            return model
        if self.record_type == "kol_current_assessment":
            return TypeAdapter(KolAssessmentPayload).validate_python(self.payload)
        if self.record_type == "kol_cooperation_result":
            return TypeAdapter(KolCooperationPayload).validate_python(self.payload)
        raise ValueError("record_type is invalid for KOL")


class AnnotationCreate(StrictModel):
    annotation_type: Literal["private_note", "public_note", "correction_feedback"]
    content: str = Field(min_length=1)
    author: str = Field(min_length=1)


class MaintenanceRequest(StrictModel):
    operator: str = Field(min_length=1)


class RebuildRequest(MaintenanceRequest):
    source_system: Literal["C", "B", "KOL"] | None = None
    target_knowledge_base: Literal["c_current", "c_history", "b_business", "kol"] | None = None

    @model_validator(mode="after")
    def require_scope(self):
        if self.source_system is None and self.target_knowledge_base is None:
            raise ValueError("rebuild requires source_system or target_knowledge_base")
        return self
