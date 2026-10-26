# M07 · Compose failure, isolation, and migration evidence

- **Milestone:** [M07 — Compatibility, failure, Chrome UAT, and independent review](README.md)
- **Task ID:** `AD-M07-02`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Exercise authorization, handshake, isolation, queue/deadline, cancellation, retirement, and migration cases across R2 profiles.

**Goal:** Compose failure, isolation, and migration evidence. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M07-01](01-deterministic-release-suite.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** No source files; only `/tmp/librarian-m07-compose/` redacted Compose reports.
- **Forbidden paths:** All production/test source, private UAT corpus/configuration, secrets, EPUBs, and runtime data.

## Parallel safety and reserved surfaces

Reserve isolated Compose project and report directory. Parallel-safe with task 01.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M07 failure/migration requirement](../../../answer-delivery/README.md#m07-compatibility-failure-chrome-uat-and-independent-review)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)
- [Atomic deployment and rollback](../../../answer-delivery/compatibility-and-migration.md#atomic-deployment-and-rollback)

## Acceptance criteria

Reports prove every caller/principal, security topology, process cleanup, and failed compatibility behavior.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run checked-in R2 Compose harness and validate all four redacted report schemas.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required before Chrome UAT; unavailable Docker/model is a blocker, not a pass.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
