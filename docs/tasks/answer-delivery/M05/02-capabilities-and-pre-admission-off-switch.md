# M05 · Browser capabilities and disabled response

- **Milestone:** [M05 — Configuration, capabilities, and feature off-switch](README.md)
- **Task ID:** `AD-M05-02`
- **Lifecycle status:** **planned**
- **Milestone status:** Parallel configuration implementation in progress; M04 acceptance and M03 exit still gate acceptance/release. Task status never advances milestone status.
- **Claim record:** owner: **Unassigned**; branch/worktree: **Unassigned**; claimed timestamp: **Unassigned**; last update: **Unassigned**; coordination contact: **Unassigned**. Claim by filling every field and changing status to `claimed` before edits.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- **Source of truth:** [roadmap](../../../answer-delivery/README.md), [technical design](../../../answer-delivery/technical-design.md), [ADR 001](../../../answer-delivery/adr-internal-rpc-transport.md), [compatibility plan](../../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../../answer-delivery/acceptance.md)

## Immutable scope and goal

Publish browser delivery capabilities and return a pre-admission disabled response when events are off.

**Goal:** Browser capabilities and disabled response. Do not broaden this task into another milestone or alter the evidence policy: broad synthesis needs ten distinct relevant body-text citations, bounded explanation two, and a point fact one.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M05-01](01-delivery-mode-configuration.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `parallel implementation`.
- **Exclusive owned paths:** `apps/api/librarian_api/main.py`, `apps/api/librarian_api/config.py`, `tests/api/test_chat_delivery_capabilities.py`, `docs/api-endpoints.md`, and `docs/openapi.json`.
- **Forbidden paths:** Configuration schema/defaults, browser reducer/components, broker/Compose topology, local configuration/secrets/EPUBs/runtime data.

## Parallel safety and reserved surfaces

Reserve capability response/API composition root and endpoint documentation. Coordinate route changes with M04/M06 owners.

AD-M05-01 temporarily reserves `scripts/resolve_provider_config.py` and `packages/librarian_contracts/runtime_config.py` to carry the validated non-secret `chat.delivery_mode` into generated `r2_api` configuration and its API-only client preflight only. This is the configuration handoff for this task; AD-M05-02 retains API composition and pre-admission behavior and does not edit either reserved surface. Buffered disables only new event delivery; it does not describe a completed API behavior in this planned task.

Before editing a shared surface, add the planned files and branch/worktree to the claim record. If another active task owns the same surface, coordinate a sequence or split the boundary; do not overwrite its work.


## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [M05 capability/off-switch requirement](../../../answer-delivery/README.md#m05-configuration-capabilities-and-off-switch)
- [Authoritative runtime lifecycle](../../../answer-delivery/technical-design.md#authoritative-runtime-lifecycle)
- [Compatibility promise](../../../answer-delivery/compatibility-and-migration.md#compatibility-promise)
- [Public event evolution](../../../answer-delivery/compatibility-and-migration.md#public-event-evolution)

## Acceptance criteria

Capabilities expose only delivery mode and supported schema versions; disabled requests perform no retrieval/generation and never reintroduce HTTP.

The implementation must conform to the cited source documents, especially the lifecycle, gRPC boundary, configuration/trust, migration, and acceptance requirements that apply to this task.

## Required tests and evidence

Run API capability, disabled-pre-admission, and no-work assertion tests; update API docs/OpenAPI if endpoint changes.

Record the exact command, result, Git SHA, image IDs where relevant, report paths, and any unavailable condition in **Artifacts and notes**. Never copy private EPUB text, secrets, local configuration, credentials, prompts, or evidence excerpts into this file.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete an earlier claim, command result, review finding, or handoff. Redact sensitive local details.

- **Implementation/PR:** No claim yet.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

M06 must consume this response rather than infer server behavior.

A claimant moves the lifecycle only through `planned → claimed → in progress → in review → complete`, or to `blocked` with the exact blocker, completion condition, and next owner. Before requesting review, update every artifact line above and confirm this task’s scope does not overlap an active claim.
