# M10 · Progressive-default decision

- **Task ID:** `AD-M10-04`
- **Milestone:** [M10](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Decide whether progressive delivery becomes default only after opt-in rollout, UAT, timing, and recovery evidence.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M10-03](03-final-uat-and-handoff.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths/surfaces:** Decision record, configuration default, release notes if approved.
- **Forbidden paths/surfaces:** Evidence policy, broker transport, task ledger history, and unreviewed UI work.; all active-task owned production files; approved design specifications; ignored local configuration, secrets, EPUBs, and runtime data.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M10 rollout requirement](../../../answer-delivery/README.md#m10-controlled-rollout-and-operational-handoff)
- [Compatibility promise](../../../answer-delivery/compatibility-and-migration.md#compatibility-promise)
- [Public event evolution](../../../answer-delivery/compatibility-and-migration.md#public-event-evolution)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

Decision is evidence-backed; buffered rollback remains documented and no default change hides timing/correctness misses.

## Required tests and evidence

Review final UAT/timing/runbook evidence and run focused config/default tests if changed.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Close or extend roadmap handoff with #87 evidence.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
