# M10 · Final UAT, evidence reconciliation, and handoff

- **Milestone:** [M10 — Controlled rollout and operational handoff](README.md)
- **Task ID:** `AD-M10-03`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Re-run Chrome UAT and timing samples before any default change, reconcile #74/#83/#86 and #87, and hand off operations.

**Goal:** Final UAT, evidence reconciliation, and handoff. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M10-01](01-progressive-opt-in-rollout.md) and [AD-M10-02](02-operator-runbook-and-recovery.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** No source files; only `/tmp/librarian-m10-handoff/` final redacted report and issue/roadmap links.
- **Forbidden paths:** All production/test source, operator runbook/default configuration, private UAT corpus/configuration, secrets, EPUBs, and runtime data.

## Parallel safety and reserved surfaces

Reserve final redacted report directory and issue updates. This is the final synchronous release gate.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M10 exit condition](../../../answer-delivery/README.md#m10-controlled-rollout-and-operational-handoff)
- [Local Chrome UAT](../../../answer-delivery/acceptance.md#local-chrome-uat)
- [Timing and report format](../../../answer-delivery/acceptance.md#timing-and-report-format)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

Operators can safely roll back delivery mode; #87 links final evidence without claiming unavailable tests as success.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run charter UAT, timing sample protocol, independent review, and full gate in required order.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Marks the answer-delivery roadmap handoff only after all evidence is linked.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
