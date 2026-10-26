# M02 · Thin legacy facades and deterministic parity

- **Milestone:** [M02 — In-process answer-runtime extraction and parity](README.md)
- **Task ID:** `AD-M02-02`
- **Lifecycle status:** **complete**
- **Milestone status:** Complete. Task status never advances milestone status.
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Keep API/CLI facades thin, preserve semantics, and enforce dependency direction with a deterministic parity matrix.

**Goal:** Thin legacy facades and deterministic parity. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M02-01](01-runtime-ports-and-evidence-snapshot.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Parallel safety and reserved surfaces

Reserve facade adapters and parity matrix tests. Synchronous only with runtime port changes.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M02 extraction/parity deliverable](../../../answer-delivery/README.md#m02-in-process-answer-runtime-extraction-and-parity)
- [Components and dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)

## Acceptance criteria

Old and new terminal results match across the required fixture classes; no broker/browser change is introduced.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run parity matrix and dependency-direction tests.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Historical evidence: [PR #103](https://github.com/JonathanGWesterfield/Librarian/pull/103).
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M03 starts from the reviewed runtime boundary.

This archived record is not claimable. Open a new follow-up task or record an approved reopening decision with issue/PR evidence; do not rewrite its historical claim or completion evidence.
