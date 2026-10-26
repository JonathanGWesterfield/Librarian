# M05 · Delivery-mode parity integration proof

- **Milestone:** [M05 — Configuration, capabilities, and feature off-switch](README.md)
- **Task ID:** `AD-M05-03`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Prove buffered and progressive modes execute the same gRPC broker/evidence policy and that disabled mode is safe.

**Goal:** Delivery-mode parity integration proof. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M05-01](01-delivery-mode-configuration.md) and [AD-M05-02](02-capabilities-and-pre-admission-off-switch.md) complete; M03 exit is acceptance/release prerequisite.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `tests/api/test_chat_delivery_mode_parity.py`, `tests/fixtures/answer_delivery/v1/`, and `/tmp/librarian-m05-mode-parity/` redacted reports.
- **Forbidden paths:** Configuration parser, API composition root, browser UI, broker/Compose topology, local configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve integration fixtures/reports only; coordinate shared test config with M07.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M05 exit condition](../../../answer-delivery/README.md#m05-configuration-capabilities-and-off-switch)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)
- [Release rule](../../../answer-delivery/acceptance.md#release-rule)

## Acceptance criteria

Both modes meet the same citation/refusal policy; progressive off-switch affects admission only.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run deterministic parity fixture suite and relevant Compose integration test.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required input to M06 and M07; attach commands/SHA/results.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
