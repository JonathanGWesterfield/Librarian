# M06 · Versioned SSE parser

- **Milestone:** [M06 — Web reducer and truthful progress UI](README.md)
- **Task ID:** `AD-M06-01`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Implement schema-aware SSE parsing that handles arbitrary UTF-8 boundaries, CRLF, IDs, and version/event validation.

**Goal:** Versioned SSE parser. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M04-01](../M04/01-api-event-delivery-adapter.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `apps/web/src/answer-delivery/sseDecoder.ts` and `apps/web/src/answer-delivery/sseDecoder.test.ts`.
- **Forbidden paths:** Reducer/state modules, UI components, API endpoints, event schema generator, broker/Compose topology, local configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve web transport/parser modules and parser tests. Parallel-safe with reducer if interface is agreed in this task file first.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M06 reducer requirement](../../../answer-delivery/README.md#m06-web-reducer-and-truthful-progress-ui)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Public event evolution](../../../answer-delivery/compatibility-and-migration.md#public-event-evolution)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)

## Acceptance criteria

Unknown event/type/version and malformed frames become controlled failures; parser never creates final prose from candidate data.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run parser fixtures for split UTF-8/CRLF, malformed frames, unknown versions/types, and early EOF.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Publish the parser input/output interface in artifacts before reducer work begins.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
