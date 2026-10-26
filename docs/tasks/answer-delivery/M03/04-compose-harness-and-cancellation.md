# M03 · Run fail-closed Compose harness and live cancellation

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-04`
- **Lifecycle status:** **planned**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Run the checked-in R2 Compose harness against all profiles and prove real child process-group cancellation/reaping.

**Goal:** Run fail-closed Compose harness and live cancellation. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-02](02-all-caller-grpc-proof.md), [AD-M03-03](03-compose-isolation-and-handshake-proof.md), [AD-M03-15](15-api-non-chat-compose-proof.md), [AD-M03-16](16-summary-worker-compose-proof.md), [AD-M03-17](17-metadata-worker-compose-proof.md), and [AD-M03-18](18-evaluator-compose-proof.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `sequential acceptance/release`.
- **Exclusive owned paths:** `scripts/run_answer_delivery_compose.sh`, `scripts/validate_answer_delivery_compose_reports.py`, `tests/e2e/test_answer_delivery_compose_script.py`, and `/tmp/librarian-answer-delivery-r2/` reports.
- **Forbidden paths:** Caller adapter code/tests, `docker-compose.r2.yml`, browser/API delivery code, production local configuration, secrets, EPUBs, and runtime data.

## Parallel safety and reserved surfaces

Reserve harness scripts, report schemas, and R2 Compose fixture config. Avoid editing production local config.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Admission, execution, cancellation, and shutdown](../../../answer-delivery/technical-design.md#admission-execution-cancellation-and-shutdown)
- [Atomic deployment and rollback](../../../answer-delivery/compatibility-and-migration.md#atomic-deployment-and-rollback)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Harness fails closed; four redacted reports are emitted; live `Generate` cancellation reaps parent and child process group.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run `scripts/run_answer_delivery_compose.sh` with isolated `VERIFY_PROJECT` and validate report schemas.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet. Store only redacted report paths, SHA, image IDs, and command result in this task.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required evidence for M03 exit; hand reports to M07 UAT/review.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
