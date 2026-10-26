# M03 · API non-chat gRPC proof

- **Task ID:** `AD-M03-15`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **blocked**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **2026-10-26T13:10:00-05:00**; coordination contact: **M03 caller-proof owner.** The prior reservation is released; `tests/answer/test_r2_api_non_chat_grpc.py` remains available for this task's next claim.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Prove book summary, genre, and recommendation API routes use only the API principal’s ready generated client and permitted operations.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-10](10-api-non-chat-migration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths/surfaces:** `tests/answer/test_r2_api_non_chat_grpc.py` only (create this focused proof file if absent).
- **Forbidden paths/surfaces:** `apps/api/librarian_api/main.py`, `apps/api/librarian_api/r2_chat.py`, `tests/answer/test_grpc_chat.py`, and worker/evaluator proof tests. Ignored local configuration, secrets, EPUBs, runtime data, and approved specifications remain forbidden.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [API summary/genre/recommendation inventory rows](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Summary, genre, and recommendation pass operation/output/authorization/cancellation checks without request-level provider overrides or HTTP fallback.

## Required tests and evidence

Run focused non-chat generated-client tests and API Compose proof; record exact commands and redacted results.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs. Redact credentials, local configuration, private EPUB text, prompts, and evidence excerpts.

- **Implementation / merged PR / SHA:** 2026-10-26 — Added `tests/answer/test_r2_api_non_chat_grpc.py`; uncommitted pending senior review and root packaging. Commit SHA and PR pending.
- **Discarded implementation:** 2026-10-26 — Discarded the uncommitted `tests/answer/test_r2_api_non_chat_grpc.py` proof after its required clean-checkout Compose evidence failed. No source or test implementation from this task is eligible for packaging; the focused test result below is discovery evidence only.
- **Commands and results:** 2026-10-26 — `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test ruff check tests/answer/test_r2_api_non_chat_grpc.py` — passed. `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_r2_api_non_chat_grpc tests.answer.test_grpc_generation tests.api.test_r2_chat` — 23 tests passed. `python3 scripts/check_task_ledger.py` — fresh; `git diff --check` — passed. `env VERIFY_PROJECT=librarian-ad-m03-15 ANSWER_DELIVERY_REPORT_DIR=/private/tmp/librarian-ad-m03-15-reports scripts/run_answer_delivery_compose.sh` from a clean detached worktree at `d9287da165ed1d36303b73f9331a63f53ac64f5a` — failed before service startup because config-resolver reported missing `/config/librarian.json`.
- **Reports / screenshots:** No report produced. The harness removed its disposable runtime state and retained no report after the pre-start failure.
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** 2026-10-26 — **Blocked on `AD-M03-04` harness repair.** Its script activates `codex-broker`, `workers`, `metadata-workers`, and `evaluation` profiles but omits the `config-resolver` profile. As a result, its direct config-resolver run does not receive the tracked answer-delivery overlay and reads a missing ignored local config file. Rendering with the missing profile enabled confirms the tracked fixture mount is otherwise correct. Reopen after the harness includes the config-resolver profile, produces all four redacted reports from a clean checkout, and the focused proof still passes. The proof runs the actual API composition seam with an authenticated generated stub and a live in-process gRPC listener. Test-local workload functions stand in only for unrelated storage/search work while invoking the real injected synchronous generator; there is no HTTP provider or legacy generator in the fixture.
- **Blockers / decisions:** 2026-10-26 — **Resolved to planned.** [AD-M03-20](20-compose-harness-config-resolver-profile.md) merged in [PR #115](https://github.com/JonathanGWesterfield/Librarian/pull/115), adding the missing config-resolver profile without changing the four reported caller profiles. The clean-checkout harness and non-chat proof are now eligible for a new isolated claim; their required redacted reports remain unproduced.
- **Blockers / decisions:** 2026-10-26 — **Blocked again by a later bootstrap failure.** After #115, the fresh canonical harness at `39644a32d4be28b07cea55d380b85a3ab7e98e03` fails before startup because API declares a dependency on undefined `codex-broker`. The earlier resolver-profile defect is resolved, but this task cannot produce its required clean Compose evidence until the current-main harness bootstrap failure is repaired and rerun.

- **2026-10-26 — Repair handoff pending merge:** AD-M03-21 / [PR #120](https://github.com/JonathanGWesterfield/Librarian/pull/120) fixes the dependency-profile bootstrap failure and passed the clean canonical all-profile harness at `a14cd70c1f99ec4151559553082a290fca98c3ce`. This task stays blocked until that repair merges; then a new owner may claim the discarded non-chat proof, implement it, and rerun its required checks. The maintenance run does not supply the missing focused non-chat implementation.

## Handoff

Before review, record exact paths, commands/results, SHA, and PR. Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with a precise reopening condition. A merged task changes the roadmap and #87 only when it changes milestone eligibility, blocker, or next work.
