# M03 · Include the config-resolver profile in the R2 harness

- **Task ID:** `AD-M03-20`
- **Milestone:** [M03 — Atomic gRPC Codex-broker migration](README.md); task status does not advance milestone status.
- **Lifecycle status:** **in review**
- **Claim record:** owner: **`/root/m03_api_chat_implementer`**; branch/worktree: **`codex/m03-api-chat-grpc-proof` in the shared Librarian worktree**; claimed timestamp: **2026-10-26T10:58:27-05:00**; last update: **2026-10-26T11:13:00-05:00**; coordination contact: **`/root` via this task record**. Reserved paths: **`scripts/run_answer_delivery_compose.sh`**, **`tests/e2e/test_answer_delivery_compose_script.py`**, and this task record.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Repair the isolated R2 Compose harness bootstrap so its one-shot `config-resolver` receives the tracked answer-delivery overlay configuration. The effective R2 report profile set remains exactly the four externally reported R2 profiles; the bootstrap profile is an internal setup requirement.

## Prerequisite task IDs and ordered dependencies

- **Discovery:** [AD-M03-15](15-api-non-chat-compose-proof.md) is blocked because the harness calls `config-resolver` without its profile and receives a missing `/config/librarian.json`.
- **Implementation baseline:** [AD-M03-14](14-cutover-preflight.md) is complete.

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

The script runs `config-resolver` with the tracked R2 overlay active before loading its generated runtime Compose file. Its reported profiles remain `codex-broker`, `workers`, `metadata-workers`, and `evaluation`; a focused regression test distinguishes bootstrap from reported profiles.

## Required tests and evidence

Run the focused harness-script regression and static/rendered Compose configuration check. Record exact non-sensitive commands and results; a full live Compose run remains the caller-proof and M03-04 gate.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** 2026-10-26 — Added an internal `config_resolver_compose` command with only the `config-resolver` profile. The existing `profiles` array remains the exact four reported R2 caller profiles. Uncommitted; pending independent review and parent packaging.
- **Commands and results:** 2026-10-26 — `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test python -m unittest -v tests.e2e.test_answer_delivery_compose_script` — passed: 4 tests. `docker run --rm --volume /Users/codexai/Documents/Librarian:/app --workdir /app librarian-grpc-chat-test ruff check tests/e2e/test_answer_delivery_compose_script.py` — passed. `bash -n scripts/run_answer_delivery_compose.sh && git diff --check` — passed. `LIBRARIAN_STACK_RELEASE_SHA=ba2b5ba32c6bae1920fd10a7288cb6597fc07b31 docker compose --project-name m03-profile-proof --profile config-resolver --profile codex-broker --profile workers --profile metadata-workers --profile evaluation -f docker-compose.yml -f docker-compose.r2.yml -f docker-compose.answer-delivery.yml config --format json` — rendered successfully; a JSON assertion confirmed `config-resolver`, API, broker, both workers, and evaluator. Docker emitted its expected non-Swarm secret-mode warnings.
- **Reports / screenshots:** 2026-10-26 — No retained report: the static rendered JSON was discarded after its assertion. The full live harness was not run because this shared worktree is not a clean release checkout; that remains AD-M03-04 and the caller-proof tasks' required clean-checkout evidence.
- **Review findings and repairs:** 2026-10-26 — Created after AD-M03-15’s clean-worktree harness invocation failed before startup. The tracked fixture mount was confirmed when the config-resolver profile was supplied. 2026-10-26 — Independent senior review passed: the regression executes the Bash script, observes command boundaries, rejects the old shared-profile construction, and preserves the four reported profiles. Reviewer independently repeated the focused suite, Bash/diff/task-ledger checks, lint, and static Compose rendering; no repair requested.
- **Blockers / decisions:** _Not recorded._

## Handoff

Hand the focused regression evidence to [AD-M03-15](15-api-non-chat-compose-proof.md), which must rerun the real harness before it can move to review. This repair does not mark M03, M04, or a release ready.
