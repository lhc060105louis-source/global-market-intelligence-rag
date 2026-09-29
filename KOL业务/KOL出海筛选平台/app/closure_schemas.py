from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ActorRole = Literal[
    "project_owner", "business_analyst", "data_owner", "brand_owner", "admin"
]


class ClosureCreate(BaseModel):
    actor: str = Field(default="项目负责人", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"


class ClosureCheckUpdate(BaseModel):
    check_key: str = Field(min_length=1, max_length=60)
    status: Literal["通过", "待确认", "阻断"]
    note: str | None = Field(default=None, max_length=1000)


class ClosureChecksPayload(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="项目负责人", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    items: list[ClosureCheckUpdate] = Field(min_length=1)


class ClosureIssueCreate(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="项目负责人", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    issue_type: Literal["数据", "合同", "付款", "内容", "风险", "资产", "其他"]
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=2, max_length=2000)
    severity: Literal["阻断", "重要", "普通"]
    owner: str = Field(min_length=1, max_length=100)
    due_date: date
    source_reference: str | None = Field(default=None, max_length=255)


class ClosureIssuePatch(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="项目负责人", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    status: Literal["未开始", "处理中", "已解决", "接受遗留"]
    resolution_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_resolution(self):
        if self.status in {"已解决", "接受遗留"} and not (self.resolution_note or "").strip():
            raise ValueError("关闭或接受遗留事项时必须填写处理说明")
        return self


class ClosureSummaryPayload(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="业务分析", min_length=1, max_length=100)
    actor_role: ActorRole = "business_analyst"
    objective_result: Literal["达成", "部分达成", "未达成", "待确认"]
    executive_summary: str = Field(min_length=10, max_length=3000)
    key_results: str = Field(min_length=2, max_length=3000)
    top_kols: str = Field(min_length=2, max_length=2000)
    risk_kols: str = Field(min_length=2, max_length=2000)
    lessons_learned: str = Field(min_length=2, max_length=3000)
    next_action: str = Field(min_length=2, max_length=3000)


class ClosureActionPayload(BaseModel):
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="项目负责人", min_length=1, max_length=100)
    actor_role: ActorRole = "project_owner"
    reason: str | None = Field(default=None, max_length=2000)


class ClosureDecisionPayload(ClosureActionPayload):
    decision: Literal["确认结案", "退回补充"]

    @model_validator(mode="after")
    def require_return_reason(self):
        if self.decision == "退回补充" and not (self.reason or "").strip():
            raise ValueError("退回补充时必须填写原因")
        return self
