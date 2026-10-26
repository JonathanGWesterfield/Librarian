# M04 · Buffered terminal parity adapter

- **Task ID:** `AD-M04-03`
- **Milestone:** [M04](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Collect the same runtime event iterator for buffered `POST /chat` so it cannot start a second generation.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M04-01](01-api-event-delivery-adapter.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M04 delivery-adapter deliverable](../../../answer-delivery/README.md#m04-buffered-json-and-progressive-sse-delivery-adapters)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Compatibility promise](../../../answer-delivery/compatibility-and-migration.md#compatibility-promise)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)

## Acceptance criteria

Buffered result has terminal parity with SSE and preserves grounding/refusal semantics.

## Required tests and evidence

Run JSON/SSE terminal parity and single-generation tests.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** [PR #112](https://github.com/JonathanGWesterfield/Librarian/pull/112).
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M04 final acceptance remains blocked by M03 cutover evidence.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
