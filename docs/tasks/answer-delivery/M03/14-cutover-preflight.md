# M03 · R2 cutover preflight automation

- **Task ID:** `AD-M03-14`
- **Milestone:** [M03](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Validate release cleanliness, all-profile topology, ignored role secrets, and owner-only backups before any stack modification.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-10](../M01/10-sanitized-runtime-config.md) and [AD-M01-13](../M01/13-compose-topology-policy.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [R2 local cutover preparation](../../../answer-delivery/README.md#r2-local-cutover-preparation)
- [Configuration and Compose migration](../../../answer-delivery/compatibility-and-migration.md#configuration-and-compose-migration)
- [Atomic deployment and rollback](../../../answer-delivery/compatibility-and-migration.md#atomic-deployment-and-rollback)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Preflight changes no services, validates prerequisites, and creates timestamped owner-only snapshot.

## Required tests and evidence

Run deterministic script tests with synthetic configuration.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** Merged implementation provenance is the roadmap’s documented [PR #104–#111 range](https://github.com/JonathanGWesterfield/Librarian/pulls?q=is%3Apr+is%3Aclosed+104+105+106+107+108+109+110+111); exact slice-to-PR mapping was not retained and must not be inferred.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

`AD-M03-06` consumes the snapshot for disruptive activation/rollback proof.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
