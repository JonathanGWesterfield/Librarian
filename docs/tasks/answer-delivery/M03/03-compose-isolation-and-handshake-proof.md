# M03 · Prove R2 isolation and compatibility handshake

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-03`
- **Lifecycle status:** **planned**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Validate role-specific secrets, private broker networks, broker-only egress, sanitized mounts, authenticated Health, and compatibility admission.

**Goal:** Prove R2 isolation and compatibility handshake. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-10](../M01/10-sanitized-runtime-config.md) and [AD-M01-13](../M01/13-compose-topology-policy.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `docker-compose.r2.yml`, `tests/e2e/test_answer_delivery_compose_script.py`, and `tests/fixtures/answer_delivery/r2-compose/` topology assertions.
- **Forbidden paths:** All caller adapter modules and tests; cutover scripts; browser/API delivery code; ignored local config/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve `docker-compose.r2.yml`, topology assertions, and Compose security fixtures. Coordinate all Compose changes through one claimant.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Atomic compatibility handshake](../../../answer-delivery/technical-design.md#atomic-compatibility-handshake)
- [ADR local-Compose trust model](../../../answer-delivery/adr-internal-rpc-transport.md#local-compose-trust-model)
- [Configuration and Compose migration](../../../answer-delivery/compatibility-and-migration.md#configuration-and-compose-migration)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)

## Acceptance criteria

Each principal has only its permitted secret/network; health cannot Generate; mismatched SHA/major/minor/descriptor fail before admission.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run all-profile rendered Compose and in-container isolation/handshake suite.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet. Attach redacted `authorization.json` and `compatibility.json` evidence when run.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required before M03 exit and M04/M05 release claims.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
