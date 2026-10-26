# M03 · Metadata-worker gRPC proof

- **Task ID:** `AD-M03-17`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** owner: **/root/implementer**; branch/worktree: **codex/ad-m03-17-metadata-proof** / **/Users/codexai/Documents/Librarian**; claimed timestamp: **2026-10-26 16:51 CET**; last update: **2026-10-26 16:58 CET**; coordination contact: **/root**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Prove metadata-worker invokes only tag/genre through its own credential/network and cancels active jobs safely.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-08](08-generated-client-adapter.md) and [AD-M03-12](12-metadata-worker-migration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths/surfaces:** `tests/answer/test_r2_metadata_worker_grpc.py` only (create this focused proof file if absent).
- **Forbidden paths/surfaces:** `scripts/process_metadata_jobs.py`, `packages/librarian_answer_adapters/worker_lifecycle.py`, API/evaluator code, and all other proof tests. Ignored local configuration, secrets, EPUBs, runtime data, and approved specifications remain forbidden.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Metadata-worker inventory row](../../../answer-delivery/technical-design.md#complete-boundary-and-migration-inventory)
- [v1 operation/output/principal matrix](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

Only tag/genre operations are authorized; denied operations never admit provider work; timeout and shutdown behave as designed.

## Required tests and evidence

Run focused worker integration and metadata-worker Compose profile/authorization proof.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs. Redact credentials, local configuration, private EPUB text, prompts, and evidence excerpts.

- **Implementation / merged PR / SHA:** _Not recorded._
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

- **2026-10-26 16:51 CET — Claim:** /root/implementer claimed this parallel implementation slice on `codex/ad-m03-17-metadata-proof`, reserving `tests/answer/test_r2_metadata_worker_grpc.py` and this task record. Coordinator: /root. Prerequisite records were reviewed as complete; this task does not change milestone or release status.
- **2026-10-26 17:02 CET — In progress:** implementing the reserved generated-gRPC metadata-worker proof. It will exercise the durable tag/genre job path, pre-provider authorization denial, short deadline cleanup, and shutdown recovery with tracked synthetic SQLite data only.
- **2026-10-26 16:58 CET — Implementation evidence:** added `tests/answer/test_r2_metadata_worker_grpc.py`. Its live generated-stub listener/client and temporary SQLite fixture prove tag and genre durable jobs reach the provider, a metadata credential cannot invoke book summary before provider admission, a short generated-client deadline cancels a blocking provider without a late result, and shutdown leaves a claimed tag job for recovery on the next worker pass. `/private/tmp/librarian-m03-test-venv/bin/python3 -m unittest tests.answer.test_r2_metadata_worker_grpc -v` passed 4 tests; the related worker/metadata group passed 23 tests. `py_compile` and `git diff --check` passed for owned files.
- **2026-10-26 16:58 CET — Isolated Compose baseline:** in a separate clean checkout at `d9287da165ed1d36303b73f9331a63f53ac64f5a`, `VERIFY_PROJECT=librarian-ad-m03-17 ANSWER_DELIVERY_REPORT_DIR=/tmp/librarian-ad-m03-17-reports scripts/run_answer_delivery_compose.sh` passed. Redacted reports show `metadata-worker` running; 12 authorized and 24 denied calls across four principals; deadline, queue, unhealthy-broker, and contract-mismatch denials; plus live RPC cancellation with process-group reaping. The baseline predates this uncommitted proof file; it is retained Compose-profile evidence, not a claim that the new test was included in that run. No normal-stack, private-data, or ignored-configuration changes were made.
- **2026-10-26 16:58 CET — Review handoff:** owned implementation is ready for independent review. No commit SHA or PR exists yet; review findings will be recorded here before the parent packages the approved slice.
- **2026-10-26 16:58 CET — Validation and review:** `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh tests.answer.test_r2_metadata_worker_grpc tests.answer.test_r2_worker_grpc_integration tests.answer.test_r2_worker_scripts tests.answer.test_grpc_generation tests.ingestion.test_metadata_jobs` passed 23 tests; `/private/tmp/librarian-m03-test-venv/bin/ruff check tests/answer/test_r2_metadata_worker_grpc.py` and `git diff --check` passed. Senior independent reviewer `/root/reviewer` approved the proof after an independent focused run. Lifecycle moved to `in review`; no completion is claimed before a reviewed PR is merged.
- **2026-10-26 16:58 CET — Timestamp correction:** the preceding `17:02 CET` in-progress entry was recorded from an incorrect clock reading. Verified `TZ=Europe/Berlin date` at this update is `2026-10-26 16:58 CET`; this correction preserves the append-only history without changing the earlier entry.
- **2026-10-26 16:58 CET — Full local gate:** coordinator ran `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` in `/Users/codexai/librarian-ad-m03-17-check`, a clean checkout containing only this task record and proof test on top of the baseline. It passed with 496 tests in 6.353 seconds, including contract generation/drift/breaking, task-ledger freshness, compilation, and evaluation checks. Log: `/tmp/librarian-ad-m03-17-check.log`.
- **2026-10-26 16:58 CET — Final independent review:** `/root/reviewer` re-reviewed the final two-file diff and approved it. Scope, append-only chronology correction, `in review` lifecycle, and the distinction between baseline Compose evidence and the uncommitted proof were confirmed. No blocker or important findings remain. The full-gate log has pre-existing-style resource warnings and expected host-guard messages but exits successfully; neither is attributed to this slice.

- **2026-10-26 — PR handoff:** [PR #114](https://github.com/JonathanGWesterfield/Librarian/pull/114) contains the approved two-file slice. Its head commit is the implementation SHA; the task remains `in review` until merge. No milestone completion or release readiness is claimed.

- **2026-10-26 — Merged completion:** PR #114 merged as `d4a4d1cea73247fa5c7320135992089abb0c36d0`; merge verified through GitHub. The approved focused proof, 496-test full gate, and isolated Compose baseline evidence satisfy this task. Lifecycle is now `complete`; M03 remains in progress with its separate acceptance/release gates.

## Handoff

Before review, record exact paths, commands/results, SHA, and PR. Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with a precise reopening condition. A merged task changes the roadmap and #87 only when it changes milestone eligibility, blocker, or next work.
