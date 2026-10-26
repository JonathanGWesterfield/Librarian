# M03 · Summary-worker R2 migration

- **Task ID:** `AD-M03-11`
- **Milestone:** [M03](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Migrate summary-worker durable-job execution to a process-lifetime generated client for chapter and book summary operations.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Summary-worker inventory row](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Configuration and Compose migration](../../../answer-delivery/compatibility-and-migration.md#configuration-and-compose-migration)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)

## Acceptance criteria

Shutdown cancels active RPC, leaves job recoverable, and no legacy HTTP generator is instantiated.

## Required tests and evidence

Run summary-worker operation, shutdown, and profile tests.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** Merged implementation provenance is the roadmap’s documented [PR #104–#111 range](https://github.com/JonathanGWesterfield/Librarian/pulls?q=is%3Apr+is%3Aclosed+104+105+106+107+108+109+110+111); exact slice-to-PR mapping was not retained and must not be inferred.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

`AD-M03-02` and `AD-M03-04` require fresh profile proof.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
