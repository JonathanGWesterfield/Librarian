# M09 · Evaluate separate runtime deployment

- **Milestone:** [M09 — Separate answer-runtime deployment decision](README.md)
- **Task ID:** `AD-M09-01`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Decide whether scale, isolation, ownership, or release evidence justifies an answer-runtime service.

**Goal:** Evaluate separate runtime deployment. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M07-05](../M07/05-full-local-gate.md) and [AD-M08-05](../M08/05-optimization-evidence.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** `docs/tasks/answer-delivery/M09/01-runtime-extraction-decision.md` append-only decision record and `/tmp/librarian-m09-decision/` redacted architecture review evidence.
- **Forbidden paths:** New runtime service, Compose network, API/browser contracts, broker behavior, local configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve decision record/ADR amendment only. This is a synchronous architecture gate.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M09 decision requirement](../../../answer-delivery/README.md#m09-decide-whether-to-deploy-the-answer-runtime-separately)
- [Components and dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction)
- [ADR decision](../../../answer-delivery/adr-internal-rpc-transport.md#decision)
- [ADR amendment rule](../../../answer-delivery/adr-internal-rpc-transport.md#amendment-rule)

## Acceptance criteria

Decision documents evidence, selected topology, trigger to revisit, and no unsupported latency claim.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Review M07/M08 reports and conduct architecture review.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet. Issue [#83](https://github.com/JonathanGWesterfield/Librarian/issues/83) tracks this decision.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

If rejected, close with trigger; if approved, unblock task 02.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
