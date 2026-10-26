# M03 · Execute atomic R2 cutover and rollback proof

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-06`
- **Lifecycle status:** **planned**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Use the documented preflight, activation, smoke, and rollback workflows against a disposable/local stack without exposing secrets.

**Goal:** Execute atomic R2 cutover and rollback proof. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M03-02](02-all-caller-grpc-proof.md), [AD-M03-03](03-compose-isolation-and-handshake-proof.md), [AD-M03-04](04-compose-harness-and-cancellation.md), and [AD-M03-05](05-http-retirement-proof.md) complete; Docker and approved local credentials available.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** `scripts/prepare_r2_cutover.py`, `scripts/deploy_r2_cutover.py`, their focused tests, and `/tmp/librarian-r2-cutover/` redacted evidence.
- **Forbidden paths:** Broker/API/worker implementation modules, Compose topology, browser UI, production local configuration, secrets, EPUBs, and runtime data.

## Parallel safety and reserved surfaces

Reserve cutover scripts, tracked synthetic config, and isolated Compose project/report directory. This is a synchronous release gate.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M03 exit condition](../../../answer-delivery/README.md#m03-atomic-grpc-codex-broker-migration)
- [ADR health and readiness](../../../answer-delivery/adr-internal-rpc-transport.md#health-and-readiness)
- [Atomic deployment and rollback](../../../answer-delivery/compatibility-and-migration.md#atomic-deployment-and-rollback)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Preflight produces owner-only snapshot; activation admits only after readiness/smokes; an induced failure restores complete R0 baseline without mixing R0/R2.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run deterministic preflight/cutover/rollback workflow and retain redacted evidence.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet. Environment availability must be recorded rather than simulated.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

This is the M03 release gate and gates M04 acceptance/release.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
