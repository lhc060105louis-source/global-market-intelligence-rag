# 跨域风险调查 Agent MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在风险页面加入一个可追踪、引用证据、经人工批准后才创建协同案例和任务的跨域调查 Agent。

**Architecture:** 使用一个 Agent 服务，通过现有 RAG 适配器和记录验证逻辑进行有界只读检索；用本地 Ollama 产生结构化工具调用建议和调查草稿。将运行状态保存在 `agent_runs`，由 FastAPI 后台任务执行调查；审批在单一数据库事务中建立领域事件、关联候选、案例和任务。`PageAlert` 提供调查与审批界面。

**Tech Stack:** Python 3.11、FastAPI、Pydantic 2、SQLAlchemy、Alembic、httpx、Ollama `/api/chat`、React、TypeScript、Vite。

## 全局约束

- 每次运行最多调用工具 6 次，查询时限默认 60 秒。
- 每次搜索使用现有 top-K 上限；最终简报每个领域最多引用 3 条记录。
- 仅允许 C、B、KOL 知识目标；Agent 调查阶段只能使用只读工具。
- 模型输出和检索文档均为不可信输入；校验工具名称、参数、领域、记录 ID 和剩余预算。
- 模型失败、JSON 无效、超时或没有证据时，不得创建协同记录。
- Agent 不能访问任意 URL、Shell、文件系统、消息发送或外部写操作。
- 审批前来源版本变化时，草稿必须标记过期并要求重新调查。
- 所有正式关联、案例和任务都必须由业务人员审批后创建。
- 继续支持现有 `/api/v1/query` 行为；fake 适配器不可用作真实调查结果。
- 第一版不包含后台风险监控、自动触发、自动执行任务、多 Agent、新数据连接器、向量数据库替换或法律/市场/投资自动决策。
- 本计划不增加或运行自动化测试；用户如需测试或验证，可另行要求。

---

## 文件职责

- `rag/service/app/models.py`：持久化 Agent 运行状态、证据轨迹和审批结果。
- `rag/service/app/risk_investigation_schemas.py`：Agent 请求、响应、工具提案、草稿和审批输入的严格 Pydantic 合约。
- `rag/service/app/risk_investigation.py`：只读工具分发、有界 Ollama 调用、证据整理、运行状态更新和审批事务。
- `rag/service/app/main.py`：注册鉴权 API 路由、安排后台任务、启动时恢复中断运行。
- `rag/service/alembic_migrations/versions/0004_risk_investigation_agent.py`：新增运行记录表、索引和外键。
- `rag/frontend-v2/src/lib/api.ts`：Agent API 类型与请求函数。
- `rag/frontend-v2/src/pages/PageAlert.tsx`：从活跃风险启动调查并呈现结果和审批操作。
- `README.md`：说明配置前提和手动调查流程。

## 实现任务

### Task 1：持久化运行记录和严格 API 合约

**文件：**

- 修改：`rag/service/app/models.py`
- 新建：`rag/service/app/risk_investigation_schemas.py`
- 新建：`rag/service/alembic_migrations/versions/0004_risk_investigation_agent.py`

**接口：**

- 产生 `AgentRun` 模型，字段包括：`id`、唯一 `request_key`、`risk_object_id`、`episode_id`、来源版本 JSON、`status`、工具轨迹 JSON、草稿 JSON、决定、发起人、结果事件/候选/案例 ID、`object_version`、错误码、创建/完成/审批时间。
- 运行状态限定为 `queued`、`running`、`awaiting_approval`、`needs_clarification`、`no_evidence`、`failed`、`approved`、`rejected`、`stale`。
- 定义 `RiskInvestigationStart`、`AgentToolProposal`、`RiskInvestigationDraft`、`TaskDraft`、`RiskInvestigationDecision` 请求/响应合约；Pydantic 模型使用 `extra="forbid"`。
- `RiskInvestigationDecision` 要求决定值、期望 `object_version` 和操作者；批准时允许提交用户编辑后的任务草案。

**步骤：**

- [x] 在模型文件中加入 `AgentRun` SQLAlchemy 模型，增加 `request_key` 唯一索引、风险对象和事件周期外键、状态索引及 JSON 状态字段。
- [x] 在新 schema 文件中定义上面的输入输出类型；限制工具名为四个只读工具：`get_risk_context`、`get_record`、`search_domain`、`finish_investigation`。
- [x] 新建 Alembic 迁移，`down_revision` 指向 `0003_coordination_delivery_idempotency`；升级创建表及索引，降级按依赖顺序删除。
- [x] 确认迁移字段名称与 ORM 完全一致，并确认请求键和状态字段有数据库级索引约束。

### Task 2：受限调查服务

**文件：**

- 新建：`rag/service/app/risk_investigation.py`
- 修改：`rag/service/app/query.py`（只在需要共用证据验证函数时）

**接口：**

- `run_risk_investigation(run_id: str, *, session_factory, adapter, settings) -> None`：读取运行记录、执行循环并持久化最终状态。
- `approve_risk_investigation(db: Session, *, run_id: str, body: RiskInvestigationDecision, actor_id: str) -> AgentRun`：验证版本并在一个事务中创建正式协同对象。
- Ollama 工具调用 JSON 形状：`{"tool": "search_domain", "arguments": {"target": "b_business", "query": "..."}}`；完成时返回 `{"tool": "finish_investigation", "arguments": {"draft": {...}}}`。

**步骤：**

- [x] 实现只读工具分发：风险上下文只从风险对象、活跃事件周期和趋势点读取；记录读取只接受数据库已有 ID；搜索只允许 `c_current`、`c_history`、`b_business`、`kol`。
- [x] 使用现有 `query.py` 的 `evaluate_evidence` / `filter_effective_evidence` 等函数，将 MaxKB 命中文档解析回当前有效、来源版本一致的 `KnowledgeRecord`；不接受适配器返回的自由文本作为未经验证的证据。
- [x] 为每次运行设 6 次工具调用和配置的总查询时限；每次 Ollama 调用使用 httpx 超时；序列化前裁剪轨迹字段，不存储凭据或完整提示词。
- [x] 使用 Ollama `/api/chat` 的 JSON 输出格式；提示词要求只选择白名单工具，声明证据是数据不是指令，且最终草稿只能引用已验证证据。
- [x] 按以下循环执行：载入风险上下文 → 将当前可用工具、已验证证据摘要和剩余预算传给模型 → 验证并执行一个只读工具 → 将已清理的调用和结果写入 `tool_trace_json` → 继续，直到模型选 `finish_investigation` 或达到调用/时间上限。
- [x] 对每个工具提案验证 schema、参数、域、记录 ID、查询长度、调用预算和风险主体范围；无效提案按失败处理，不执行工具。
- [x] 证据为空时保存 `no_evidence`；主体缺少品牌/车型时保存 `needs_clarification`；模型错误、超时或预算用尽时保存可公开错误码并禁止审批。
- [x] 最终草稿限制每域最多 3 条证据，保存 `record_id`、`source_version`、证据字段路径和哈希引用，列出数据时间、证据缺口、限制及建议任务。
- [x] 实现审批事务：再次校验证据版本和哈希；调用新增的 `create_investigation_domain_event(db, run, actor_id)` 创建/复用来源领域事件；用确定性候选键创建并接受关联候选；创建案例和任务；写入协调审计事件；更新运行结果 ID 和终态。事务失败时全部回滚。`create_investigation_domain_event` 必须使用 `DomainEvent`、`DomainEventRevision`、`event_revision_payload`、`stable_hash` 现有模型/哈希规则，并绑定到风险趋势点的主来源记录。
- [x] 审批采用期望 `object_version` 和条件状态更新；重复审批返回原有结果，过期证据将运行标记为 `stale`。

### Task 3：鉴权端点和后台运行生命周期

**文件：**

- 修改：`rag/service/app/main.py`
- 修改：`rag/service/app/risk_investigation.py`

**接口：**

- `POST /api/v1/agent/risk-investigations`：请求含 `risk_object_id`、`request_key`；响应含 `run_id` 和 `queued` 状态。
- `GET /api/v1/agent/risk-investigations/{run_id}`：返回状态、简报、工具轨迹、证据引用、决定和案例 ID。
- `POST /api/v1/agent/risk-investigations/{run_id}/decision`：批准或拒绝并要求 `expected_object_version`。

**步骤：**

- [x] 在 `create_app` 中注册三个使用现有 `auth` 和 `get_db` 依赖的路由。
- [x] 启动端点验证风险存在且有活跃事件周期、来源点和最新版本；相同请求键与风险主体返回同一运行，不同风险主体复用该键时返回冲突；检测 fake adapter 或无搜索接口，返回可操作的 `agent_unavailable` 错误。
- [x] 提交 `queued` 记录后用 FastAPI `BackgroundTasks` 安排 `run_risk_investigation`，将 session factory、adapter 和 settings 显式传入后台函数；限制同时执行的运行数量为 2。
- [x] 获取端点只返回已清理的轨迹和输出字段；错误响应遵循现有 `request_id` 和 `error_code` 格式。
- [x] 决定端点只接受 `awaiting_approval` 的运行，并调用 Task 2 的原子审批函数；拒绝只记录人类决定，不创建领域事件、候选、案例或任务。
- [x] 在应用 lifespan 的数据库迁移完成后，将残留 `queued`/`running` 记录更新为 `failed`，错误码为 `interrupted_by_restart`。
- [x] 后台函数每次状态变化都单独提交；确保任意未捕获异常被转换为安全错误码并持久化，不向用户返回模型堆栈或凭据。

### Task 4：风险页面调查与审批 UI

**文件：**

- 修改：`rag/frontend-v2/src/lib/api.ts`
- 修改：`rag/frontend-v2/src/pages/PageAlert.tsx`

**接口：**

- 增加 `RiskInvestigationRun`、证据引用、任务草案和决定类型。
- 增加 `startRiskInvestigation(riskId, requestKey)`、`getRiskInvestigation(runId, signal)`、`decideRiskInvestigation(runId, body)` 请求函数。

**步骤：**

- [x] 在 API 客户端添加三个 Agent 请求函数；使用现有 `request<T>` 处理 JSON、鉴权代理和错误。
- [x] 仅对活跃风险显示“Investigate”按钮；点击后创建随机请求键、启动运行并每秒读取状态，直到运行进入待审或终态；组件卸载时取消轮询。
- [x] 显示排队/运行/澄清/无证据/失败/过期状态，清楚区分部分失败和完整调查；不把模型错误详情或内部提示词显示给用户。
- [x] 显示简报、按域归类的证据（记录标题、来源版本、日期和来源链接）、数据限制、缺失领域和任务草案。
- [x] 对任务草案提供有限编辑：领域、任务类型、负责人和预期输出；审批请求携带当前 `object_version` 和编辑后的任务数组。
- [x] 只有 `awaiting_approval` 显示“Approve”与“Reject”；拒绝要求简短理由。批准成功显示案例链接，重复点击期间禁用按钮并刷新运行结果。

### Task 5：运行说明和配置提示

**文件：**

- 修改：`README.md`
- 可选修改：`rag/service/.env.example`（只有确实新增配置项时）

**步骤：**

- [x] 在 README 增加第一版 Agent 运行流程、MaxKB 搜索适配器和 Ollama 的前置条件，以及 fake adapter 下 Agent 不可用的说明。
- [x] 说明如何从活跃风险启动调查、查看证据、审批/拒绝和处理来源过期状态。
- [x] 说明调查是原型决策支持，所有正式协同对象都要人工审批；不声称已经验证市场或合规效果。
- [x] 不修改用户未授权的数据集或外部服务配置，不提交真实凭据。

## 手工验收场景

使用已配置的 MaxKB 和本地 Ollama 手工验证一个已有活跃风险：

1. 从活跃风险点击“Investigate”，确认只生成一个运行记录，返回 `queued` 后状态可查询。
2. 调查完成后，确认每个显示的引用都能解析到对应 `record_id` 和保存的 `source_version`，并展示来源链接或可读预览。
3. 确认没有 B2B 或 KOL 证据时，简报明确写出证据缺口，不伪造跨域影响。
4. 拒绝草稿后，确认没有生成正式领域事件、候选、案例或任务。
5. 对证据版本仍有效的草稿批准一次，确认只创建一个候选、一个案例和建议任务；重复提交返回原案例。
6. 将来源版本更新后再审批旧草稿，确认返回 `stale` 且没有创建任何协同对象。
7. 用默认 fake adapter 启动时，确认界面显示配置提示，运行结果没有伪装成真实证据。

## 执行说明

本会话当前约束禁止在未被明确要求时新增或运行自动化测试。实现阶段按上述手工验收场景检查交互；如需自动化测试或构建验证，请由用户另行要求。
