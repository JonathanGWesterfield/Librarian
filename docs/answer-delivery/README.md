# Modular answer delivery implementation roadmap

**Status:** Planned. This document is the burn-down index, not the protocol
specification. No milestone is complete until its listed evidence is merged and
linked from [#87](https://github.com/JonathanGWesterfield/Librarian/issues/87).

**Design source of truth:**

- [ADR 001: internal RPC transport](adr-internal-rpc-transport.md)
- [Answer delivery technical design](technical-design.md)
- [Compatibility and migration plan](compatibility-and-migration.md)
- [Acceptance charter](acceptance.md)

## Outcome

Librarian delivers the same grounded answer through buffered JSON and
progressive SSE. It retains current evidence floors and refusals: ten relevant,
distinct body-text citations for broad synthesis; two citations for bounded
explanations; one for a point fact; and a scoped refusal when evidence is weak.
Candidate progress never becomes answer prose before validation.

Every Librarian-owned inter-process boundary uses gRPC. In-process composition,
browser HTTP/SSE, and third-party vendor protocols remain the explicit
exceptions defined in [ADR 001](adr-internal-rpc-transport.md). gRPC is a
typed, observable contract choice, not a claim that it alone improves latency.

## Start gate

The design review found P0 and P1 gaps in the original roadmap. They are now
mapped to concrete prerequisites below. M02 and M03 must not begin until their
required M00/M01 deliverables have passed review.

| Review finding | Resolution and acceptance condition |
| --- | --- |
| P0: tracker pointed to an unpublished design | **M00:** merge this documentation set in a focused PR; #87 then links to the immutable files and contains status/evidence only. Until then, #87 must say implementation is blocked on documentation publication. |
| P0: migration inventory omitted callers | [Technical design inventory](technical-design.md#complete-boundary-and-migration-inventory) now enumerates chat, API and worker summary, metadata tag/genre, recommendation, evaluator, and every host CLI disposition. M03 migrates every supported Compose caller and rejects host Docker-broker execution before transport. |
| P0: trust/authentication deferred | [ADR 001](adr-internal-rpc-transport.md#local-compose-trust-model) fixes the single-host Compose exception: five named networks, role-specific Compose secret mounts, generated sanitized per-service config files, health identity, rotation, and the multi-host block. M03 proves isolation as well as authorization denial. |
| P1: incomplete proto and event semantics | The normative [v1 contract](technical-design.md#v1-grpc-contract) specifies canonical messages, fields, reservations, output matrix, typed error/status mapping, limits, and metadata. Its [compatibility handshake](technical-design.md#atomic-compatibility-handshake), evidence snapshot, and runtime lifecycle define the required implementation. M01 adds the canonical proto, JSON schema, generated stubs, and fixtures. |
| P1: overlapping broker RPCs | v1 has one unary `GenerationBroker.Generate`; no `ObserveGenerate`. The runtime owns progress. A broker stream needs a future ADR amendment and concrete consumer. |
| P1: unspecified cancellation and resource bounds | [Execution design](technical-design.md#admission-execution-cancellation-and-shutdown) selects `grpc.aio`, process-group ownership, cleanup escalation, and initial limits. M03 includes a real subprocess cancellation test. |
| P1: mixed-protocol rollout risk | [Compatibility plan](compatibility-and-migration.md) selects atomic Compose R2, an authenticated release/protocol/descriptor handshake, configuration validation, rollback, and HTTP retirement proof. |
| P1: toolchain/ownership absent | [Toolchain and ownership](technical-design.md#toolchain-and-ownership) specifies canonical proto ownership, generation, checked-in output, and CI drift/breaking checks. |
| P1: non-reproducible acceptance | The [acceptance charter](acceptance.md) separates tracked deterministic fixtures from local private-library Chrome UAT and specifies report evidence. |

## Milestones

| ID | Deliverable | Depends on | Status |
| --- | --- | --- | --- |
| M00 | Publish and approve the design source of truth | none | Complete ([#88](https://github.com/JonathanGWesterfield/Librarian/pull/88)) |
| M01 | Contract, toolchain, inventory audit, and deterministic fixtures | M00 | In progress ([M01a #89](https://github.com/JonathanGWesterfield/Librarian/issues/89)) |
| M02 | In-process answer-runtime extraction and parity | M01 | Not started |
| M03 | Atomic gRPC Codex-broker migration | M02 | Not started |
| M04 | Buffered JSON and progressive SSE delivery adapters | M03 | Not started |
| M05 | Configuration, capabilities, and feature off-switch | M04 | Not started |
| M06 | Web reducer and truthful progress UI | M04, M05 | Not started |
| M07 | Compatibility, failure, Chrome UAT, and independent review | M06 | Not started |
| M08 | Measured broker optimization | M03 baseline, M07 harness | Not started |
| M09 | Separate answer-runtime deployment decision | M07, M08 | Not started |
| M10 | Controlled rollout and operational handoff | M07–M09 | Not started |

### M00 — Publish and approve the design source of truth

Owner: architecture/documentation.

- [x] Merge the ADR, technical design, compatibility plan, acceptance charter,
  and this roadmap in one focused documentation PR.
- [x] Update #87 to link to the merged file paths and retain only milestone
  status, PR links, blockers, and acceptance reports.
- [x] Obtain architecture review approval for ADR 001 and the design's security,
  lifecycle, and resource decisions.

**Exit:** all source links resolve on `main`; #87 does not duplicate the
specification; M01 has an approved design baseline. This is the required remedy
for the unpublished-tracker P0.

### M01 — Contract, toolchain, inventory audit, and deterministic fixtures

Owner: contracts, configuration, and broker owners.

The first focused implementation slice,
[#89](https://github.com/JonathanGWesterfield/Librarian/issues/89), is complete
in [PR #90](https://github.com/JonathanGWesterfield/Librarian/pull/90): the
canonical protobuf source, checked-in Python bindings, reproducible generation,
and contract-drift tests. The second slice, [#91](https://github.com/JonathanGWesterfield/Librarian/issues/91),
is complete in [PR #92](https://github.com/JonathanGWesterfield/Librarian/pull/92):
the public event JSON Schema, generated TypeScript types, fixtures, and drift
gate. The third slice is complete in [PR #93](https://github.com/JonathanGWesterfield/Librarian/pull/93):
a versioned manifest and static tests account for every direct legacy generator
or judge construction and every API or host entry point before M03 migration
begins. The fourth slice is complete in [PR #94](https://github.com/JonathanGWesterfield/Librarian/pull/94):
the tracked synthetic answer-fixture bank and lifecycle checks required by the
acceptance charter. The fifth slice is complete in [PR #95](https://github.com/JonathanGWesterfield/Librarian/pull/95):
the base-descriptor compatibility gate required before a v1 protobuf change can
merge. The sixth slice is complete in [PR #96](https://github.com/JonathanGWesterfield/Librarian/pull/96):
the remaining R0 HTTP broker target is an explicit M03-removal exception and a
new runtime target is blocked in CI. The seventh slice is complete in
[PR #97](https://github.com/JonathanGWesterfield/Librarian/pull/97): it
generates and strictly validates the immutable, descriptor-bound release
manifest that M03 will package into every R2 image. The eighth slice is complete
in [PR #98](https://github.com/JonathanGWesterfield/Librarian/pull/98): it turns
the v1 admission matrix, size bounds, and non-OK status/detail mapping into
reusable contract code. The ninth slice is complete in
[PR #99](https://github.com/JonathanGWesterfield/Librarian/pull/99): it rejects
host CLI use of the private `docker_codex_broker` before a broker URL, client,
or provider process can be constructed. The tenth slice adds the remaining
deterministic prerequisites for that R2 boundary: resolver-owned, sanitized
per-role configuration; client-side capability validation; and a fixed-path
configuration-and-secret preflight. M03 wires those already-tested components
into the full role-and-secret admission rule. These slices do not implement a
broker, browser delivery, or Compose migration.

- [ ] Add the canonical v1 proto, public event JSON Schema, generated Python
  and TypeScript workflow, exact tool versions, and CI generation/drift and
  breaking-change checks described in the technical design.
- [ ] Turn each enumerated chat, summary, tag, genre, recommendation, worker,
  evaluator, and host-guard row into a testable migration ticket. Re-run the
  source/configuration inventory; a new call site blocks M03 until it is added
  to the matrix with a migration or pre-transport rejection.
- [ ] Add tracked synthetic corpus fixtures and contract tests from the
  acceptance charter. They must run without Docker, private books, credentials,
  or model access.
- [ ] Implement and validate the full proto and status/size rules, immutable
  release manifest, per-principal Compose secrets/networks, authenticated Health
  and capabilities handshake with client response validation, sanitized
  single-file config mounts, non-spoofable host guard, timeout/limit validation,
  log redaction, and deployment preflight specified by ADR 001 and the
  compatibility plan.
- [ ] Record a fresh baseline with the existing stack; label unavailable model
  or Docker conditions rather than synthesizing measurements.

**Exit:** a clean checkout generates and compiles contracts, detects descriptor
drift, passes every fixture, proves the full boundary inventory and host guards,
and demonstrates the secret/config-mount/network/handshake policy. Security and
configuration decisions are executable tests, not comments.

### M02 — In-process answer-runtime extraction and parity

Owner: answer-runtime and retrieval owners.

- [ ] Extract the current answer orchestration from `prepare_answer_question()`
  behind the ports and immutable evidence snapshot defined in the technical
  design. Keep the runtime in process.
- [ ] Preserve scoped refusal, citation validation, repair budget, source
  revision behavior, and final result semantics.
- [ ] Keep existing CLI/API entry points as thin facades and enforce dependency
  direction with focused tests.

**Exit:** old and new paths yield equivalent terminal results for deterministic
fixtures, including point, bounded, broad, refusal, source-change, and repair
cases. No broker transport or browser behavior changes in M02.

### M03 — Atomic gRPC Codex-broker migration

Owner: broker, API, summary/metadata workers, evaluator, and configuration
owners.

- [ ] Implement the unary v1 broker service, generated clients, authenticated
  Health and `GetCapabilities`, release-manifest enforcement, scheduler,
  process-group cleanup, deadlines, limits, and metrics.
- [ ] Migrate chat synthesis/selection/review, API summary/genre/recommendation,
  summary worker, metadata worker, and evaluator in the atomic
  Compose R2 release. Do not add a hidden HTTP fallback; host use is rejected
  before transport.
- [ ] Create the metadata-worker profile, role-specific secret mounts, named
  two-service broker networks, and broker-only egress network specified by the
  technical design.
- [ ] Apply the preflight, deployment, rollback, and HTTP retirement proof in
  the compatibility plan.

**Exit:** Compose proves every supported inventory row uses generated gRPC stubs
and each host row is rejected; secret/network isolation, rejected
identity/operation, incompatible release/version/descriptor, queue full,
deadline, unhealthy broker, and real subprocess cancellation behave as
specified. The old HTTP listener/client paths are removed, and rollback restores
the complete R0 stack rather than mixing it.

### M04 — Buffered JSON and progressive SSE delivery adapters

Owner: API delivery.

- [ ] Expose versioned event delivery as a serializer over the runtime iterator;
  collect that same iterator for `POST /chat`.
- [ ] Document every browser endpoint in `docs/api-endpoints.md` with examples
  and update `docs/openapi.json` in the implementation PR.
- [ ] Preserve the existing `/chat/stream` contract until separately deprecated.

**Exit:** fixture tests prove JSON/SSE terminal parity, correct frame decoding,
one terminal state, no raw draft, disconnect propagation, and first candidate
progress while fake generation is blocked.

### M05 — Configuration, capabilities, and off-switch

Owner: configuration and API composition root.

- [ ] Add `chat.delivery_mode` with buffered default, progressive opt-in, and a
  pre-admission disabled response.
- [ ] Publish a capability response containing only browser delivery mode and
  supported event schema versions.

**Exit:** both modes exercise the same gRPC broker and evidence policy. Invalid
or incompatible configuration fails before work starts; disabling events does
not reintroduce inter-service HTTP.

### M06 — Web reducer and truthful progress UI

Owner: web application.

- [ ] Isolate SSE parsing and state reduction behind the versioned event schema.
- [ ] Implement Stop, explicit retry, scope changes, stale-response protection,
  unknown-version handling, and accessible truthful stage indicators.

**Exit:** parser/reducer tests cover arbitrary UTF-8 boundaries, duplicate or
out-of-order events, corruption, early EOF, and all terminal outcomes. Drafts
never render as answers and candidates never appear as final citations.

### M07 — Compatibility, failure, Chrome UAT, and independent review

Owner: evaluation/integration; an independent reviewer completes the final step.

- [ ] Run deterministic contract/parity/cancellation suite.
- [ ] Run the acceptance charter in Chrome against the actual React UI and
  Compose/nginx stack for both delivery modes.
- [ ] Exercise full failure/migration cases, then conduct independent code and
  live-service review before the full test suite.

**Exit:** linked reports document citation quality, lifecycle, every caller
class, Health/auth/handshake, secret/network isolation, process cleanup, browser
delivery, and unavailable conditions. UAT comes before independent review, which
comes before the full suite.

### M08 — Measured broker optimization

Owner: provider broker; coordinate in [#86](https://github.com/JonathanGWesterfield/Librarian/issues/86).

- [ ] Measure channel connection, queue wait, broker startup/execution, provider
  work, review, repair, and terminal completion by query class.
- [ ] Change process lifetime or provider integration only when the measurements
  identify it as the bottleneck and the contract/cancellation guarantees hold.

**Exit:** reproducible before/after evidence demonstrates an improvement or a
documented no-go. Correctness and credentials are unchanged.

### M09 — Decide whether to deploy the answer runtime separately

Owner: architecture and operations; coordinate in [#83](https://github.com/JonathanGWesterfield/Librarian/issues/83).

- [ ] Review scaling, isolation, release, and ownership evidence.
- [ ] If extraction is justified, create a scoped issue and use
  `AnswerRuntime.Run` gRPC from its first deployment. If not, record the trigger
  that would reopen the decision.

**Exit:** a reviewed decision exists with parity, health, auth, cancellation,
and rollback evidence for the selected topology.

### M10 — Controlled rollout and operational handoff

Owner: API, web, and operations.

- [ ] Ship progressive delivery opt-in while buffered remains default.
- [ ] Publish operator recovery, gRPC health, secret rotation, cancellation,
  metric, and rollback instructions.
- [ ] Re-run Chrome UAT and timing samples before a later default change.

**Exit:** operators can roll back delivery mode without replaying work or
changing grounding policy. #87 links the final evidence and reconciles #74,
#83, and #86 without claiming unverified success.

## Release evidence

The [acceptance charter](acceptance.md) is normative. In short,
every behavior-changing milestone requires deterministic fixtures, actual Chrome
UAT where applicable, independent review, and full checks in that order.
Existing warm-eight-second and cold-thirty-second targets remain visible;
small-sample p95 values are descriptive until there is enough data for an SLA.

## Explicit deferrals

Public raw-token streaming, gRPC-Web, WebSockets, durable/replayable chat jobs,
message-bus integration, and a runtime microservice without a demonstrated need
are out of scope. They require their own design review and, when they change a
service boundary, an ADR amendment.
