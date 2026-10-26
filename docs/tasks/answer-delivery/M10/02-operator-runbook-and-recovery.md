# M10 · Operator recovery and lifecycle runbook

- **Milestone:** [M10 — Controlled rollout and operational handoff](README.md)
- **Task ID:** `AD-M10-02`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Publish recovery, gRPC health, secret rotation, cancellation, metric, and rollback instructions for the selected topology.

**Goal:** Operator recovery and lifecycle runbook. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M07-05](../M07/05-full-local-gate.md) and [AD-M09-01](../M09/01-runtime-extraction-decision.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `docs/answer-delivery/operator-runbook.md` and `/tmp/librarian-m10-runbook/` redacted dry-run evidence.
- **Forbidden paths:** Rollout configuration/defaults, browser UI, broker/runtime implementation, private configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve operator documentation and command verification artifacts. Parallel-safe with task 01 when interfaces are stable.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M10 operations requirement](../../../answer-delivery/README.md#m10-controlled-rollout-and-operational-handoff)
- [ADR local-Compose trust model](../../../answer-delivery/adr-internal-rpc-transport.md#local-compose-trust-model)
- [ADR health and readiness](../../../answer-delivery/adr-internal-rpc-transport.md#health-and-readiness)
- [Atomic deployment and rollback](../../../answer-delivery/compatibility-and-migration.md#atomic-deployment-and-rollback)

## Acceptance criteria

Instructions are executable, redacted, and distinguish delivery rollback from R2 rollback.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Dry-run documented commands against a disposable/local stack and peer-review runbook.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Task 03 validates this runbook during final handoff.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
