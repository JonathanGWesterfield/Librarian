# M03 · Preserve R2 dependency profiles during resolver bootstrap

- **Task ID:** `AD-M03-21`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** owner: **/root/implementer**; branch/worktree: **codex/ad-m03-21-compose-bootstrap** / **/Users/codexai/Documents/Librarian-worktrees/ad-m03-21**; claimed timestamp: **2026-10-26 19:57 CET**; last update: **2026-10-26 19:58 CET**; coordination contact: **/root**.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Repair the isolated harness resolver invocation so the effective Compose model includes the resolver and every R2 dependency needed to validate it. Preserve exactly four reported acceptance profiles and all trust/isolation assertions.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M03-20](20-compose-harness-config-resolver-profile.md) is merged; this task repairs its resolver-only command's undefined-broker dependency failure.
- **Coordination:** AD-M03-04 remains unclaimed and gated. This bounded maintenance repair owns the shared harness/test surfaces until review handoff; it does not run the final acceptance conclusion early.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel maintenance`; it unblocks caller-specific Compose proofs but does not claim M03 acceptance or release.
- **Exclusive owned paths/surfaces:** `scripts/run_answer_delivery_compose.sh` and `tests/e2e/test_answer_delivery_compose_script.py`.
- **Forbidden paths/surfaces:** `docker-compose.answer-delivery.yml`, caller adapter code/tests, runtime configuration fixtures, production local configuration, secrets, EPUBs, runtime data, and generated reports.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** The browser remains external HTTP/SSE and the R2 internal boundary remains gRPC.

**Direct requirements for this task:**
- [Configuration and Compose migration](../../../answer-delivery/compatibility-and-migration.md#configuration-and-compose-migration)
- [Atomic deployment and rollback](../../../answer-delivery/compatibility-and-migration.md#atomic-deployment-and-rollback)
- [Deterministic fixture suite](../../../answer-delivery/acceptance.md#deterministic-fixture-suite)
- [Reproducible commands and retained evidence](../../../answer-delivery/acceptance.md#reproducible-commands-and-retained-evidence)

## Acceptance criteria

The exact resolver bootstrap command validates with real Docker Compose, includes required R2 dependency profiles, uses only tracked fixtures, and preserves the four reported profiles. A regression must detect the resolver-only undefined-dependency failure. The canonical clean-checkout harness must complete and emit its four redacted reports; the normal stack remains untouched.

## Required tests and evidence

Run focused harness regression, the actual bootstrap Compose configuration validation, the canonical isolated clean-checkout harness, independent review, and full repository checks. Record the tested SHA, exact commands, redacted reports, and any limitations.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **2026-10-26 — Task registered:** the clean current-main harness fails before startup because its resolver-only profile set excludes the broker required by API. AD-M03-20 is merged; this new bounded maintenance task owns the follow-up repair rather than reopening the completed task. No implementation is yet claimed.
- **2026-10-26 19:57 CET — Claim:** /root/implementer claimed this parallel maintenance slice on `codex/ad-m03-21-compose-bootstrap`, reserving `scripts/run_answer_delivery_compose.sh`, `tests/e2e/test_answer_delivery_compose_script.py`, and this task record. Coordinator: /root. The roadmap, issue #87, task index, AD-M03-20, all design sources, and current shared-worktree diff were reviewed. This task does not advance M03 or M03-04 acceptance.
- **2026-10-26 19:58 CET — In progress:** updating only the resolver bootstrap command and its scoped regression. The bootstrap model will enable `config-resolver` plus all four R2 dependency profiles, while report-facing profiles remain the documented four. Validation will use the fixture overlay and a release SHA only; it will not mutate the normal stack or local configuration.
- **2026-10-26 20:00 CET — Implementation evidence:** on base `f738749ef228c424ad0566ec0bc1417e6ae69adf`, the resolver bootstrap command now enables `config-resolver`, `codex-broker`, `workers`, `metadata-workers`, and `evaluation`; the separate report-facing profile array remains exactly the four documented R2 profiles. The scoped regression still executes the harness with fake Docker to distinguish those two command boundaries, and now renders the real fixture-overlay Compose model with `LIBRARIAN_STACK_RELEASE_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, asserting `config-resolver`, API, broker, summary worker, metadata worker, and evaluator are all present. `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh tests.e2e.test_answer_delivery_compose_script` passed 5 tests. `bash -n scripts/run_answer_delivery_compose.sh`, `/private/tmp/librarian-m03-test-venv/bin/ruff check tests/e2e/test_answer_delivery_compose_script.py`, and `git diff --check` passed. The direct full-profile `docker compose ... config --format json` assertion also passed (only expected non-Swarm secret-mode warnings). No normal-stack, local-config, fixture, secret, or report file was changed.
- **2026-10-26 20:02 CET — Review repair:** `/root/reviewer` found that the real-model test had a separately hardcoded bootstrap profile sequence, so it could drift from the script command it was meant to prove. The test now captures both profile arrays from the existing fake-Docker execution of the harness; it feeds the captured resolver sequence into the real fixture-overlay Compose render and asserts that it is exactly `config-resolver` plus the four report profiles. The focused suite again passed 5 tests; ruff, Bash syntax, and `git diff --check` passed. Re-review requested.
- **2026-10-26 20:03 CET — Independent code review:** `/root/reviewer` approved the repair and independently confirmed the captured resolver sequence drives the real Compose model test, with focused tests (5/5) and source checks passing. The task remains `in progress` pending the coordinator's clean-checkout canonical harness evidence and final review; no M03 or M03-04 acceptance conclusion is claimed.

- **2026-10-26 — Clean live harness:** `VERIFY_PROJECT=librarian-ad-m03-21 ANSWER_DELIVERY_REPORT_DIR=/tmp/librarian-ad-m03-21-reports scripts/run_answer_delivery_compose.sh` passed (exit 0) on clean committed source `a14cd70c1f99ec4151559553082a290fca98c3ce`, without extra profile environment overrides. The four redacted reports are `/tmp/librarian-ad-m03-21-reports/compose-summary.json`, `authorization.json`, `compatibility.json`, and `cancellation.json`; log `/tmp/librarian-ad-m03-21-compose.log`. All four profiles passed: 12 authorized / 24 denied operations, unauthenticated denial, exact secret/network isolation assertions, authenticated health, release/descriptor/major/minor mismatch rejection, queue/deadline/unhealthy checks, absent HTTP listener, and live RPC cancellation with process-group reaping. No project containers remained after harness cleanup. This verifies the maintenance repair, not final M03 acceptance or cutover.
- **2026-10-26 — Tested image IDs:** `librarian-ad-m03-21-api` = `sha256:62aa8bc6c356ec055ddfb9258ca867982c1a6f983b5d4c35671bb8d1e7eae39f`; broker = `sha256:e7baec93a05a46f320a74d90b9a0faf356cdbe12c7d546f40c4fe90eb02410d3`; summary worker = `sha256:039f1294ad1ab93d52f4989c5dcf41085757d7d2cfa989f46f452198d6cc3379`; metadata worker = `sha256:39f7382dee590d8e8135667339ba86e62619ce61e8b5af2be842b6df1f0c8853`; evaluator = `sha256:052072845a1486975bda887b94d706ca5e78568c5708d3d76d71c8e4ce3c3eb8`; resolver = `sha256:6938a3a9e745c990da6ba073fc1cded414b32df414bbdacb8cf203cc44b00870`.
- **2026-10-26 — PR handoff:** [PR #120](https://github.com/JonathanGWesterfield/Librarian/pull/120) contains the repair. The tested source SHA above is retained for reproducibility; later documentation-only amendments record evidence. Task remains `in review` until merge.

- **2026-10-26 — Independent live review and full gate:** `/root/reviewer` inspected the canonical log and all four redacted reports and approved live evidence without blocker/important findings. The subsequent `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` passed 514 tests in 8.723 seconds (exit 0), including actual Compose rendering, contract generation/breaking checks, ledger freshness, compilation, and evaluation. Log: `/tmp/librarian-ad-m03-21-check.log`.

- **2026-10-26 — Final approval:** `/root/reviewer` approved the complete ten-file implementation/evidence transition after the 514-test gate, with no blocker or important findings. The current task remains `in review` until PR #120 merges; AD-M03-04 and the non-chat proof retain their own gates.

- **2026-10-26 — Merged completion:** verified PR #120 merged as `224c7d2a631ab67201fec919afea0b8b09003a9f`. Independent code/live review and the 514-test full gate passed; task is complete and releases its shared harness regression surface. M03 acceptance and cutover gates remain separate.

## Handoff

Hand a successful clean-checkout harness run and redacted report paths to AD-M03-03, AD-M03-15, and AD-M03-04. This maintenance repair does not itself complete any release gate.
