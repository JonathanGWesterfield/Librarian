# M03 · Prove R2 isolation and compatibility handshake

- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md)
- **Task ID:** `AD-M03-03`
- **Lifecycle status:** **in review**
- **Milestone status:** In progress. Task status never advances milestone status.
- **Claim record:** owner: **`/root/m03_api_chat_implementer`**; branch/worktree: **`codex/m03-compose-isolation-handshake` in the shared Librarian worktree**; claimed timestamp: **2026-10-26T13:56:49-05:00**; last update: **2026-10-26T14:04:07-05:00**; coordination contact: **`/root` via this task record**. Reserved paths: **`docker-compose.r2.yml`**, **`tests/e2e/test_answer_delivery_compose_script.py`**, **`tests/fixtures/answer_delivery/r2-compose/`**, and this task record.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Validate role-specific secrets, private broker networks, broker-only egress, sanitized mounts, authenticated Health, and compatibility admission.

**Goal:** Prove R2 isolation and compatibility handshake. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-10](../M01/10-sanitized-runtime-config.md) and [AD-M01-13](../M01/13-compose-topology-policy.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `docker-compose.r2.yml`, `tests/e2e/test_answer_delivery_compose_script.py`, and `tests/fixtures/answer_delivery/r2-compose/` topology assertions.
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

- **Implementation/PR:** No claim yet. Attach redacted `authorization.json` and `compatibility.json` evidence when run.
- **2026-10-26T13:56:49-05:00 — Claim:** `/root/m03_api_chat_implementer` claimed this parallel implementation slice on `codex/m03-compose-isolation-handshake`, reserving the declared Compose topology/configuration fixtures and this task record. Coordinator: `/root`. Prerequisites were checked as complete; this claim does not advance M03 or release status.
- **2026-10-26T13:56:49-05:00 — In progress:** reviewing the rendered all-profile topology and the current clean-stack resolver failure against the isolation and atomic-handshake requirements. The implementation will remain inside the reserved paths; a blocker outside those paths will be recorded rather than patched here.
- **Commands and results:** 2026-10-26 — Before this repair, the clean detached worktree at `f738749ef228c424ad0566ec0bc1417e6ae69adf` ran `VERIFY_PROJECT=librarian-m03-03-isolation ANSWER_DELIVERY_REPORT_DIR=/private/tmp/librarian-m03-03-reports scripts/run_answer_delivery_compose.sh` and failed before service startup: resolver-only Compose rendering included the unprofiled R2 API, whose dependency on the disabled `codex-broker` was invalid. No report files were retained or treated as acceptance evidence.
- **Commands and results:** 2026-10-26 — After limiting the dependent R2 API and web services to the `codex-broker` profile, `python3 -m unittest -v tests.e2e.test_answer_delivery_compose_script tests.e2e.test_r2_compose_overlay` passed: **6 tests**. It rendered both the resolver-only bootstrap and documented all-profile topology. The direct all-profile `docker compose ... config --format json` plus `validate_r2_compose_security` also passed; Docker emitted only its expected non-Swarm secret-mode warnings. `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.e2e.test_answer_delivery_compose_script tests.contracts.test_compose_security` passed: **12 tests**, with the Docker-dependent render test skipped inside the image. `ruff check tests/e2e/test_answer_delivery_compose_script.py`, `git diff --check`, and `python3 scripts/check_task_ledger.py` passed; ledger reports 64 fresh task files. Baseline Git SHA: `f738749ef228c424ad0566ec0bc1417e6ae69adf`.
- **Commands and results:** 2026-10-26 — `PATH=/private/tmp/librarian-m03-test-venv/bin:$PATH scripts/check.sh` passed: **515 tests**. It confirmed generated contracts, compatibility with `origin/main`, and 64 fresh task records. The supported project test environment was used after the host Python 3.9 run proved unsuitable for this suite.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** 2026-10-26 — Independent review found that the resolver-only assertion omitted the newly profiled `web` service and the all-profile assertion did not explicitly retain it. The owned Compose test now requires `web` to be absent from resolver-only rendering and present with API, broker, and every caller in documented all-profile rendering. `python3 -m unittest -v tests.e2e.test_answer_delivery_compose_script tests.e2e.test_r2_compose_overlay` passed: **7 tests**; the Docker deterministic/security suite passed: **13 tests** with its two host-Compose render tests skipped inside the container. Changed-file Ruff, `git diff --check`, and `python3 scripts/check_task_ledger.py` passed again.
- **Review findings and repairs:** 2026-10-26 — Independent senior code/design review passed after the web assertions were added. The current clean-state live harness is still a separately gated M03/AD-M03-04 acceptance activity; it is not claimed by this bounded topology repair.
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Required before M03 exit and M04/M05 release claims.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
