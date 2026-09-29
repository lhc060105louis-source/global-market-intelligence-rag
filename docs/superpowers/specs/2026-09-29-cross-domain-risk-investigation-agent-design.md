# Cross-Domain Risk Investigation Agent Design

**Status:** Bilingual specification; user review pending

**Date:** 2026-09-29

## Goal

Add a bounded, evidence-grounded risk investigation Agent to the existing Global Market Intelligence and Risk Analysis Platform. An operator starts an investigation from an active risk in the Alert page. The Agent gathers relevant evidence from the consumer, B2B, and creator domains, drafts an impact brief and proposed follow-up tasks, and waits for operator approval before creating formal coordination records.

The first release demonstrates a complete read, reason, propose, approve workflow. It does not perform external actions or make autonomous compliance decisions.

## Existing project context

- `rag/service/app/main.py` owns the FastAPI query and coordination routes. The query route retrieves and validates evidence, and the coordination routes persist domain events, association candidates, cases, tasks, results, monitoring snapshots, and audit events.
- Active risk details expose trend points with source record IDs and source versions. These are suitable starting evidence for an investigation from the existing Alert page.
- `rag/service/app/config.py` already configures the RAG adapter and Ollama model. The current query planner and semantic draft default to shadow mode.
- `rag/frontend-v2/src/pages/PageAlert.tsx` already displays active risks and loads their source evidence on demand.
- The current public README describes the project as a research prototype and does not claim validated model performance. The Agent must present citations and evidence gaps, and its evaluation must be separate from ordinary unit and contract tests.

## User flow

1. The operator selects an active risk in **Alert Coordination** and starts an investigation.
2. The API creates a persisted Agent run tied to the risk object, active episode, and latest source record versions, then starts a bounded background run. A restart marks any run left in `queued` or `running` as interrupted and failed; the operator can start a new run.
3. The Agent uses an allowlist of read-only tools to inspect the source records and retrieve relevant consumer, B2B, and KOL evidence. It may ask for a narrower scope when the risk subject is ambiguous.
4. The Agent saves a draft brief containing the cross-domain summary, domain-specific impacts, evidence references, limitations, and proposed tasks. The run becomes `awaiting_approval`.
5. The operator reviews the brief, evidence, and editable task drafts, then approves or rejects the proposal. Approval creates or reuses a `cross_domain_risk_investigation` domain event for the captured source record, accepts the generated association candidate, and creates the coordination case and proposed tasks with existing audit and version controls. Rejection records the decision without creating those records.
6. The page shows the run trace and the resulting case or rejection decision.

## Architecture and components

### Agent orchestration

Add a focused `risk_investigation` service under `rag/service/app`. It owns the bounded investigation loop, allowlisted tool dispatch, result validation, and draft assembly. It reuses the current query planner, RAG adapter, record validation, evidence reference, and coordination services where their boundaries permit. The `/api/v1/query` route should remain compatible; extract shared query operations only where required by the Agent.

The Agent may select among these read-only tools:

- `get_risk_context`: load the selected risk, episode, and source trend points.
- `get_record`: load a record only by an existing record ID and preserve its source version.
- `search_domain`: query one of the existing RAG domains with a bounded query and result count.
- `finish_investigation`: return a structured draft when the evidence is sufficient or state what is missing.

Use the configured local Ollama model for structured planning and final synthesis. Model output is an untrusted tool proposal. Validate its JSON shape, tool name, arguments, domain, record IDs, and remaining budget before dispatch. Retrieved documents are evidence, never instructions. The Agent has no write tool during investigation. Keep the Agent unavailable with an actionable configuration message when the adapter does not support search (including the default fake adapter) or Ollama is unreachable; do not report fake results as an investigation.

### Persistence and API

Add an `agent_runs` table and an Alembic migration. Store the initiating actor, risk and episode IDs, initial source versions, run status, bounded tool-call trace, draft output, approval decision, resulting event/candidate/case IDs, timestamps, and a sanitized failure code. Do not store credentials or full model prompts in the trace. Use FastAPI background work for the first release; on startup, mark orphaned queued/running rows as interrupted failures.

Add authenticated endpoints:

- `POST /api/v1/agent/risk-investigations` to start an investigation from a risk object.
- `GET /api/v1/agent/risk-investigations/{run_id}` to read current state, trace, draft, and decision.
- `POST /api/v1/agent/risk-investigations/{run_id}/decision` to approve or reject an awaiting proposal.

Starting requests must be idempotent for a supplied request key. Approval must also be idempotent and use a database transaction so one approval cannot create duplicate events, candidates, cases, or tasks. Reuse the existing evidence hash/version validation, optimistic object versions, actor identity, and audit events. The generated event is tied to the primary consumer risk record; related B2B and KOL records remain evidence and candidate associations.

### Frontend

Add a **Investigate** action for the selected active risk in `PageAlert.tsx`. Show run progress, retrieved records with their domains and source versions, the brief, gaps and limitations, and proposed tasks. Present approve and reject controls only when the run is awaiting approval. On approval, link to the created coordination case using its existing identifier.

### Run states

`queued → running → awaiting_approval → approved | rejected`

`running` can also end as `needs_clarification`, `no_evidence`, or `failed`. Terminal states cannot be restarted through the decision endpoint. A retry creates a new run and keeps the original trace available.

## Limits and failure handling

- Limit each run to at most 6 tool calls and the configured query deadline (default 60 seconds). Limit each search to the existing top-K bound and a maximum of 3 evidence records per domain in the final brief. Run work in a bounded background task and persist each state change before returning it to the UI.
- Permit only C, B, and KOL knowledge targets. Do not allow arbitrary URLs, shell, filesystem, message sending, or external write operations.
- If the model is unavailable, returns malformed tool JSON, or exceeds the budget, save a failed or partial run with a clear reason. Never create coordination records from a partial or failed run.
- If no evidence is found, return `no_evidence` with the searched domains and do not generate proposed actions.
- If source versions change before approval, mark the proposal stale and require a new investigation rather than applying tasks to outdated evidence.
- If approval fails, roll back all candidate, case, and task writes and retain the run as awaiting approval with an actionable error.
- Require an operator approval for the full proposal. No tool sends notifications, changes upstream systems, or treats generated compliance language as a legal decision.

## Review and evaluation

Before implementation is considered ready, demonstrate one seeded scenario end to end: an active consumer risk with valid source evidence, relevant B2B and KOL records, a cited cross-domain brief, and proposed tasks. Show that missing evidence is reported, rejection creates no coordination records, approval creates exactly one case and its tasks, and every citation resolves to the captured record version.

Evaluate a small, versioned set of public or synthetic scenarios for evidence citation completeness, domain relevance, unsupported claims, false cross-domain associations, operator acceptance, latency, and model/tool failures. Report results as a prototype baseline; do not claim validated market or compliance outcomes.

## Scope exclusions

- Background risk monitoring or automatic event triggering.
- Autonomous task execution, external messaging, or updates to upstream business systems.
- Multiple cooperating Agents.
- New data connectors, new vector database, or replacement of MaxKB/Ollama.
- Automated legal, market forecast, or investment decisions.

## Design self-review

- Every write action is behind the approval endpoint; the investigation loop has read-only tools.
- The start flow uses an active risk object already represented in the Alert page and retrieves source record IDs from its trend points.
- The status flow includes clarification, no-evidence, failure, stale-source, and approval outcomes.
- The design introduces a persisted run and migration because the UI needs durable run state and an auditable approval boundary.
- Evaluation claims are explicitly limited to a prototype baseline.

---

# 跨域风险调查 Agent 设计（中文版）

**状态：** 方向已确认，设计文档待审阅

**日期：** 2026-09-29

## 目标

在现有全球市场情报与风险分析平台中加入一个有明确边界、以证据为依据的风险调查 Agent。业务人员从“风险协同”页面中的一条活跃风险手动发起调查。Agent 收集消费者、B2B 和创作者三个领域的相关证据，起草影响简报和后续任务建议，等待业务人员批准后才创建正式协同记录。

第一版要展示完整的“读取、分析、提出建议、人工批准”流程。它不执行外部操作，也不自主作出合规决定。

## 项目现状

- `rag/service/app/main.py` 实现 FastAPI 查询和协同接口。查询接口负责检索和验证证据；协同接口保存领域事件、关联候选、案例、任务、执行结果、监控记录和审计事件。
- 活跃风险详情包含趋势点及其来源记录 ID 和版本号，可作为从现有风险页面发起调查的起点。
- `rag/service/app/config.py` 已配置 RAG 适配器和 Ollama 模型。当前查询规划器和语义草稿默认处于影子模式。
- `rag/frontend-v2/src/pages/PageAlert.tsx` 已展示活跃风险，并支持按需加载来源证据。
- 当前公开 README 将项目定位为研究原型，没有声称模型效果已通过验证。Agent 必须展示引用来源和证据缺口；Agent 效果评估要独立于普通单元测试和接口契约测试。

## 用户流程

1. 业务人员在“风险协同”页面选择一条活跃风险并启动调查。
2. API 创建一条持久化的 Agent 运行记录，关联风险对象、活跃事件周期和最新来源记录版本，然后启动有界后台任务。服务重启后仍处于 `queued` 或 `running` 的任务会标记为中断失败；业务人员可以重新发起一条调查。
3. Agent 使用只读工具白名单查看来源记录，并检索消费者、B2B 和 KOL 领域的相关信息。如果风险主体不明确，可以要求用户进一步限定范围。
4. Agent 保存一份调查草稿，其中包括跨领域摘要、各领域影响、证据引用、局限说明和待办草案，随后将运行状态改为 `awaiting_approval`。
5. 业务人员审阅简报、证据和可编辑的任务草案，然后批准或拒绝。批准后，系统为已记录的来源记录创建或复用 `cross_domain_risk_investigation` 领域事件，接受 Agent 生成的关联候选，并创建协同案例及待办任务，同时沿用现有审计和版本控制。拒绝则只记录审批结果，不创建上述协同对象。
6. 页面展示运行轨迹，以及创建的案例或拒绝结果。

## 架构与组件

### Agent 协调器

在 `rag/service/app` 下新增专用的 `risk_investigation` 服务，负责有界调查循环、白名单工具调用、结果验证和草稿整理。尽量复用现有查询规划、RAG 适配器、记录验证、证据引用和协同服务。保持 `/api/v1/query` 行为兼容；只有 Agent 确实需要时才抽取共用查询逻辑。

Agent 可从以下只读工具中选择：

- `get_risk_context`：读取所选风险、事件周期和来源趋势点。
- `get_record`：只通过已有记录 ID 读取记录，并保留来源版本。
- `search_domain`：使用有界查询和结果数量，在现有 RAG 领域中检索。
- `finish_investigation`：证据充分时返回结构化调查草稿；证据不足时说明缺少什么。

使用已配置的本地 Ollama 模型进行结构化规划和最终综合。模型输出只是未经信任的工具调用提议。执行前必须验证 JSON 结构、工具名称、参数、领域、记录 ID 和剩余调用预算。检索到的文档只能作为证据，不能作为指令。调查过程中 Agent 没有写入工具。如果适配器不支持搜索（包括默认的 fake 适配器）或 Ollama 无法连接，界面应明确提示配置问题，不能把模拟数据展示成真实调查结果。

### 持久化与 API

新增 `agent_runs` 数据表和 Alembic 迁移。保存发起人、风险和事件周期 ID、初始来源版本、运行状态、有界工具调用轨迹、调查草稿、审批结果、关联领域事件/候选/案例 ID、时间戳和经过清理的错误码。不得把凭据或完整模型提示词写入轨迹。第一版使用 FastAPI 后台任务；服务启动时将遗留的 `queued` 或 `running` 记录标记为中断失败。

新增需要身份验证的接口：

- `POST /api/v1/agent/risk-investigations`：从一条风险对象启动调查。
- `GET /api/v1/agent/risk-investigations/{run_id}`：读取运行状态、轨迹、草稿和审批结果。
- `POST /api/v1/agent/risk-investigations/{run_id}/decision`：批准或拒绝一条待审调查。

启动请求必须支持调用方提供的请求键，重复请求不能重复启动相同运行。审批也必须幂等，并在数据库事务中完成，防止一次批准创建重复事件、候选、案例或任务。复用现有证据哈希/版本验证、乐观版本控制、操作人身份和审计事件。创建的领域事件关联主要消费者风险记录；B2B 和 KOL 记录作为证据及候选关联保留。

### 前端

在 `PageAlert.tsx` 所选活跃风险旁添加“调查”操作。展示运行进度、检索记录的领域和来源版本、调查简报、证据缺口、局限以及任务草案。只有运行状态为 `awaiting_approval` 时显示批准和拒绝操作。批准后，提供到新建协同案例的链接。

### 运行状态

`queued → running → awaiting_approval → approved | rejected`

`running` 也可以结束为 `needs_clarification`、`no_evidence` 或 `failed`。终态不能通过审批接口重新启动。重试会新建一次运行，同时保留原始运行轨迹。

## 限制与失败处理

- 每次运行最多调用工具 6 次，并遵守查询时限（默认 60 秒）。每次搜索使用现有 top-K 上限；最终简报每个领域最多引用 3 条记录。后台任务须有并发上限，并在向界面返回状态前保存每次状态变化。
- 仅允许查询 C、B 和 KOL 知识域。禁止任意网址、Shell、文件系统、消息发送和外部写操作。
- 如果模型不可用、返回无法解析的工具 JSON 或超出预算，保存失败或部分运行，并给出明确原因。部分失败的运行不能创建协同记录。
- 没有找到证据时返回 `no_evidence`，说明搜索过哪些领域，不生成行动建议。
- 如果审批前来源版本发生变化，将草稿标记为过期，要求重新调查，避免基于过期证据创建任务。
- 如果审批写入失败，回滚候选、案例和任务的全部变更；运行保持待审批状态，并显示可处理的错误信息。
- 整份建议必须由业务人员审批。任何工具都不发送通知、不改动上游系统，生成的合规文字也不作为法律结论。

## 审阅与效果评估

实现完成前，使用一条种子场景端到端演示：活跃消费者风险及有效来源证据、相关的 B2B 和 KOL 记录、带引用的跨领域简报和待办草案。演示证据缺失时的处理、拒绝后没有协同记录、批准后只生成一份案例及其任务，并确认每条引用都能解析到已捕获版本的记录。

用一组小型、有版本记录的公开或模拟场景评估证据引用完整度、领域相关性、无依据的断言、错误跨域关联、业务人员采纳情况、延迟以及模型/工具故障。结果只作为原型基线，不宣称已验证市场或合规效果。

## 不在第一版范围内

- 后台持续监控风险或自动触发调查。
- 自主执行任务、对外发送消息或更新上游业务系统。
- 多个 Agent 协作。
- 新增数据连接器、新建向量数据库，或替换 MaxKB/Ollama。
- 自动作出法律、市场预测或投资决定。

## 设计自检

- 所有写操作都在审批接口之后；调查过程只使用只读工具。
- 启动流程使用风险页面已有的活跃风险对象，并从趋势点读取来源记录 ID。
- 状态流覆盖澄清、无证据、失败、来源过期和审批结果。
- 因为界面需要持久运行状态和可审计的审批边界，设计新增运行记录和数据库迁移。
- 对效果的描述明确限定为原型基线。
