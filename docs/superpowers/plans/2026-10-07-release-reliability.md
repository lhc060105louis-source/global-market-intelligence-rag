# Release Reliability Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent modules and verification-before-completion before reporting completion.

**Goal:** Make the public checkout runnable and ensure risk investigations and creator reinvestment use bounded execution and actual business records.

**Architecture:** Retain the existing applications and storage. Restore the missing self-contained VOC calculation modules from the user's original source after checking for embedded data/secrets. Replace implicit creator demonstration defaults with database-backed results, preserving the API/UI contracts where possible. Reserve an Agent tool slot for final synthesis and validate configuration at startup.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite, pytest, React, TypeScript, Vite, pnpm.

## Global Constraints

- Preserve existing user files and research notes. Work on `codex/release-reliability`.
- No new agent framework, vector database, message broker or live external actions.
- No embedded customer data, credentials or implicit demonstration business results.
- Preserve evidence/version validation and human approval for coordination writes.
- Regression tests must fail for the targeted bug before the implementation change and pass afterwards.
- External LLM/search responses may be stubbed in deterministic tests; database and approval behavior must be real.

## Task 1 — VOC engine completeness

Files: `customer-voc/six-dimensions-v3.0/core.py`, `dimensions.py`; VOC integration tests and dependency documentation.

- [x] Run existing `tests/test_c_rag_push.py` and capture missing-engine failures.
- [x] Review original `source/C端/六维3.0/core.py` and `dimensions.py` for runtime dependencies and embedded business data.
- [x] Restore only calculation code needed by `six_dimension_service._load_legacy_engine()`, preserving existing output semantics.
- [x] Run VOC tests with synthetic records, including six-dimension aggregation and Hub-envelope validation.
- [x] Document the bundled engine and test command; do not import historical datasets or presentations.

## Task 2 — Real creator reinvestment data

Files: creator `app/services/reinvestment.py`, supporting small service module if needed, API schemas/routes, existing reinvestment frontend, `tests/test_reinvestment_api.py`.

- [x] Add failing behavior tests for an empty database, a new non-seeded creator, changing performance evidence, and missing score/quote data.
- [x] Build candidates from persisted `Kol`, performance, campaign and content records; use stable creator identity.
- [x] Remove fixed scores, historical claims and portfolio outcomes from the default path. Preserve explicit unavailable values where data cannot support a calculation.
- [x] Keep approval/governance/actions persistent and validate referenced creators/tasks. Ensure the frontend handles empty and unavailable results.
- [x] Replace fixture-dependent tests with database-backed fixtures and run creator regression tests.

## Task 3 — Bounded investigations and approval regression coverage

Files: `rag/service/app/risk_investigation.py`, related schemas only if needed; investigation tests.

- [x] Reproduce multiple-source fallback exhausting the six-call budget using the real runner and a temporary database.
- [x] Reserve final synthesis within the six-tool maximum, preserve the time deadline, and surface unsearched-domain gaps deterministically.
- [x] Cover approve/retry, reject, changed evidence and transactional rollback through authenticated APIs.
- [x] Verify failed/partial/no-evidence runs create no coordination records.
- [x] Run the complete Hub suite.

## Task 4 — Startup and repeatable checks

Files: `README.md`, Hub config/startup validation tests, frontend package/type configuration as required, `.github/workflows/tests.yml`.

- [x] Reject blank/default primary API credentials at startup without leaking values. Document `.env` loading for standalone launch.
- [x] Install dependencies only into ignored local environments; run existing baseline suites separately because services share Python package names.
- [x] Add frontend `typecheck` and correct errors revealed by it without redesigning UI behavior.
- [x] Add GitHub Actions jobs for Hub, VOC integration, creator tests and frontend typecheck/build, with explicit Python/Node versions and no live secrets.
- [x] Run equivalent checks locally and distinguish existing failures from introduced regressions.

## Final verification and review

- [x] Review the complete patch for data leakage, implicit demo output, API/UI compatibility and scope.
- [x] Address important review findings and rerun affected checks.
- [x] Record exact tests, results, and any external-service limitation here and in the completion report.

## Execution record

Plan created following approval to start the first delivery batch in the GitHub research report. Later batches (shared identity, claim-level citations, case workbench, persistent investigation recovery and evaluation baseline) remain a separate planned continuation.

Completed on 2026-10-07. Final local results: Hub 166 passed, VOC 25 passed, creator 267 passed, creator UI 1 passed, frontend typecheck and build passed. Independent review found a cross-campaign approval leak; it was fixed and independently rechecked. Fresh-db migration, interrupted migration recovery, missing campaign schemas, semantic query failures and creator compliance-hint normalization were also repaired as baseline blockers. Full details and the untouched B2B baseline (59 passed, 22 failed) are in docs/research/2026-10-07-release-verification.md. At verification time, GitHub Actions and live MaxKB/Ollama remained unverified remotely. Publication is handled in the subsequent GitHub synchronization step.
