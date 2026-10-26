# M07 · Independent review and full local gate

- **Milestone:** [M07 — Compatibility, failure, Chrome UAT, and independent review](README.md)
- **Task ID:** `AD-M07-04`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Independently inspect design conformance and live evidence after UAT, then run the full required check.

**Goal:** Independent review and full local gate. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M07-03](03-chrome-uat-both-modes.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** No source files; only this task’s independent review finding log and `/tmp/librarian-m07-review/` redacted report.
- **Forbidden paths:** All implementation source until a separate repair task is claimed; private UAT corpus/configuration, secrets, EPUBs, and runtime data.

## Parallel safety and reserved surfaces

No source ownership; reviewer reports findings in this task and implementers address them in separate linked tasks. This is strictly synchronous.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M07 independent-review requirement](../../../answer-delivery/README.md#m07-compatibility-failure-chrome-uat-and-independent-review)
- [Release evidence](../../../answer-delivery/README.md#release-evidence)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)
- [Timing and report format](../../../answer-delivery/acceptance.md#timing-and-report-format)

## Acceptance criteria

Reviewer confirms lifecycle, transport, security, evidence policy, and UAT evidence; `scripts/check.sh` passes after findings are resolved.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run independent review, then the full local gate; do not reverse the required order.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

This is the M07 completion/release gate and input to M08–M10.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
