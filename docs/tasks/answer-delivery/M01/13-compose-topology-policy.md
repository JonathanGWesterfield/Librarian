# M01 · Executable Compose topology policy

- **Milestone:** [M01 — Contracts, toolchain, inventory, and fixtures](README.md)
- **Task ID:** `AD-M01-13`
- **Lifecycle status:** **complete**
- **Milestone status:** Complete. Task status never advances milestone status.
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Encode per-role secrets, private networks, broker-only egress, fixed config mounts, and normalized rendered paths as testable policy.

**Goal:** Executable Compose topology policy. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-10](10-sanitized-runtime-config.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Parallel safety and reserved surfaces

Reserve Compose topology assertions and synthetic test configuration. Coordinate Compose-file edits.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [ADR local-Compose trust model](../../../answer-delivery/adr-internal-rpc-transport.md#local-compose-trust-model)
- [Security, observability, and deployment](../../../answer-delivery/technical-design.md#security-observability-and-deployment)
- [Configuration and Compose migration](../../../answer-delivery/compatibility-and-migration.md#configuration-and-compose-migration)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)

## Acceptance criteria

Rendered configuration and assertions prove required mounts/networks and reject ancestor config mounts.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run topology policy tests and rendered-config assertions.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Merged milestone evidence: [PR #101](https://github.com/JonathanGWesterfield/Librarian/pull/101), which the roadmap records as M01 completion.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M03 Compose acceptance must exercise this policy live.

This archived record is not claimable. Open a new follow-up task or record an approved reopening decision with issue/PR evidence; do not rewrite its historical claim or completion evidence.
