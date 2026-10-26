# M03 · Generated client lifecycle and compatibility validation

- **Task ID:** `AD-M03-08`
- **Milestone:** [M03](README.md) · task status does not advance milestone status.
- **Lifecycle status:** **complete**
- **Claim record:** **Archived / non-claimable.** This completed historical record may be reopened only by a new task or an approved decision linked in its append-only log.
- **Progress ledger:** [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)

## Immutable scope and goal

Create one generated `grpc.aio` channel/stub per caller process and validate capabilities/manifest before admission.

## Prerequisite task IDs and ordered dependencies

- **Implementation:** [AD-M01-01](../M01/01-proto-and-python-bindings.md), [AD-M01-07](../M01/07-stack-release-manifest.md), and [AD-M01-10](../M01/10-sanitized-runtime-config.md) complete.

## Execution class, owned paths, and forbidden paths

- **Execution class:** `archived historical record`.
- **Exclusive owned paths:** none; archived historical record is non-claimable.
- **Forbidden paths:** all implementation, test, and configuration paths; create a new follow-up task for any reopening.

## Design anchors

- **Read first — [program outcome](../../../answer-delivery/README.md#outcome) and [component/dependency direction](../../../answer-delivery/technical-design.md#components-and-dependency-direction).** These define the grounded-answer, in-process-runtime, browser-HTTP/SSE, and internal-gRPC boundaries that every slice preserves.

**Direct requirements for this task:**
- [Atomic compatibility handshake](../../../answer-delivery/technical-design.md#atomic-compatibility-handshake)
- [v1 gRPC contract](../../../answer-delivery/technical-design.md#v1-grpc-contract)
- [Version matrix and enforced handshake](../../../answer-delivery/compatibility-and-migration.md#version-matrix-and-enforced-handshake)
- [ADR health and readiness](../../../answer-delivery/adr-internal-rpc-transport.md#health-and-readiness)

## Acceptance criteria

Every caller validates SHA, major/minor range, descriptor, and required operations; disagreement is `CONTRACT_MISMATCH`.

## Required tests and evidence

Run generated-client and negative handshake tests.

## Append-only log, artifacts, and notes

Append dated entries; never rewrite or delete earlier claims, commands, review findings, or handoffs.

- **Implementation / merged PR / SHA:** Merged implementation provenance is the roadmap’s documented [PR #104–#111 range](https://github.com/JonathanGWesterfield/Librarian/pulls?q=is%3Apr+is%3Aclosed+104+105+106+107+108+109+110+111); exact slice-to-PR mapping was not retained and must not be inferred.
- **Commands and results:** _Not recorded._
- **Reports / screenshots:** _Not recorded._
- **Review findings and repairs:** _Not recorded._
- **Blockers / decisions:** _Not recorded._

## Handoff

Caller-specific tasks consume this adapter; do not reopen HTTP fallback.

Move only through `planned → claimed → in progress → in review → complete`, or to `blocked` with its exact condition. A task is complete only when its merged PR and required evidence are linked; unmerged work never advances the milestone. When the slice changes milestone state, blocker, or next eligible work, update the roadmap table and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) in that PR.
