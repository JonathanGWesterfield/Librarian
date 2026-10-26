# M07 · Chrome UAT through React and Compose/nginx

- **Milestone:** [M07 — Compatibility, failure, Chrome UAT, and independent review](README.md)
- **Task ID:** `AD-M07-03`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Execute the acceptance charter using the actual React UI in buffered and progressive modes with private local corpus kept out of Git.

**Goal:** Chrome UAT through React and Compose/nginx. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M07-02](02-compose-failure-and-migration-suite.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** No source files; only ignored local UAT configuration and `/tmp/librarian-m07-chrome-uat/` redacted report.
- **Forbidden paths:** All production/test source, task-ledger protocol, private EPUB text, secrets, and local configuration committed to Git.

## Parallel safety and reserved surfaces

Reserve ignored local UAT configuration and one redacted report directory. This is synchronous with a stable release candidate.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M07 Chrome-UAT requirement](../../../answer-delivery/README.md#m07-compatibility-failure-chrome-uat-and-independent-review)
- [Local Chrome UAT](../../../answer-delivery/acceptance.md#local-chrome-uat)
- [Timing and report format](../../../answer-delivery/acceptance.md#timing-and-report-format)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

All question classes, progress, Stop, failures, citations, and timing observations meet the charter or are explicitly reported as misses/blockers.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Use Chrome via extension only; collect required five cold/twenty warm observations when measuring release candidate.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet. Never include EPUB text, secrets, or local config in the task file.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

UAT must finish before task 04 independent review.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
