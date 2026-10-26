# M03 · Evaluator gRPC proof

- **Task ID:** `AD-M03-18`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Prove evaluator uses only evaluator judgement through its generated client, with budget/cancellation, and never constructs HTTP/local judge paths.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-13](13-evaluator-migration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths/surfaces:** `tests/evaluation/test_r2_evaluator_grpc.py` only (create this focused proof file if absent).
- **Forbidden paths/surfaces:** `scripts/evaluate_retrieval.py`, API/worker code, and all other proof tests. Ignored local configuration, secrets, EPUBs, runtime data, and approved specifications remain forbidden.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Evaluator inventory row](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Evaluator operation/output/authentication/cancellation proof passes; wrong-principal requests fail before provider execution.

## Required tests and evidence

Run evaluator focused tests and evaluator Compose profile/authorization proof.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs. Redact credentials, local configuration, private EPUB text, prompts, and evidence excerpts.

- **Implementation / merged PR / SHA:** _Not recorded._
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Before review, record exact paths, commands/results, SHA, and PR. Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with a precise reopening condition. A merged task changes the roadmap and #87 only when it changes milestone eligibility, blocker, or next work.
