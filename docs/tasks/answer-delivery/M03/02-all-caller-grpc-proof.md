# M03 · Prove API chat uses generated gRPC

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-02`
- **Lifecycle status:** **in review**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **`/root`**; branch/worktree: **`codex/m03-api-chat-generated-proof` in the shared Librarian worktree**; claimed timestamp: **2026-10-26T13:32:00-05:00**; last update: **2026-10-26T13:45:00-05:00**; coordination contact: **`/root` via this task record**. Reserved paths: **`tests/answer/test_grpc_chat.py`** and this task record. [AD-M03-19](19-api-chat-cancellation-terminal-event.md) released the test surface after its merge.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Exercise API chat synthesis, semantic selection, and support review through the API principal’s generated stub. This task owns only chat proof; caller-specific proof lives in `AD-M03-15` through `AD-M03-18`.

**Goal:** Prove API chat uses generated gRPC. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-09](09-api-chat-migration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `tests/answer/test_grpc_chat.py` only.
- **Forbidden paths:** `apps/api/librarian_api/r2_chat.py`, `packages/librarian_answer_adapters/grpc_chat.py`, `tests/answer/test_grpc_generation.py`, and all worker/evaluator proof tests. Ignored local configuration, secrets, EPUBs, runtime data, and approved specifications remain forbidden.

## Parallel safety and reserved surfaces

Reserve API chat migration tests, chat Compose fixtures, and API generated-client assertions only. Do not edit worker, evaluator, or non-chat API tests.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M03 migration deliverable](../../../answer-delivery/README.md#m03-atomic-grpc-codex-broker-migration)
- [API chat inventory row](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)

## Acceptance criteria

API chat has a positive generated-client proof for synthesis, selection, and review; disconnect/deadline behavior has no hidden HTTP fallback.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run focused API chat generated-client, cancellation, and API Compose tests.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet. Attach exact test command, report path, SHA, and PR after execution.
- **Implementation/PR:** 2026-10-26 — Packaged in commit `c26e6bda126b8a168e0121584b9bec31fae258be`; [PR #118](https://github.com/JonathanGWesterfield/Librarian/pull/118) is in review. Keep this task `in review` until the PR merges.
- **Commands and results:** _Not recorded._
- **Commands and results:** 2026-10-26 — `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_grpc_chat tests.answer.test_runtime tests.answer.test_grpc_broker_adapter tests.answer.test_grpc_generation tests.api.test_r2_chat` — passed: **42 tests**. The new positive fixture runs `R2ApiChatCaller.run()` with a live authenticated `api` generated client and in-process generated gRPC broker; it observes semantic selection, grounded synthesis, and support review at the provider in order, each with its required v1 output contract and one body-text evidence snapshot. The retained live cancellation cases cover disconnect, explicit cancellation, deadline, and unrelated-task cancellation. Test image: `librarian-grpc-chat-test` (Python 3.12; image ID previously recorded in AD-M03-19).
- **Commands and results:** 2026-10-26 — `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test ruff check tests/answer/test_grpc_chat.py` — passed. `git diff --check && python3 scripts/check_task_ledger.py` — passed; task ledger reports 64 fresh task files. Baseline Git SHA: `81e72fa8192e8ab217a4de9cba4bf7478e370619`.
- **Commands and results:** 2026-10-26 — Senior reviewer independently repeated the 42-test focused runtime/gRPC/API-chat suite, changed-path Ruff, diff check, and task-ledger check; all passed. The static HTTP-retirement and boundary-inventory suite also passed: 5 tests. The broader R2 Compose/Chrome evidence remains unavailable until its documented current-main bootstrap blocker is repaired; no Compose report is claimed for this proof task.
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Review findings and repairs:** 2026-10-26 — Senior code/design review passed. The proof drives `R2ApiChatCaller.run()` through an authenticated generated `api` client and real in-process broker, stubbing only retrieval and source persistence. It observes selection, synthesis, and support review in order with the required v1 output contracts, body-text snapshots, and accepted lifecycle; retained live cancellation cases still pass. Retain `in review` until the PR merges.
- **Blockers / decisions:** 2026-10-26 — **Blocked.** A live authenticated `api` generated-client integration fixture reached the broker for grounded synthesis, then a parent cancellation caused the in-flight gRPC await to raise `asyncio.CancelledError` out of `AnswerRuntime.run()` after `generation_started`. This contradicts the acceptance charter requirement for exactly one terminal `cancelled` event with no late completion. The proof-only task cannot edit `packages/librarian_answer/runtime.py` or the generated-client adapter. [AD-M03-19](19-api-chat-cancellation-terminal-event.md) is the required repair task and owns the released chat proof surface; reopen this proof after it makes in-flight generated RPC cancellation yield that terminal event and its live regression passes. Focused Python 3.12 container command (before removing the contradictory test): `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_grpc_chat` — **9 tests passed**, but the passing cancellation assertion accepted the contradicted behavior and was removed.
- **Blockers / decisions:** 2026-10-26 — **Resolved.** [AD-M03-19](19-api-chat-cancellation-terminal-event.md) merged in [PR #117](https://github.com/JonathanGWesterfield/Librarian/pull/117), including the live cancellation regression. This proof is now in progress to assert API-principal generated-stub coverage for synthesis, semantic selection, and support review without an HTTP fallback. Full Compose evidence remains a later M03 acceptance gate and does not expand this focused proof task.

## Handoff

Blocks `AD-M03-04`, `AD-M03-05`, and `AD-M03-06`. The **answer-runtime owner** must claim [AD-M03-19](19-api-chat-cancellation-terminal-event.md), repair the terminal cancellation contract, and then return live evidence here before this proof is reopened.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
