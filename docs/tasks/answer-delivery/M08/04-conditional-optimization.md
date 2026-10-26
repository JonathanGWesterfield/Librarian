# M08 · Conditional broker optimization

- **Task ID:** `AD-M08-04`
- **Milestone:** [M08](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Implement only the bottleneck-targeted change selected by measured baseline and decision review.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M08-03](03-optimization-decision-report.md) complete and selects a change.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths/surfaces:** Selected broker/provider paths and matched benchmark fixture, recorded before edits.
- **Forbidden paths/surfaces:** Contracts, lifecycle, credential policy, and unrelated latency architecture.; all active-task owned production files; approved design specifications; ignored local configuration, secrets, EPUBs, and runtime data.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M08 optimization constraint](../../../answer-delivery/README.md#m08-measured-broker-optimization)
- [Admission, execution, cancellation, and shutdown](../../../answer-delivery/technical-design.md#admission-execution-cancellation-and-shutdown)
- [Security, observability, and deployment](../../../answer-delivery/technical-design.md#security-observability-and-deployment)
- [Timing and report format](../../../answer-delivery/acceptance.md#timing-and-report-format)

## Acceptance criteria

Correctness/cancellation/security retain M07 evidence; comparable before/after data supports ship or no-go.

## Required tests and evidence

Run contract/cancellation suite and identical benchmark protocol.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Hand data to `AD-M08-05`; never treat an unmeasured change as an optimization.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
