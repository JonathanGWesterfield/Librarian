# M03 · Summary-worker gRPC proof

- **Task ID:** `AD-M03-16`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** owner: **/root/implementer**; branch/worktree: **codex/ad-m03-16-summary-proof** / **/Users/codexai/Documents/Librarian-worktrees/ad-m03-16**; claimed timestamp: **2026-10-26 18:08 CET**; last update: **2026-10-26 18:11 CET**; coordination contact: **/root**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Prove summary-worker invokes only chapter/book summary through its generated client and preserves cancellation/recovery semantics.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-11](11-summary-worker-migration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths/surfaces:** `tests/answer/test_r2_summary_worker_grpc.py` only (create this focused proof file if absent).
- **Forbidden paths/surfaces:** `scripts/process_summary_jobs.py`, `packages/librarian_answer_adapters/worker_lifecycle.py`, API/evaluator code, and all other proof tests. Ignored local configuration, secrets, EPUBs, runtime data, and approved specifications remain forbidden.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Summary-worker inventory row](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Only allowed operations reach the provider; shutdown cancels active RPC and leaves claimed job recoverable.

## Required tests and evidence

Run focused worker integration and summary-worker Compose profile/authorization proof.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs. Redact credentials, local configuration, private EPUB text, prompts, and evidence excerpts.

- **Implementation / merged PR / SHA:** _Not recorded._
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

- **2026-10-26 18:08 CET — Claim:** /root/implementer claimed this parallel implementation slice on `codex/ad-m03-16-summary-proof`, reserving `tests/answer/test_r2_summary_worker_grpc.py` and this task record. Coordinator: /root. Prerequisites were reviewed as complete; this task does not advance M03 or release status.
- **2026-10-26 18:08 CET — In progress:** implementing the reserved live generated-gRPC proof with tracked temporary SQLite data. Coverage will use the durable summary-worker path for chapter and book operations, pre-provider authorization denial, and cancellation/restart recovery.
- **2026-10-26 18:10 CET — Implementation evidence:** added `tests/answer/test_r2_summary_worker_grpc.py`. Its live generated-stub listener/client and temporary SQLite fixture prove a durable summary job reaches the provider through `CHAPTER_SUMMARIZATION` and `BOOK_SUMMARIZATION`, a summary-worker credential cannot invoke tag generation before provider admission, a short generated-client deadline cancels a blocking provider without a late result, and shutdown leaves a claimed job for recovery on the next worker pass. `/private/tmp/librarian-m03-test-venv/bin/python3 -m unittest tests.answer.test_r2_summary_worker_grpc -v` passed 4 tests. `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh tests.answer.test_r2_summary_worker_grpc tests.answer.test_r2_worker_grpc_integration tests.answer.test_r2_worker_scripts tests.answer.test_grpc_generation tests.ingestion.test_summarize` passed 29 tests; ruff and `git diff --check` passed. Compose and full-gate evidence remain coordinator-owned.
- **2026-10-26 18:11 CET — Compose evidence:** coordinator ran the canonical Compose harness in a clean baseline checkout at `d4a4d1cea73247fa5c7320135992089abb0c36d0`: `VERIFY_PROJECT=librarian-ad-m03-16-baseline ANSWER_DELIVERY_REPORT_DIR=/tmp/librarian-ad-m03-16-baseline-reports scripts/run_answer_delivery_compose.sh` passed with exit 0. All four redacted reports and the log are retained at `/tmp/librarian-ad-m03-16-baseline-reports` and `/tmp/librarian-ad-m03-16-baseline-compose.log`. This proves unchanged summary-worker runtime code, but predates the uncommitted proof test.
- **2026-10-26 18:11 CET — External current-main blocker:** unrelated current main `39644a32d4be28b07cea55d380b85a3ab7e98e03` fails the same harness before any service starts because API depends on an undefined `codex-broker` service. Log: `/tmp/librarian-ad-m03-16-compose.log`. This task does not modify the harness and does not attribute the failure to the summary-worker proof.
- **2026-10-26 18:11 CET — Independent review:** `/root/reviewer` approved the code/design proof and independently passed the 29-test focused regression group plus ruff. Lifecycle moved to `in review`; no M03 completion or release readiness is claimed.
- **2026-10-26 18:11 CET — Full local gate:** coordinator ran `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` in the isolated task checkout. It passed with 500 tests in 6.603 seconds; log: `/tmp/librarian-ad-m03-16-check.log`.
- **2026-10-26 18:11 CET — Final independent review:** `/root/reviewer` approved the final focused two-file slice with no blocker or important findings. It independently reran the 29 targeted tests and ruff, and checked the diff and freshness. The clean d4a4 Compose report remains unchanged-runtime baseline evidence; the current-main pre-start harness failure remains an external M03 live-acceptance blocker and is not caused by this test-only slice.

- **2026-10-26 — Command correction:** the successful baseline Compose invocation used `VERIFY_PROJECT=librarian-ad-m03-16`; the report directory was `/tmp/librarian-ad-m03-16-baseline-reports`. The preceding command entry incorrectly added `-baseline` to the project name; evidence and results are unchanged.

- **2026-10-26 — Current-main integration:** rebased the reviewed slice onto `39644a32d4be28b07cea55d380b85a3ab7e98e03` without conflicts. Re-ran the full `scripts/check.sh`: 501 tests passed in 7.524 seconds, exit 0; log `/tmp/librarian-ad-m03-16-rebased-check.log`. The current-main live Compose bootstrap blocker remains separate from this passing deterministic gate.

- **2026-10-26 — PR handoff:** [PR #116](https://github.com/JonathanGWesterfield/Librarian/pull/116) contains the reviewed proof and task-status reconciliation. Its head commit is the implementation SHA. Task16 remains `in review` until merge; task17 is complete via merged PR114.

- **2026-10-26 — Merged completion:** verified PR #116 merged as `e5d57a03ad40b2358968335d5ec53f5785277125`. The independent review, 501-test gate, and labeled clean-baseline Compose proof are recorded above. Task lifecycle is `complete`; the separate current-main Compose bootstrap blocker and M03 release gates remain.

## Handoff

Before review, record exact paths, commands/results, SHA, and PR. Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with a precise reopening condition. A merged task changes the roadmap and #87 only when it changes milestone eligibility, blocker, or next work.
