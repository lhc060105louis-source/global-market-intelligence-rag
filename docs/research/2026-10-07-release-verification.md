# First release reliability batch — verification

This batch implements the reliability prerequisites in the GitHub comparison review. It retains the current architecture and does not implement the later shared-identity, claim-level citation, case-workbench or durable-execution proposals.

## Implemented

- Restored the original self-contained VOC engine and adapted its vocabulary to the existing analyzer and Hub contracts. No historical customer data was copied.
- Replaced implicit creator reinvestment fixtures with persisted creators, performance evidence, manual assessments and tasks. Missing data is explicitly unavailable; no portfolio forecast is invented.
- Restored the missing campaign request schemas and checked them against current API and frontend payloads.
- Reserved the final Agent tool call for synthesis; enforced deadlines and exposed unsearched domains. Added real database/API checks for approval retries, evidence changes, rejection and rollback.
- Rejected template Hub credentials, documented `.env` loading, and repaired fresh database migrations plus recovery from the old prematurely-created Agent table without dropping its rows.
- Added frontend type checking and GitHub Actions for Hub, VOC, creator and frontend checks.
- Fixed query error handling, generic-verb domain contamination and creator compliance-hint normalization found by full regression runs. Corrected confirmed obsolete label/packaging assertions.

## Verified local checks

| Check | Result |
| --- | --- |
| Complete Hub Python suite | 166 passed |
| Complete deterministic VOC suite, including real local Hub ingestion | 25 passed |
| Complete creator Python suite, run from its service directory | 267 passed |
| Creator reinvestment UI runtime test | 1 passed |
| Frontend TypeScript check | Passed |
| Frontend production build | Passed |
| Git whitespace/error check | Passed |

The 458 Python tests above passed on the final implementation in separate processes. Windows sandbox restrictions required the local API tests to run outside the sandbox with dedicated temporary databases. An independent reviewer reproduced and verified the fix for cross-campaign approval leakage and reported no remaining actionable findings in this batch. The CI test entry point was then corrected to run creator tests from that service's directory, matching the successful full local run.

This report records verification before publication from the branch `codex/release-reliability`. Publication and hosted CI results are tracked separately in GitHub.

## Verification boundaries

All business records in regression tests are synthetic. Database storage, HTTP API validation and approval transactions are exercised locally; retrieval/model results are deterministic substitutes. Live MaxKB/Ollama connectivity, model output quality and real customer deployments have not been validated. GitHub Actions is configured but has not yet run remotely.

## Additional B2B baseline findings (outside this batch)

The untouched B2B suite was also run: **59 passed, 22 failed**. No B2B or shared-domain source file was changed in this batch. It is not included in the new passing CI jobs and must not be described as fully verified.

The highest-priority remaining failure is `test_product_mismatch_is_a_no_go_hard_gate`: a synthetic passenger-car-only supplier receives `go` for an electric-bus procurement where the test expects the product mismatch hard gate to return `no_go`. Investigate the product taxonomy and translated matching terms before relying on this decision in business use.

The other failures concern navigation/UI labels and wording expectations in frontend, offer and positioning tests. Audit these against intended behavior instead of blindly changing strings to satisfy tests.

Reproduce from the repository root using a separately configured B2B environment:

```bash
python -m pytest b2b-public-sector/week7/compliance-sales-support/tests -q
```
