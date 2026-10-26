# M03 · Complete HTTP retirement proof

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-05`
- **Lifecycle status:** **complete**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Verify removal of every retired owned HTTP broker listener/client path and preserve no fallback/mixed-stack guard.

**Goal:** Complete HTTP retirement proof. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M03-02](02-all-caller-grpc-proof.md) and [AD-M03-04](04-compose-harness-and-cancellation.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Parallel safety and reserved surfaces

Reserve retired-target scans and broker transport tests; coordinate any deletion with callers proven in task 02.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [ADR boundary policy](../../../answer-delivery/adr-internal-rpc-transport.md#boundary-policy)
- [ADR amendment rule](../../../answer-delivery/adr-internal-rpc-transport.md#amendment-rule)
- [HTTP retirement proof](../../../answer-delivery/compatibility-and-migration.md#http-retirement-proof)
- [M03 exit condition](../../../answer-delivery/README.md#m03-atomic-grpc-codex-broker-migration)

## Acceptance criteria

Repository scan has no owned HTTP broker target; broker has no HTTP route/host port; host and config guards reject legacy path.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run static scan, broker transport tests, rendered Compose assertions, and host guard suite.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Merged source changes and recorded implementation evidence: [PR #112](https://github.com/JonathanGWesterfield/Librarian/pull/112). The milestone still needs the separate live Compose/cutover evidence in `AD-M03-04` and `AD-M03-06`.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required before M03 exit. Do not delete rollback artifacts or declare M03 complete from a scan alone.

This archived record is not claimable. Open a new follow-up task or record an approved reopening decision with issue/PR evidence; do not rewrite its historical claim or completion evidence.
