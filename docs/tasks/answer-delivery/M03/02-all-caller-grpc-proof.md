# M03 · Prove API chat uses generated gRPC

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-02`
- **Lifecycle status:** **blocked**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **`/root/m03_api_chat_implementer`**; branch/worktree: **`codex/m03-api-chat-grpc-proof` in the shared Librarian worktree**; claimed timestamp: **2026-10-26T10:50:44-05:00**; last update: **2026-10-26T10:54:18-05:00**; coordination contact: **`/root` via this task record**. The former `tests/answer/test_grpc_chat.py` reservation is released to [AD-M03-19](19-api-chat-cancellation-terminal-event.md); this blocked record now owns only its evidence.
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
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** 2026-10-26 — **Blocked.** A live authenticated `api` generated-client integration fixture reached the broker for grounded synthesis, then a parent cancellation caused the in-flight gRPC await to raise `asyncio.CancelledError` out of `AnswerRuntime.run()` after `generation_started`. This contradicts the acceptance charter requirement for exactly one terminal `cancelled` event with no late completion. The proof-only task cannot edit `packages/librarian_answer/runtime.py` or the generated-client adapter. [AD-M03-19](19-api-chat-cancellation-terminal-event.md) is the required repair task and owns the released chat proof surface; reopen this proof after it makes in-flight generated RPC cancellation yield that terminal event and its live regression passes. Focused Python 3.12 container command (before removing the contradictory test): `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_grpc_chat` — **9 tests passed**, but the passing cancellation assertion accepted the contradicted behavior and was removed.

## Handoff

Blocks `AD-M03-04`, `AD-M03-05`, and `AD-M03-06`. The **answer-runtime owner** must claim [AD-M03-19](19-api-chat-cancellation-terminal-event.md), repair the terminal cancellation contract, and then return live evidence here before this proof is reopened.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
