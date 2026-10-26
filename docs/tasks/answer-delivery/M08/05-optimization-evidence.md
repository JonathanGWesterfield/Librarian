# M08 · Optimization evidence and issue reconciliation

- **Task ID:** `AD-M08-05`
- **Milestone:** [M08](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Publish a reproducible evidence record and reconcile issue #86 without overstating latency results.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M08-04](04-conditional-optimization.md) complete, or [AD-M08-03](03-optimization-decision-report.md) records a reviewed no-go.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths/surfaces:** Redacted benchmark/report path and issue #86 update.
- **Forbidden paths/surfaces:** Production code except linked repair tasks; private prompt/provider data.; all active-task owned production files; approved design specifications; ignored local configuration, secrets, EPUBs, and runtime data.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M08 exit condition](../../../answer-delivery/README.md#m08-measured-broker-optimization)
- [Security, observability, and deployment](../../../answer-delivery/technical-design.md#security-observability-and-deployment)
- [Timing and report format](../../../answer-delivery/acceptance.md#timing-and-report-format)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

Evidence contains method, environment, baseline, results, limitations, and correctness checks.

## Required tests and evidence

Review report and rerun representative deterministic checks.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M09/M10 consume only this reviewed evidence.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
