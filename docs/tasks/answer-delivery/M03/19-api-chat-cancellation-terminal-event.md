# M03 · Restore API chat cancellation terminal event

- **Task ID:** `AD-M03-19`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **planned**
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Answer-runtime owner.**
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Repair the live API-chat generated-RPC cancellation path found by [AD-M03-02](02-all-caller-grpc-proof.md). After cancellation occurs during an admitted gRPC call, the runtime must produce exactly one terminal `cancelled` event and no validated or completed answer.

## Prerequisite task IDs and ordered dependencies

- **Discovery:** [AD-M03-02](02-all-caller-grpc-proof.md) is blocked until this repair supplies its regression evidence.
- **Implementation baseline:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-09](09-api-chat-migration.md) are complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`; it blocks M03’s chat proof and final acceptance but not unrelated caller proofs.
- **Exclusive owned paths/surfaces:** `packages/librarian_answer/runtime.py`, `packages/librarian_answer_adapters/grpc_broker.py`, `packages/librarian_answer_adapters/grpc_chat.py`, and `tests/answer/test_grpc_chat.py`.
- **Forbidden paths/surfaces:** public SSE projection, browser reducer, worker/evaluator implementation and proof tests, ignored local configuration, secrets, EPUBs, and runtime data.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These preserve the in-process runtime and internal gRPC boundary.

**Direct requirements for this task:**
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Admission, execution, cancellation, and shutdown](../../../answer-delivery/technical-design.md#admission-execution-cancellation-and-shutdown)
- [API chat inventory row](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)
- [Local Chrome UAT cancellation behavior](../../../answer-delivery/acceptance.md#local-chrome-uat)

## Acceptance criteria

An authenticated live API generated-client call started through `AnswerRuntime.run()` is cancelled at the gRPC boundary, then yields exactly one `cancelled` terminal event. It emits no `answer_validated` or `completed` event and no late answer; the repair introduces no HTTP or local-provider fallback.

## Required tests and evidence

Run focused live generated-stub cancellation, answer-runtime lifecycle, and API chat tests. Record exact commands, result, Git SHA, image IDs where relevant, reports, and unavailable conditions without private text, prompts, secrets, or configuration.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** _Not recorded._
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** 2026-10-26 — Created from AD-M03-02 live generated-client discovery; its initial test must assert the terminal lifecycle rather than accept propagated cancellation.
- **Blockers / decisions:** _Not recorded._

## Handoff

Return the live regression evidence to [AD-M03-02](02-all-caller-grpc-proof.md), which can then be reopened for the all-chat generated-client proof. This task must not mark M03, M04, or a release ready.
