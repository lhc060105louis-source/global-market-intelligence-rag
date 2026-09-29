# Cross-Domain Risk Investigation Agent Design

**Status:** Approved direction; design review pending  
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
