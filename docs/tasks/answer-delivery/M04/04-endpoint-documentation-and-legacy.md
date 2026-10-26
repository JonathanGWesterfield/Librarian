# M04 · Event endpoint documentation and legacy stream preservation

- **Task ID:** `AD-M04-04`
- **Milestone:** [M04](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Document browser endpoints and examples, update OpenAPI, and preserve existing `/chat/stream` framing.

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
- [Compatibility promise](../../../answer-delivery/compatibility-and-migration.md#compatibility-promise)
- [Public event evolution](../../../answer-delivery/compatibility-and-migration.md#public-event-evolution)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

Every FastAPI endpoint change is documented with request/response examples; legacy stream remains unchanged.

## Required tests and evidence

Run OpenAPI generation/parse and route compatibility tests.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** [PR #112](https://github.com/JonathanGWesterfield/Librarian/pull/112).
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M05 capability endpoint work must update these same docs under a new claim.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
