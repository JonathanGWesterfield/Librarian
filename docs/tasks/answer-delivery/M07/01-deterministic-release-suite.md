# M07 · Deterministic release suite evidence

- **Milestone:** [M07 — Compatibility, failure, Chrome UAT, and independent review](README.md)
- **Task ID:** `AD-M07-01`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Run contract, parity, cancellation, API, browser-contract, and migration fixtures from a clean checkout.

**Goal:** Deterministic release suite evidence. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M03-06](../M03/06-atomic-cutover-and-rollback-live-proof.md), [AD-M05-03](../M05/03-mode-parity-and-off-switch-integration.md), and [AD-M06-04](../M06/04-web-failure-and-accessibility-integration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** No source files; only `/tmp/librarian-m07-deterministic/` command logs and redacted summary.
- **Forbidden paths:** All production and test source, private UAT corpus/configuration, secrets, EPUBs, and runtime data.

## Parallel safety and reserved surfaces

Reserve no product source; reserve a uniquely named report directory. Parallel-safe with task 02.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M07 deterministic-suite requirement](../../../answer-delivery/README.md#m07-compatibility-failure-chrome-uat-and-independent-review)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

All tracked fixture cases pass with no Docker, private books, credentials, or model where charter requires.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run the charter deterministic command and record exact command, SHA, result, and failures.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required before Chrome UAT and independent review.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
