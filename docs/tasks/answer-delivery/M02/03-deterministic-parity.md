# M02 · Deterministic parity matrix

- **Task ID:** `AD-M02-03`
- **Milestone:** [M02](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Keep a dedicated deterministic matrix proving old and extracted in-process answer paths produce equivalent terminal semantics.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M02-01](01-runtime-ports-and-evidence-snapshot.md) and [AD-M02-02](02-facade-adapters-and-parity-matrix.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M02 exit condition](../../../answer-delivery/README.md#m02-in-process-answer-runtime-extraction-and-parity)
- [Evidence snapshot](../../../answer-delivery/technical-design.md#evidence-snapshot)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)

## Acceptance criteria

Point, bounded, broad, refusal, source-change, and repair fixtures preserve result and citation/refusal semantics.

## Required tests and evidence

Run focused parity matrix without Docker/private corpus.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** [PR #103](https://github.com/JonathanGWesterfield/Librarian/pull/103).
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M03 must reuse this matrix when substituting broker adapters.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
