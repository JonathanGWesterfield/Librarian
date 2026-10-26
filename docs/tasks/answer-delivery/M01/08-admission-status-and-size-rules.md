# M01 · Reusable admission, size, and status rules

- **Milestone:** [M01 — Contracts, toolchain, inventory, and fixtures](README.md)
- **Task ID:** `AD-M01-08`
- **Lifecycle status:** **complete**
- **Milestone status:** Complete. Task status never advances milestone status.
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Implement v1 operation/output validation, size limits, and non-OK status/detail mapping as reusable contract code.

**Goal:** Reusable admission, size, and status rules. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-01](01-proto-and-python-bindings.md) and [AD-M01-04](04-synthetic-fixture-bank.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Parallel safety and reserved surfaces

Reserve shared contract validation modules. Parallel-safe with config work; coordinate public error changes.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [v1 gRPC contract](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Validation, size limits, and status mapping](../../../answer-delivery/technical-design.md#validation-size-limits-and-status-mapping)
- [Admission, execution, cancellation, and shutdown](../../../answer-delivery/technical-design.md#admission-execution-cancellation-and-shutdown)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)

## Acceptance criteria

Invalid enum, mismatch, or oversize input fails before queue admission with specified mapping.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run contract validation and status mapping fixtures.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Historical evidence: [PR #98](https://github.com/JonathanGWesterfield/Librarian/pull/98).
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M03 broker must call this code before scheduling provider work.

This archived record is not claimable. Open a new follow-up task or record an approved reopening decision with issue/PR evidence; do not rewrite its historical claim or completion evidence.
