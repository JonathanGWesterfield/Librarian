# M05 · Validate delivery-mode configuration

- **Milestone:** [M05 — Configuration, capabilities, and feature off-switch](README.md)
- **Task ID:** `AD-M05-01`
- **Lifecycle status:** **in review**
- **Milestone status:** Parallel configuration implementation in progress; M04 acceptance and M03 exit still gate acceptance/release. Task status never advances milestone status.
- **Claim record:** owner: **/root/implementer**; branch/worktree: **`codex/ad-m05-01-delivery-config`** / **`/Users/codexai/Documents/Librarian-worktrees/ad-m05-01`**; claimed timestamp: **2026-10-26 21:16:16 CET**; last update: **2026-10-26 21:24:04 CET**; coordination contact: **/root**. Claimed before edits; lifecycle advanced `planned → claimed → in progress` at the same verified timestamp.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Add `chat.delivery_mode` with buffered default and progressive opt-in, without changing evidence policy or broker transport.

**Goal:** Validate delivery-mode configuration. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M04-01](../M04/01-api-event-delivery-adapter.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `packages/librarian_config/config.py`, `config/librarian.base.json`, `tests/config/test_chat_delivery_mode.py`, and `tests/config/__init__.py` (bounded discovery support).
- **Bounded shared reservation:** `scripts/resolve_provider_config.py` and `packages/librarian_contracts/runtime_config.py`, coordinated with AD-M05-02. This task serializes the validated non-secret mode only into the generated `r2_api` document and permits that API-only optional field through the strict R2 client preflight; it does not alter API composition, browser behavior, broker, or Compose topology.
- **Forbidden paths:** API routes/composition, browser UI, public event schema, broker/Compose topology, local configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve configuration schema/defaults and configuration tests. Coordinate config changes with task 02.

AD-M05-01 holds the bounded resolver and R2 client-preflight reservations above while AD-M05-02 remains planned. The shared boundary is recorded in both task files before implementation.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M05 delivery-mode requirement](../../../answer-delivery/README.md#m05-configuration-capabilities-and-off-switch)
- [Goals and non-goals](../../../answer-delivery/technical-design.md#goals-and-non-goals)
- [Compatibility promise](../../../answer-delivery/compatibility-and-migration.md#compatibility-promise)
- [Public event evolution](../../../answer-delivery/compatibility-and-migration.md#public-event-evolution)

## Acceptance criteria

Invalid/incompatible values fail before work; default is buffered; progressive is explicit.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run configuration parsing, default, invalid-value, and pre-admission tests.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** 2026-10-26 21:16:16 CET — claimed by `/root/implementer` on `codex/ad-m05-01-delivery-config`; implementation started after the claim. Reserved `packages/librarian_config/config.py`, `config/librarian.base.json`, `tests/config/test_chat_delivery_mode.py`, `tests/config/__init__.py` for canonical discovery, and the bounded AD-M05-02-coordinated resolver/client-preflight surfaces `scripts/resolve_provider_config.py` and `packages/librarian_contracts/runtime_config.py`.
- **Commands and results:** 2026-10-26 21:16:16 CET — inspected the worktree diff, task/design anchors, configuration parser, base document, resolver, and existing provider configuration tests. The worktree had coordinator-owned roadmap/task/freshness changes associated with the merged M03 work; they remain outside this task's implementation ownership. 2026-10-26 21:20:39 CET — `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh tests.config.test_chat_delivery_mode tests.ingestion.test_provider_config tests.contracts.test_broker_runtime_config` passed 33 tests; `ruff check --ignore RUF034 packages/librarian_config/config.py packages/librarian_contracts/runtime_config.py scripts/resolve_provider_config.py tests/config/test_chat_delivery_mode.py` and `git diff --check` passed on the working tree based at `d2f7c37df61b5a9607f37fbd2ac4de5e40ca40c5`. 2026-10-26 21:23:31 CET — after the final strictness repair, the same focused command passed 33 tests; canonical discovery `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh` passed 522 tests with local loopback permission. The ignored `RUF034` is the unchanged pre-existing `config.py` line 568 finding.
- **Reports / screenshots:** Full gate log `/tmp/librarian-ad-m05-01-check.log`. Configuration-only change; no endpoint or browser behavior is activated by this slice.
- **Review findings and repairs:** 2026-10-26 21:16:16 CET — initial reviewer required the generated R2 API document to retain the mode and parse it under version-2 validation. The reviewer initially requested a `disabled` value, then corrected that after rereading the compatibility plan: `buffered` and `progressive` remain the only values; buffered is the events-off mode. The first resolver round-trip exposed the strict R2 client preflight rejecting `chat`; coordinator authorized the bounded API-only `packages/librarian_contracts/runtime_config.py` reservation. The repair keeps worker/evaluator schemas exact and validates a v1 → generated `r2_api` → client preflight → parser round trip. 2026-10-26 21:23:31 CET — reviewer found the application parser accepted explicit `chat: {}` while the strict R2 preflight rejected it. Repaired so only an absent section defaults buffered; an explicit section must contain exactly `delivery_mode`. Added the direct preflight rejection for `disabled` and reran focused plus canonical tests.
- **Review findings and repairs:** 2026-10-26 21:24:04 CET — senior reviewer independently approved the repaired slice after rerunning the 33-test focused config/provider/contract group, freshness, changed-file lint (with only the documented unchanged `RUF034`), and diff check. The task remains in progress pending coordinator full-gate evidence.
- **Blockers / decisions:** Awaiting merge of [PR #123](https://github.com/JonathanGWesterfield/Librarian/pull/123). M03/M04 acceptance and release gates remain; AD-M05-02 owns API admission.

- **2026-10-26 — Full gate and review handoff:** root ran `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` after independent code approval: all checks and 522 tests passed (log above). Implementation snapshot `6c40ff8` contains the tested code; subsequent changes are documentation/evidence and the PR link only. PR #123 packages this slice; task moves to `in review`, not complete, until merge.

- **2026-10-26 — Final approval:** `/root/reviewer` approved implementation snapshot `6c40ff8` and the final PR/evidence updates after the 522-test gate, with no blocking or important findings. Task remains `in review` until PR #123 merges.

## Handoff

Task 02 composes the validated mode into API admission. Buffered disables only new event delivery; task 02 owns the endpoint behavior and has not been implemented by this configuration slice.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
