# M03 · API non-chat gRPC proof

- **Task ID:** `AD-M03-15`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Prove book summary, genre, and recommendation API routes use only the API principal’s ready generated client and permitted operations.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-10](10-api-non-chat-migration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths/surfaces:** `tests/answer/test_r2_api_non_chat_grpc.py` only (create this focused proof file if absent).
- **Forbidden paths/surfaces:** `apps/api/librarian_api/main.py`, `apps/api/librarian_api/r2_chat.py`, `tests/answer/test_grpc_chat.py`, and worker/evaluator proof tests. Ignored local configuration, secrets, EPUBs, runtime data, and approved specifications remain forbidden.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [API summary/genre/recommendation inventory rows](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Summary, genre, and recommendation pass operation/output/authorization/cancellation checks without request-level provider overrides or HTTP fallback.

## Required tests and evidence

Run focused non-chat generated-client tests and API Compose proof; record exact commands and redacted results.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs. Redact credentials, local configuration, private EPUB text, prompts, and evidence excerpts.

- **Implementation / merged PR / SHA:** _Not recorded._
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Before review, record exact paths, commands/results, SHA, and PR. Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with a precise reopening condition. A merged task changes the roadmap and #87 only when it changes milestone eligibility, blocker, or next work.
