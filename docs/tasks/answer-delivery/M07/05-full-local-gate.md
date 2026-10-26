# M07 · Full local gate after independent review

- **Task ID:** `AD-M07-05`
- **Milestone:** [M07](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Run the broad deterministic local check only after deterministic/Compose evidence, Chrome UAT, and independent review have completed.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M07-04](04-independent-review-and-full-gate.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths/surfaces:** No production files; uniquely named local logs/report directory.
- **Forbidden paths/surfaces:** Any source changes until reviewer findings are repaired; live private corpus/secrets.; all active-task owned production files; approved design specifications; ignored local configuration, secrets, EPUBs, and runtime data.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M07 exit condition](../../../answer-delivery/README.md#m07-compatibility-failure-chrome-uat-and-independent-review)
- [Release evidence](../../../answer-delivery/README.md#release-evidence)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

`scripts/check.sh` passes after independent review; failures are diagnosed as product, environment, or test issues without weakening checks.

## Required tests and evidence

Run `scripts/check.sh` and record command, SHA, result, and bounded failure diagnosis.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

This finalizes M07 evidence and unblocks M08/M09/M10.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
