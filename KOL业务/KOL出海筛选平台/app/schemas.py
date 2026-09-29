from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_COLLECTION_KEYWORDS = [
    "EV",
    "electric car",
    "car review",
    "Chinese EV",
    "BYD",
    "NIO",
    "XPeng",
    "MG electric",
]


class ScoreRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score_type: str
    dimension: str
    auto_score: float | None
    manual_score: float | None
    final_score: float | None
    evidence: str | None
    source: str | None
    manual_evidence: str | None
    manual_source: str | None


class ScoreSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    commercial_score: float | None
    commercial_completeness: float
    commercial_status: str
    risk_score: float | None
    risk_completeness: float
    risk_status: str
    risk_level: str | None


class KolListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sync_id: str
    version: int
    updated_by_device: str
    deleted_at: datetime | None
    name: str | None
    platform: str
    platform_account_id: str | None
    handle: str | None
    profile_url: str | None
    country: str
    language: str | None
    content_categories: str | None
    followers: int | None
    average_engagement_rate: float | None
    audience_country_ratio: float | None
    score_summary: ScoreSummaryResponse | None
    workflow_stage: int = 0


class KolWrite(BaseModel):
    """Writable fields accepted by the prototype's add/edit form."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    platform: str = Field(min_length=1, max_length=50)
    platform_account_id: str | None = Field(default=None, max_length=255)
    handle: str | None = Field(default=None, max_length=255)
    profile_url: str | None = Field(default=None, max_length=500)
    country: str = Field(min_length=1, max_length=50)
    language: str | None = Field(default=None, max_length=50)
    content_categories: str | None = None
    followers: int | None = Field(default=None, ge=0)
    average_engagement_rate: float | None = Field(default=None, ge=0)
    audience_country_ratio: float | None = Field(default=None, ge=0, le=100)
    commercial_inputs: dict = Field(default_factory=dict)
    risk_inputs: dict = Field(default_factory=dict)


class KolUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, min_length=1, max_length=50)
    platform_account_id: str | None = Field(default=None, max_length=255)
    handle: str | None = Field(default=None, max_length=255)
    profile_url: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, min_length=1, max_length=50)
    language: str | None = Field(default=None, max_length=50)
    content_categories: str | None = None
    followers: int | None = Field(default=None, ge=0)
    average_engagement_rate: float | None = Field(default=None, ge=0)
    audience_country_ratio: float | None = Field(default=None, ge=0, le=100)
    commercial_inputs: dict | None = None
    risk_inputs: dict | None = None


class YouTubeLookupRequest(BaseModel):
    profile_url: str = Field(min_length=1, max_length=500)


class YouTubeLookupResponse(BaseModel):
    name: str | None = None
    platform_account_id: str | None = None
    profile_url: str | None = None
    followers: int | None = None
    description: str | None = None


class AssessmentPreviewRequest(BaseModel):
    commercial_inputs: dict = Field(default_factory=dict)
    risk_inputs: dict = Field(default_factory=dict)


class KolDetail(KolListItem):
    score_records: list[ScoreRecordResponse]
    commercial_inputs: dict = Field(default_factory=dict)
    risk_inputs: dict = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    assessment_updated_at: datetime | None = None
    workflow_updated_at: datetime | None = None


class WorkflowUpdate(BaseModel):
    stage: int = Field(ge=0, le=6)


class WorkflowResponse(BaseModel):
    stage: int
    updated_at: datetime


class WorkflowHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: int
    changed_at: datetime
    changed_by_device: str


class ContractWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    status: str = Field(default="draft", max_length=30)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    amount: float | None = Field(default=None, ge=0)
    notes: str | None = None


class ContractResponse(ContractWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kol_id: int
    sync_id: str
    version: int
    created_at: datetime
    updated_at: datetime


class PerformanceReviewWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign: str = Field(min_length=1, max_length=255)
    impressions: int | None = Field(default=None, ge=0)
    engagements: int | None = Field(default=None, ge=0)
    conversions: int | None = Field(default=None, ge=0)
    notes: str | None = None


class PerformanceReviewResponse(PerformanceReviewWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kol_id: int
    sync_id: str
    version: int
    created_at: datetime
    updated_at: datetime


class RegulationChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regulation_id: str = Field(min_length=1, max_length=100)
    regulation_name: str = ""
    country: list[str] = Field(default_factory=list)
    change_type: str = "生效"
    summary: str = ""
    affected_scenarios: list[str] = Field(default_factory=list)
    affected_brands: list[str] = Field(default_factory=list)
    published_at: str = ""

    @field_validator("regulation_id")
    @classmethod
    def nonblank_regulation_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("regulation_id must not be blank")
        return value.strip()

    @field_validator("country")
    @classmethod
    def shared_countries_only(cls, values: list[str]) -> list[str]:
        from app.shared_contracts import to_shared_country

        return [to_shared_country(value).value for value in values]


class RegulationChangeResult(BaseModel):
    matched: int
    created: int
    existing: int


class RegulationReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kol_id: int
    regulation_id: str
    regulation_name: str
    change_type: str
    summary: str
    affected_scenarios: list[str]
    published_at: str
    status: str
    created_at: datetime
    updated_at: datetime


class KOLRiskAlertResponse(BaseModel):
    brand: str
    country: str
    creator_name: str = ""
    platform: str = ""
    severity: str = "medium"
    topic: str = ""
    regulation_hint: str = ""
    detected_at: str = ""


class MigrationResult(BaseModel):
    created: int
    updated: int
    failed: int


class YouTubeEnrichmentRequest(BaseModel):
    kol_ids: list[int] = Field(default_factory=list)


class YouTubeEnrichmentResponse(BaseModel):
    requested: int
    updated: int
    skipped: int
    failed: int


class YouTubeKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=1)


class YouTubeSettingsResponse(BaseModel):
    configured: bool
    valid: bool | None


class SupabaseSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(pattern=r"^https://", max_length=500)
    anon_key: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


class SupabaseSettingsResponse(BaseModel):
    configured: bool
    url: str | None = None


class SyncStatusResponse(BaseModel):
    state: str
    pending: int
    conflicts: int
    last_synced_at: datetime | None = None


class ImportResult(BaseModel):
    job_id: int
    total_rows: int
    created: int
    updated: int
    failed: int


class ImportErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    message: str


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    total_rows: int
    created_count: int
    updated_count: int
    failed_count: int
    errors: list[ImportErrorResponse]


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["youtube"])
    languages: list[str] = Field(default_factory=lambda: ["en", "fr", "de"])
    markets: list[str] = Field(default_factory=lambda: ["GB", "FR", "DE"])
    limit_per_platform: int = Field(default=30, ge=1, le=100)


class CollectionCreateResponse(BaseModel):
    job_id: int
    status: str


class CollectionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str | None
    level: str
    message: str


class CollectionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    keywords: list[str]
    platforms: list[str]
    languages: list[str]
    markets: list[str]
    limit_per_platform: int
    total_found: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    logs: list[CollectionLogResponse]


class ScoreOverrideRequest(BaseModel):
    score_type: str
    dimension: str
    manual_score: float = Field(ge=0, le=100)
    evidence: str | None = None
    source: str | None = None


class ComparisonRequest(BaseModel):
    kol_ids: list[int] = Field(min_length=1, max_length=4)


class ComparisonResponse(BaseModel):
    items: list[KolDetail]


class ShortlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_country: str | None = None
    notes: str | None = None


class ShortlistItemCreate(BaseModel):
    kol_id: int
    priority: int | None = Field(default=None, ge=1)
    recommendation: str | None = None


class ShortlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kol_id: int
    priority: int | None
    recommendation: str | None
    kol: KolListItem


class ShortlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_country: str | None
    notes: str | None
    items: list[ShortlistItemResponse]
