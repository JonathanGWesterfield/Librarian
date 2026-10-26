# M03 · Prove R2 isolation and compatibility handshake

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-03`
- **Lifecycle status:** **in review**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **/root/implementer**; branch/worktree: **codex/ad-m03-03-isolation-proof** / **/Users/codexai/Documents/Librarian-worktrees/ad-m03-03**; claimed timestamp: **2026-10-26 20:58 CET**; last update: **2026-10-26 20:58 CET**; coordination contact: **/root**. Temporarily coordinated with unclaimed AD-M03-04 for `scripts/run_answer_delivery_compose.sh` probe wiring; no AD-M03-04 acceptance conclusion is delegated. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Validate role-specific secrets, private broker networks, broker-only egress, sanitized mounts, authenticated Health, and compatibility admission.

**Goal:** Prove R2 isolation and compatibility handshake. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-10](../M01/10-sanitized-runtime-config.md) and [AD-M01-13](../M01/13-compose-topology-policy.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `docker-compose.r2.yml`, `tests/e2e/test_answer_delivery_compose_script.py`, `tests/fixtures/answer_delivery/r2-compose/` topology/handshake assertions, and bounded probe wiring in `scripts/run_answer_delivery_compose.sh`.
- **Forbidden paths:** All caller adapter modules and tests; cutover scripts; browser/API delivery code; ignored local config/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve `docker-compose.r2.yml`, topology assertions, and Compose security fixtures. Coordinate all Compose changes through one claimant.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Atomic compatibility handshake](../../../answer-delivery/technical-design.md#atomic-compatibility-handshake)
- [ADR local-Compose trust model](../../../answer-delivery/adr-internal-rpc-transport.md#local-compose-trust-model)
- [Configuration and Compose migration](../../../answer-delivery/compatibility-and-migration.md#configuration-and-compose-migration)
- [Inventory, authorization, and compatibility coverage](../../../answer-delivery/acceptance.md#inventory-authorization-and-compatibility-coverage)

## Acceptance criteria

Each principal has only its permitted secret/network; health cannot Generate; mismatched SHA/major/minor/descriptor fail before admission.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run all-profile rendered Compose and in-container isolation/handshake suite.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** [PR #122](https://github.com/JonathanGWesterfield/Librarian/pull/122); clean live-tested commit `2171f8ff4538b3fc992774efd0c6ca4b2a4df9fa`.
- **Commands and results:** Canonical live harness and 516-test full gate passed; exact commands and evidence below.
- **Reports / screenshots:** `/tmp/librarian-ad-m03-03-reports/{compose-summary,authorization,compatibility,cancellation}.json`; live log `/tmp/librarian-ad-m03-03-compose.log`; full gate `/tmp/librarian-ad-m03-03-check.log`.
- **Review findings and repairs:** Independent code and live-evidence review approved; no blocking findings.
- **Blockers / decisions:** No task-local blocker. Awaiting merge; M03 and AD-M03-04 acceptance remain separate.

- **2026-10-26 20:58 CET — Claim:** /root/implementer claimed this parallel implementation on `codex/ad-m03-03-isolation-proof`, reserving `docker-compose.r2.yml`, `tests/e2e/test_answer_delivery_compose_script.py`, `tests/fixtures/answer_delivery/r2-compose/` topology assertions, and—under recorded AD-M03-04 coordination—bounded probe wiring in `scripts/run_answer_delivery_compose.sh`. Coordinator: /root. The roadmap, issue #87, task index, all design sources, existing harness, and current worktree were audited. The slice does not claim M03 or AD-M03-04 acceptance.
- **2026-10-26 20:58 CET — In progress:** adding only tracked fixture probe wiring for per-caller positive/mismatched capability handshakes, cyclic cross-private-network refusal, and live evaluator network inspection. Existing four-report schema, fixture-only inputs, and normal-stack isolation remain unchanged.
- **2026-10-26 21:02 CET — Implementation evidence:** on base `224c7d2a631ab67201fec919afea0b8b09003a9f`, added the tracked `caller_isolation_probe.py` fixture and bounded harness wiring. API, summary-worker, metadata-worker, and a project-scoped ephemeral evaluator each open their real R2 client for a positive caller-local readiness handshake; each then submits SHA, descriptor, minor, and major mutations through the generated `GetCapabilities` stub and requires `FAILED_PRECONDITION` with `CONTRACT_MISMATCH` before `Generate`. Every caller also must fail a short socket connection to the broker IP on a cyclically different private network. The harness inspects the evaluator container's live network membership before cleanup. All probe output is role/check success only; the four report schema remains unchanged. `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/test.sh tests.e2e.test_answer_delivery_compose_script` passed 7 tests. `bash -n scripts/run_answer_delivery_compose.sh`, `/private/tmp/librarian-m03-test-venv/bin/ruff check tests/e2e/test_answer_delivery_compose_script.py tests/fixtures/answer_delivery/r2-compose/caller_isolation_probe.py`, and `git diff --check` passed. The real all-profile fixture-overlay `docker compose ... config --format json` render passed with expected non-Swarm secret-mode warnings and confirmed the four private networks are internal, broker egress is non-internal, and principal memberships are exact. Clean-checkout live harness evidence remains required before review completion.
- **2026-10-26 21:04 CET — Independent code review:** `/root/reviewer` approved the fixture branch coverage and real Compose topology validation. The clean-checkout canonical harness is the only remaining proof before final review, so lifecycle remains `in progress`; no M03 or AD-M03-04 acceptance conclusion is claimed.

- **2026-10-26 — Bounded reservation coordination:** coordinator reserves harness probe wiring for this task in addition to its original topology/test paths, with AD-M03-04 unclaimed and gated. Existing compatibility probes run only inside the broker with API credentials and do not inspect the ephemeral evaluator network. Caller-local probes and evaluator network inspection are needed to satisfy the existing immutable scope; this adds no production caller code, trust-model change, or early release conclusion.

- **2026-10-26 — Clean live evidence:** `env VERIFY_PROJECT=librarian-ad-m03-03 ANSWER_DELIVERY_REPORT_DIR=/tmp/librarian-ad-m03-03-reports scripts/run_answer_delivery_compose.sh` passed at clean `2171f8ff4538b3fc992774efd0c6ca4b2a4df9fa`. All four caller-local positive/mismatch/isolation probes passed before report generation. The four redacted reports prove 12 authorized and 24 denied operations, unauthenticated denial, authenticated health, all four contract mismatch categories, deadline/queue/unhealthy rejection, and live RPC cancellation/reaping. `/root/reviewer` independently inspected the log/reports and confirmed no project containers remained, including the evaluator probe. Expected non-Swarm secret-mode warnings only; normal-stack inputs were not used.
- **2026-10-26 — Image evidence:** project image SHA256 IDs: broker `6fa817b00a962420cdb7cd8efd0a1400680824a5889629b480693684c7870ef3`; API `fb0affd8ac496bd238ad2aef1ff80d30e670d9680df13d9155837a6f6bed90bc`; summary-worker `cf0d417cd42dc23fcca33b8fdff556553dc8e1770364a70c2c4f84e6950d91f9`; metadata-worker `b62ca2f3f3fe944028df473b0b2a30933b359ec8cb808013399f2797df51f35d`; evaluator `5db1c672048ab58f8cbf510aadeb3bc7db5c8b7dcd4e3d997e14b211e3a88221`; resolver `2844c3fadb069b135ef962ad7b6a7e77c3c2b47182cc97cf49dead1975d58dca`.
- **2026-10-26 — Full gate and handoff:** `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` passed, including 516 tests. The task moves to `in review` for PR #122; only documentation/evidence changes follow the live-tested commit. Merge is required before completion. This evidence does not complete M03, cutover/rollback, or AD-M03-04.

- **2026-10-26 — Final approval:** `/root/reviewer` approved the complete implementation and evidence transition after the 516-test gate, with no blocking or important findings. Task remains `in review` until PR #122 merges.

## Handoff

Required before M03 exit and M04/M05 release claims.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
