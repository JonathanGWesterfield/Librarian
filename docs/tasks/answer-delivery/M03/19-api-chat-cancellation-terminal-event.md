# M03 · Restore API chat cancellation terminal event

- **Task ID:** `AD-M03-19`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **in review**
- **Claim record:** owner: **`/root`**; branch/worktree: **`codex/m03-api-chat-cancellation-terminal-event` in the shared Librarian worktree**; claimed timestamp: **2026-10-26T12:08:13-05:00**; last update: **2026-10-26T13:10:00-05:00**; coordination contact: **`/root` via this task record**. Reserved paths: **`packages/librarian_answer/runtime.py`**, **`packages/librarian_answer/ports.py`**, **`packages/librarian_answer_adapters/grpc_broker.py`**, **`packages/librarian_answer_adapters/grpc_chat.py`**, **`apps/api/librarian_api/r2_chat.py`**, **`tests/answer/test_grpc_chat.py`**, and this task record.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Repair the live API-chat generated-RPC cancellation path found by [AD-M03-02](02-all-caller-grpc-proof.md). After cancellation occurs during an admitted gRPC call, the runtime must produce exactly one terminal `cancelled` event and no validated or completed answer.

## Prerequisite task IDs and ordered dependencies

- **Discovery:** [AD-M03-02](02-all-caller-grpc-proof.md) is blocked until this repair supplies its regression evidence.
- **Implementation baseline:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-09](09-api-chat-migration.md) are complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`; it blocks M03’s chat proof and final acceptance but not unrelated caller proofs.
- **Exclusive owned paths/surfaces:** `packages/librarian_answer/runtime.py`, `packages/librarian_answer/ports.py`, `packages/librarian_answer_adapters/grpc_broker.py`, `packages/librarian_answer_adapters/grpc_chat.py`, `apps/api/librarian_api/r2_chat.py`, and `tests/answer/test_grpc_chat.py`.
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

- **Implementation / merged PR / SHA:** 2026-10-26 — The runtime now converts a context-driven cancellation raised while it awaits synthesis or support review into one terminal `cancelled` event, while re-raising unrelated task cancellation. The generated runtime adapter detects an elapsed API deadline after its admitted RPC is cancelled and surfaces an ordinary safe generation failure instead of a `cancelled` event. Uncommitted; pending independent review and parent packaging. Baseline Git SHA: `39644a32d4be28b07cea55d380b85a3ab7e98e03`.
- **Commands and results:** 2026-10-26 — Initial reproduction: `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_grpc_chat` — failed as expected before the repair when `AnswerRuntime.run()` propagated `CancelledError` during the live generated RPC. Final: `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_runtime tests.answer.test_grpc_chat tests.answer.test_grpc_broker_adapter tests.answer.test_grpc_generation` — passed: 26 tests, including live authenticated API generated-stub cancellation and elapsed-deadline cases. `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test ruff check packages/librarian_answer/runtime.py packages/librarian_answer_adapters/grpc_broker.py tests/answer/test_grpc_chat.py` — passed. `git diff --check && python3 scripts/check_task_ledger.py` — passed; ledger reports 64 fresh task files. Test image: `librarian-grpc-chat-test` (`sha256:c66d7cd37b4ea89062b5c8dd5c981fc0666cb0778f043042339240196e22afbe`).
- **Commands and results:** 2026-10-26 — Final post-review command: `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_runtime tests.answer.test_grpc_chat tests.answer.test_grpc_broker_adapter tests.answer.test_grpc_generation tests.api.test_r2_chat` — passed: 39 tests. It covers live authenticated generated-stub cancellation for disconnect, explicit cancellation, deadline, and unrelated task cancellation, plus a source-selection call through `_PhaseRequestContext` with a legacy parent context lacking `cancellation_cause`. Final lint: `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test ruff check packages/librarian_answer/ports.py packages/librarian_answer/runtime.py packages/librarian_answer_adapters/grpc_broker.py apps/api/librarian_api/r2_chat.py tests/answer/test_grpc_chat.py` — passed. `git diff --check && python3 scripts/check_task_ledger.py` — passed; ledger reports 64 fresh task files.
- **Commands and results:** 2026-10-26 — Final deadline-lifecycle command: `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.answer.test_runtime tests.answer.test_grpc_chat tests.answer.test_grpc_broker_adapter tests.answer.test_grpc_generation tests.api.test_r2_chat` — passed: 41 tests. It adds deadline assertions after retrieval and between synthesis and validation; both produce the safe `generation_unavailable` completion without broker admission or a `cancelled`/validated event. The changed-path Ruff command and `git diff --check && python3 scripts/check_task_ledger.py` passed again; ledger reports 64 fresh task files.
- **Commands and results:** 2026-10-26 — Senior reviewer independently repeated the final 41-test Docker suite, changed-path Ruff, `git diff --check`, and task-ledger check; all passed. Full local Compose/Ollama/Chrome startup remains unavailable because config resolution rejects `generation.api_key_file` before the API and broker start. That ignored local configuration condition is outside this task's focused proof and remains a later M03/M07 acceptance limitation.
- **Reports / screenshots:** 2026-10-26 — No retained reports or screenshots. The live test starts an in-process authenticated generated gRPC broker with a blocking provider and observes its downstream cancellation event; it contains only synthetic fixture text and credentials.
- **Review findings and repairs:** 2026-10-26 — Created from AD-M03-02 live generated-client discovery; its initial test must assert the terminal lifecycle rather than accept propagated cancellation.
- **Review findings and repairs:** 2026-10-26 — Independent review found that the first repair used `is_cancelled()` and an API-only `was_disconnected` attribute to distinguish cancellation from a deadline. That is insufficient: explicit adapter cancellation and disconnect must be distinguishable from elapsed deadline through a transport-neutral cause. The scope therefore expands to the request-context port and its API implementation; this task remains in progress until explicit cancellation, disconnect, and deadline regressions pass independently.
- **Review findings and repairs:** 2026-10-26 — Senior code/design review passed after three repair rounds. The final implementation maps every runtime gate through the transport-neutral cause: explicit cancellation and disconnect emit exactly one `cancelled`, deadline emits a safe `generation_unavailable` completion, and unrelated task cancellation propagates. The authenticated generated-stub test proves downstream RPC cancellation and no late answer. No AD-M03-19 acceptance criterion remains unmet; retain `in review` until the implementation is merged.
- **Blockers / decisions:** _Not recorded._

## Handoff

Return the live regression evidence to [AD-M03-02](02-all-caller-grpc-proof.md), which can then be reopened for the all-chat generated-client proof. This task must not mark M03, M04, or a release ready.
