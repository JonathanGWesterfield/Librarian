# M04 · M04 delivery acceptance and release evidence

- **Milestone:** [M04 — Buffered JSON and progressive SSE delivery adapters](README.md)
- **Task ID:** `AD-M04-02`
- **Lifecycle status:** **blocked**
- **Milestone status:** In progress in parallel with M03. Task status never advances milestone status.
- **Claim record:** **Blocked / non-claimable.** The exact reopening condition below controls; do not reserve paths or start edits until it is met.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Non-claimable condition

**Non-claimable while blocked.** Current blocker: [AD-M03-06](../M03/06-atomic-cutover-and-rollback-live-proof.md) must be `complete` with redacted live cutover/rollback evidence. Reopening trigger: that task’s merged PR/evidence is linked in #87 and [AD-M04-01](01-api-event-delivery-adapter.md) remains complete. Executor on reopening: API delivery/integration owner. Successor: `AD-M05-01` and `AD-M06-01`.

## Immutable scope and goal

Run final delivery acceptance once M03 atomic release evidence exists.

**Goal:** M04 delivery acceptance and release evidence. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M03-06](../M03/06-atomic-cutover-and-rollback-live-proof.md) complete with live cutover/rollback evidence and [AD-M04-01](01-api-event-delivery-adapter.md) merged.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `non-claimable conditional task`.
- **Exclusive owned paths:** none while blocked; the named reopening executor reserves only the paths specified in a new claim record.
- **Forbidden paths:** all implementation, test, and configuration paths until the recorded reopening trigger is satisfied.

## Parallel safety and reserved surfaces

Reserve no source files by default; reserve a redacted report directory while executing. This is a synchronous acceptance/release gate.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M04 exit condition](../../../answer-delivery/README.md#m04-buffered-json-and-progressive-sse-delivery-adapters)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Local Chrome UAT](../../../answer-delivery/acceptance.md#local-chrome-uat)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

Fixtures prove terminal parity, frame decoding, one terminal, no draft prose, disconnect propagation, and candidate progress during blocked generation.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run deterministic API fixtures, Compose harness dependency, Chrome evidence where M07 requires it, and full relevant suite.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Blocked on M03 exit; do not change to complete based only on PR #112.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Pass redacted evidence and known blockers to M05/M06/M07.

This blocked record is non-claimable. Only the named executor may claim it after the recorded reopening trigger is met; preserve its blocker and decision evidence in the append-only log.
