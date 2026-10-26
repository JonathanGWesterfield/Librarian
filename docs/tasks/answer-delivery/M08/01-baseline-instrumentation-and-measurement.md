# M08 · Broker timing instrumentation and baseline

- **Milestone:** [M08 — Measured broker optimization](README.md)
- **Task ID:** `AD-M08-01`
- **Lifecycle status:** **planned**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Measure connection, queue, broker execution, provider work, review, repair, and terminal completion by query class.

**Goal:** Broker timing instrumentation and baseline. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M03-06](../M03/06-atomic-cutover-and-rollback-live-proof.md) and [AD-M07-05](../M07/05-full-local-gate.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `apps/codex_broker/librarian_broker/metrics.py`, `tests/broker/test_answer_delivery_metrics.py`, and `/tmp/librarian-m08-baseline/` redacted measurements.
- **Forbidden paths:** Broker scheduler/cancellation semantics, provider process integration, browser UI, benchmark decision report, local configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve timing instrumentation/metrics and benchmark report format. Coordinate request-ID fields with API.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M08 measurement requirement](../../../answer-delivery/README.md#m08-measured-broker-optimization)
- [Security, observability, and deployment](../../../answer-delivery/technical-design.md#security-observability-and-deployment)
- [Timing and report format](../../../answer-delivery/acceptance.md#timing-and-report-format)
- [ADR consequences](../../../answer-delivery/adr-internal-rpc-transport.md#consequences)

## Acceptance criteria

Measurements are monotonic, correlated, redacted, and separate lifecycle stages without changing completion definitions.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run reproducible benchmark harness; retain synthetic/redacted report and environment fingerprint.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Task 02 must use this baseline; issue [#86](https://github.com/JonathanGWesterfield/Librarian/issues/86) tracks optimization.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
