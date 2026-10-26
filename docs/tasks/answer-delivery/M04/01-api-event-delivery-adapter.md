# M04 · Versioned API event-delivery adapter

- **Milestone:** [M04 — Buffered JSON and progressive SSE delivery adapters](README.md)
- **Task ID:** `AD-M04-01`
- **Lifecycle status:** **complete**
- **Milestone status:** In progress in parallel with M03. Task status never advances milestone status.
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Project the runtime iterator into v1 SSE events, collect that exact iterator for buffered `POST /chat`, and leave `/chat/stream` unchanged.

**Goal:** Versioned API event-delivery adapter. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M02-03](../M02/03-deterministic-parity.md) complete; M03 is an acceptance/release dependency only.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Parallel safety and reserved surfaces

Reserve API delivery adapter, serializer, API tests, `docs/api-endpoints.md`, and OpenAPI artifact. Coordinate endpoint edits.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M04 delivery-adapter deliverable](../../../answer-delivery/README.md#m04-buffered-json-and-progressive-sse-delivery-adapters)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Compatibility promise](../../../answer-delivery/compatibility-and-migration.md#compatibility-promise)
- [Public event evolution](../../../answer-delivery/compatibility-and-migration.md#public-event-evolution)

## Acceptance criteria

One event maps to one validated SSE envelope; full UTF-8 frame cap and lifecycle rules hold; buffered JSON has terminal parity.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run API serializer/route tests including transition, multibyte size, duplicate/terminal, cancellation, and JSON/SSE parity coverage.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Historical evidence: merged [PR #112](https://github.com/JonathanGWesterfield/Librarian/pull/112). This completion is implementation provenance, not M04 acceptance.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

[AD-M04-02](02-delivery-adapter-acceptance.md) consumes the adapter after [AD-M03-06](../M03/06-atomic-cutover-and-rollback-live-proof.md) completes.

This archived record is not claimable. Open a new follow-up task or record an approved reopening decision with issue/PR evidence; do not rewrite its historical claim or completion evidence.
