# M03 · Evaluator gRPC proof

- **Task ID:** `AD-M03-18`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** owner: **/root/implementer**; branch/worktree: **codex/ad-m03-18-evaluator-proof** / **/Users/codexai/Documents/Librarian-worktrees/ad-m03-18**; claimed timestamp: **2026-10-26 18:32 CET**; last update: **2026-10-26 18:35 CET**; coordination contact: **/root**.
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

- **2026-10-26 18:32 CET — Claim:** /root/implementer claimed this parallel implementation slice on `codex/ad-m03-18-evaluator-proof`, reserving `tests/evaluation/test_r2_evaluator_grpc.py` and this task record. Coordinator: /root. Prerequisites were reviewed as complete; this task does not advance M03 or release status.
- **2026-10-26 18:32 CET — In progress:** implementing the reserved live generated-gRPC evaluator proof. It will exercise evaluator-judgement/verdict operation binding, wrong-principal pre-provider denial, the fixed 30-second budget, cancellation, and absence of legacy judge fallback using synthetic fixtures only.
- **2026-10-26 18:35 CET — Implementation evidence:** added `tests/evaluation/test_r2_evaluator_grpc.py`. Its live generated-stub listener/client and `GrpcEvaluatorJudge` prove evaluator judgement uses only `EVALUATOR_JUDGEMENT` with `EVALUATOR_VERDICT_JSON_V1`; evaluator and summary-worker cross-role requests are denied before provider work; a shortened test stand-in for the fixed 30-second budget cancels a blocking provider without a late result; shutdown cancels an active judgement and a fresh judgement succeeds. The deadline proof makes direct legacy subprocess, HTTP, Codex, and Ollama fallback paths fail if touched. `/private/tmp/librarian-m03-test-venv/bin/python3 -m unittest tests.evaluation.test_r2_evaluator_grpc -v` passed 4 tests. `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh tests.evaluation.test_r2_evaluator_grpc tests.answer.test_r2_evaluator_script tests.evaluation.test_llm_judge tests.answer.test_r2_worker_grpc_integration tests.answer.test_grpc_generation` passed 33 tests; ruff and `git diff --check` passed.
- **2026-10-26 18:35 CET — Compose evidence limitation:** the retained clean `d4a4d1cea73247fa5c7320135992089abb0c36d0` all-role baseline reports at `/tmp/librarian-ad-m03-16-baseline-reports` include evaluator authorization/profile evidence, and evaluator source is unchanged since that run. Current main `e5d57a03ad40b2358968335d5ec53f5785277125` fails the canonical harness before services start because API depends on undefined `codex-broker`, with and without explicit profiles; log: `/tmp/librarian-ad-m03-18-default-compose.log`. This external resolver-profile regression prevents a current evaluator Compose run and is not attributed to this test-only slice.
- **2026-10-26 18:35 CET — Review repair:** `/root/reviewer` required the live deadline test to make direct legacy subprocess and HTTP fallback calls fail if touched, in addition to Codex/Ollama constructors. The focused test now patches all four paths during the gRPC deadline and passed the full targeted suite.
- **2026-10-26 18:35 CET — Independent review:** `/root/reviewer` approved the repaired code/design proof and independently passed a broader 41-test evaluator/broker group plus ruff. Lifecycle moved to `in review`; final diff approval awaits the coordinator-owned full gate. No M03 completion or release readiness is claimed.
- **2026-10-26 18:35 CET — Full local gate:** coordinator ran `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` in the isolated task checkout. It passed with 505 tests in 7.677 seconds; log: `/tmp/librarian-ad-m03-18-check.log`.
- **2026-10-26 18:38 CET — Final review:** `/root/reviewer` approved the complete five-file transition. The review reconfirmed the no-legacy-fallback deadline repair, lifecycle and authorization coverage, ledger evidence, and explicitly limited historical Compose claim. No BLOCKER or IMPORTANT findings remain; coordinator will rebase and request the integration-focused recheck before selective commit and PR work.

- **2026-10-26 — Rebased validation:** rebased onto `81e72fa` without conflicts. The independent reviewer reran 41 evaluator/gRPC/broker tests against the merged cancellation changes and approved integration. Post-review full `scripts/check.sh` passed 512 tests in 7.722 seconds, exit 0; log `/tmp/librarian-ad-m03-18-rebased-check.log`. No current-main live Compose success is claimed.

- **2026-10-26 — PR handoff:** [PR #119](https://github.com/JonathanGWesterfield/Librarian/pull/119) contains the reviewed evaluator proof and prior-task completion reconciliation. Its head commit identifies the implementation SHA. AD-M03-18 remains `in review` pending merge, with current-main Compose acceptance separately blocked.

- **2026-10-26 — Merged completion:** verified PR #119 merged as `f738749ef228c424ad0566ec0bc1417e6ae69adf`. The approved evaluator proof and 512-test gate are merged; task is complete. Historical Compose evidence and the separate current-main bootstrap limitation remain explicitly distinguished.

## Handoff

Before review, record exact paths, commands/results, SHA, and PR. Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with a precise reopening condition. A merged task changes the roadmap and #87 only when it changes milestone eligibility, blocker, or next work.
