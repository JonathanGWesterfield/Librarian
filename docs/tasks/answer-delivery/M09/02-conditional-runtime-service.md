# M09 · Conditional AnswerRuntime service implementation

- **Milestone:** [M09 — Separate answer-runtime deployment decision](README.md)
- **Task ID:** `AD-M09-02`
- **Lifecycle status:** **blocked**
- **Milestone status:** Not started. Task status never advances milestone status.
- **Claim record:** **Blocked / non-claimable.** The exact reopening condition below controls; do not reserve paths or start edits until it is met.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Non-claimable condition

**Non-claimable while blocked.** Current blocker: [AD-M09-01](01-runtime-extraction-decision.md) must be `complete` with reviewed approval, selected topology, and required ADR amendment. Reopening trigger: its merged decision evidence links those conditions. Executor on reopening: answer-runtime/operations owner. Successor: `AD-M10-01` and `AD-M10-02` for the selected topology.

## Immutable scope and goal

If and only if task 01 approves extraction, deploy `AnswerRuntime.Run` gRPC with parity, auth, health, cancellation, and rollback proof.

**Goal:** Conditional AnswerRuntime service implementation. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Acceptance/release:** [AD-M09-01](01-runtime-extraction-decision.md) records a reviewed approval, selected topology, and required ADR amendment.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `non-claimable conditional task`.
- **Exclusive owned paths:** none while blocked; the named reopening executor reserves only the paths specified in a new claim record.
- **Forbidden paths:** all implementation, test, and configuration paths until the recorded reopening trigger is satisfied.

## Parallel safety and reserved surfaces

Reserve new runtime service, dedicated network, deployment, and parity tests. Strictly synchronous after the decision.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M09 conditional-delivery requirement](../../../answer-delivery/README.md#m09-decide-whether-to-deploy-the-answer-runtime-separately)
- [Components and dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction)
- [ADR decision](../../../answer-delivery/adr-internal-rpc-transport.md#decision)
- [ADR amendment rule](../../../answer-delivery/adr-internal-rpc-transport.md#amendment-rule)

## Acceptance criteria

Browser contracts remain unchanged; new boundary meets gRPC/security/lifecycle requirements.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run full parity, Compose, cancellation, health/auth, and rollback suite.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** Blocked pending a reviewed decision; do not start speculatively.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M10 consumes selected topology and operator evidence.

This blocked record is non-claimable. Only the named executor may claim it after the recorded reopening trigger is met; preserve its blocker and decision evidence in the append-only log.
