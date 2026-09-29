# Principal design review: modular answer delivery and gRPC internals

**Review date:** 2026-09-29

**Decision at review time:** **Revise before starting behavior-changing work.**
This document records the original gaps. The linked ADR, technical design,
compatibility plan, acceptance charter, and roadmap now contain a remediation
pass pending independent senior re-review; M00 publication remains required
before M01/M03 code work begins.

## Scope reviewed

- [Modular answer delivery, gRPC internals, and SSE roadmap](modular-answer-streaming-roadmap.md)
- [README roadmap entry](../README.md)
- [Issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87)
- Current API stream implementation in
  [`apps/api/librarian_api/main.py`](../apps/api/librarian_api/main.py)
- Current Codex broker, configuration, generation, and evaluator call sites.

This is a design review, not an implementation plan. Findings identify the
decision, artifact, or proof an implementer needs before changing behavior.

## What is sound

- Keeping browser delivery as JSON/SSE and private service calls as gRPC is a
  sensible boundary. A browser is not an internal service, and gRPC-Web would
  not improve the broker boundary.
- Preserving complete-answer validation before showing prose correctly protects
  the grounding guarantee. Candidate progress can be useful without exposing
  unvalidated answer text.
- The roadmap calls out cancellation, bounded queues, health, proxy flushing,
  legacy compatibility, and Chrome acceptance. These are often omitted from
  streaming proposals.
- Deferring a separately deployed answer runtime until it has a scaling,
  isolation, or ownership justification avoids creating a microservice merely
  to carry SSE.

## Blocking findings

### P0 — The published tracker points to a design document that is not published

Issue #87 links to `main/docs/modular-answer-streaming-roadmap.md`, but the
roadmap is currently an untracked local file. A future implementer following the
issue reaches a missing document and cannot tell whether the issue copy or a
local draft is authoritative.

**Required correction:** publish the roadmap and this review in a focused
documentation PR before using #87 as the execution ledger, or make #87 fully
self-contained until that PR merges. Set one source of truth: the design lives
in versioned docs; the issue holds milestone state and links to evidence. Do not
maintain two independently edited copies of the detailed design.

### P0 — The gRPC migration inventory is incomplete

The roadmap treats the answer runtime as the broker's caller. The current
`docker_codex_broker` configuration instead presents the broker as a general
OpenAI-compatible HTTP endpoint
([configuration](../packages/librarian_config/config.py#L470)). It is used by:

- answer generation through `OpenAICompatibleGenerator`
  ([generation](../packages/librarian_chat/generation.py#L171));
- trusted semantic source selection and support review through the same
  generator ([chat](../packages/librarian_chat/chat.py#L1025)); and
- the separate evaluator container through `DockerCodexBrokerJudge`
  ([judge](../packages/librarian_evaluation/llm_judge.py#L228)).

Removing `/v1/chat/completions` after only the answer path migrates would break
those callers. Retaining it for them violates the stated rule that every
Librarian-owned inter-process boundary uses gRPC.

**Required correction:** M01 must produce a signed-off boundary inventory and
migration matrix. For every process/container caller, record its owner,
operation, current transport, target gRPC RPC, credentials, deadline,
cancellation behavior, test coverage, and removal condition. The first gRPC
broker contract must explicitly support the distinct operations that remain in
scope: grounded synthesis, semantic selection, support review, and evaluator
judging. Then M03 can switch all callers atomically and remove the HTTP route.

### P0 — The trust and authentication model is deferred too late

The roadmap says callers will use “short-lived or rotated secret metadata” and
defers TLS/mTLS versus a trusted Compose-network exception to M01. The current
broker uses a shared bearer token and an HTTP health endpoint
([broker](../apps/codex_broker/librarian_broker/main.py#L59)); Compose probes
that endpoint directly ([Compose](../docker-compose.yml#L98)). A private Docker
network is reachability control, not an identity or authorization model.

**Required correction:** before defining the proto or server, write a small
security decision record that answers all of the following:

1. Which identities may call the broker: API, answer runtime if extracted, and
   evaluator; which RPCs each identity may invoke; and whether calls can cross a
   host boundary.
2. The exact local-Compose transport posture: plaintext only on an isolated
   network, or TLS/mTLS; how the exception is constrained; and what changes for
   a multi-host deployment.
3. Token/credential storage, rotation, expiry, revocation, and log-redaction
   rules. “Short-lived or rotated” is a requirement, not a design.
4. The health/readiness protocol and Compose probe implementation after HTTP is
   removed. A process-ready probe must not assert that a Codex login or provider
   request is healthy unless that is intentionally part of readiness.

Do not make M03 choose these during coding.

## Major findings

### P1 — The proposed proto surface is a sketch, not an implementable contract

Two service names and four RPC signatures are insufficient to generate
interoperable clients. The design does not yet define message fields, `oneof`
cases, required versus optional semantics, size limits, error/status mapping,
or compatibility behavior. It also does not settle whether `completed` carries
the authoritative answer, whether `answer_validated` carries the same payload,
or how a refusal differs from an operational failure.

The text contains a tension: it permits unknown additive data fields but says
unknown event types must be rejected. That can be correct, but only with a
precise envelope/version policy shared by proto and SSE clients.

**Required correction:** make a versioned contract specification the M01
deliverable. It must define, at minimum:

- request identity, immutable scope, delivery mode, deadline, correlation ID,
  idempotency/retry position, and admission outcome;
- `AnswerEvent` envelope with event sequence, terminal-state rules, and a
  closed `oneof` for event payloads;
- `CandidateEvidence` identity, source revision/content hash, provenance,
  allowed excerpt size, and final-citation relationship;
- one canonical `AnswerResult` referenced by `answer_validated` and
  `completed`, including refusal and generation-unavailable outcomes;
- a mapping from gRPC status plus typed error detail to safe domain outcomes and
  public SSE/JSON errors; and
- protobuf and browser-schema evolution rules, including field reservations,
  unknown-field behavior, deprecation windows, and test fixtures.

Put the complete proto and normative lifecycle table in that document. The
roadmap should link to it instead of being the only location where semantics
are described.

### P1 — `Generate`, `ObserveGenerate`, and `AnswerRuntime.Run` overlap

`Generate` is unary, `ObserveGenerate` is an optional server stream, and
`AnswerRuntime.Run` is another server stream. The design does not identify who
calls `ObserveGenerate`, whether it starts a second provider operation, which
stream is authoritative, or why lifecycle observation requires a second RPC.
gRPC cancellation already applies to a unary RPC context; an extra streaming
RPC is not needed merely to cancel a request.

**Required correction:** select one broker interaction model for v1 and state
its lifecycle. The simplest defensible first contract is a single unary,
structured `Generate` RPC with propagated deadline/cancellation and runtime
emitted stage events. Add broker streaming only after a concrete provider
capability and consumer need is demonstrated. If a broker stream is retained,
define its request ownership, terminal message, backpressure, duplication
prevention, and how its event sequence relates to `AnswerRuntime.Run`.

### P1 — Evidence provenance is underspecified across the new boundary

The answer runtime is intentionally separated from SQLite/OpenSearch, but it
still owns citation validation. Sending only mutable chunk IDs across a port is
not enough to prove that the cited text is the text retrieved and reviewed,
especially while search/index synchronization work remains separate.

**Required correction:** define an immutable evidence snapshot contract before
extracting the runtime. Each candidate/final citation needs a stable book and
chunk identity, source revision or content hash, body-text eligibility result,
scope, and bounded excerpt policy. Define what happens when the source of truth
changes between retrieval and final validation. The #78 dependency can remain a
separate project, but its consistency invariant cannot remain implicit.

Also decide whether raw candidate excerpts leave the server before validation.
Progress needs counts and stage names; excerpts should be intentionally
permitted, size-bounded, and treated as local book content rather than added by
accident to an event payload.

### P1 — Cancellation and resource controls cannot be inferred from the current broker

The existing broker calls `subprocess.run(..., timeout=240)`
([broker](../apps/codex_broker/librarian_broker/main.py#L108)). It has no
request-level cancellation hook, process-group policy, or bounded execution
queue. A cancelled gRPC request will not automatically stop that child process.
The roadmap requires “no orphan process” and cancellation propagation without
specifying the execution model needed to prove either claim.

**Required correction:** M01 must decide and document the broker execution
model before M03: async/synchronous server model, process-group ownership,
termination escalation and grace period, max concurrent Codex executions,
admission versus queue deadlines, fair scheduling, shutdown behavior, and the
observable outcome when the provider cannot be cancelled. The implementation
must include a real process-level cancellation test, not only a fake generator
test.

### P1 — Rollout and compatibility lack an atomic migration plan

The rule forbids an HTTP fallback, while M03 asks to remove the HTTP route only
after an audit. There is no deployment sequence for changing the broker, API,
and evaluator together without leaving a mixed-version Compose deployment.
The switch from static HTTP configuration to generated gRPC clients also has no
configuration migration or downgrade story.

**Required correction:** add a compatibility matrix covering broker version,
API/runtime version, evaluator version, delivery mode, and expected action. For
the local Compose topology, specify whether M03 is an atomic stack release or
uses a temporary dual-protocol *release compatibility period*. If the latter is
necessary, it is an explicit, time-boxed exception to the gRPC rule with an
owner, removal version, and test; it must not become an untracked fallback.

### P1 — Build and ownership decisions are missing from the contract plan

The current Python projects declare no gRPC/protobuf toolchain. “Select a
pinned toolchain” is necessary but not sufficient: the design does not specify
the canonical proto directory owner, generation command, generated-code policy,
runtime dependency location, Docker build step, lint/breaking-change check, or
how browser JSON types derive from the service contract without making the web
client a gRPC client.

**Required correction:** M01 must select one reproducible toolchain and record
it in the formal design. Include a clean-checkout command that generates all
needed artifacts, CI drift detection, a breaking-change check, and package
dependency direction. Keep browser event JSON as a public projection with its
own schema; do not claim it is automatically equivalent to proto merely because
both are generated from nearby files.

### P1 — The release evidence is not yet reproducible enough for correctness

The acceptance gate correctly requires Chrome UAT and real model behavior, but
the planned question bank depends on ignored local EPUBs and local provider
state. An implementer cannot reproduce the grounding claims from a clean clone.
Twenty warm requests also make a reported p95 largely an extreme sample, which
is useful diagnostic data but not a strong release statistic.

**Required correction:** define two explicit suites:

1. A tracked, deterministic fixture corpus with machine-checked expected scope,
   outcome, citation IDs, and event lifecycle. It gates contract, parity,
   cancellation, and regression behavior in CI.
2. A local UAT charter for private EPUBs and the configured Codex account. It
   records environment, model, commit, questions, results, timings, and any
   unavailable condition without exposing book text or credentials.

Keep the required broad/point/insufficient-evidence cases in both suites. State
that timing samples are descriptive until enough observations exist for a
service-level target.

## Material design improvements

### Create a formal design set before M02

The present roadmap combines rationale, protocol, event semantics, operational
rules, acceptance criteria, and a burn-down. That makes it hard to review or
change safely. Create these versioned documents:

| Artifact | Purpose | Must be approved before |
| --- | --- | --- |
| `docs/adr/NNN-internal-rpc-transport.md` | gRPC boundary rule, explicit third-party and in-process exceptions, alternatives, consequences, and amendment process | gRPC dependencies or code |
| `docs/design/answer-delivery.md` | Component boundaries, authoritative lifecycle, full proto/public-schema references, security, deployment, resource limits, failure behavior, and observability | M02 |
| `docs/design/answer-delivery-compatibility.md` | API/broker/evaluator version matrix, migration sequence, rollback, and HTTP-route retirement | M03 |
| `docs/acceptance/answer-delivery.md` | Tracked fixture suite, local Chrome UAT charter, required evidence, and reporting format | M04 |

Issue #87 should then retain milestone status, PR links, and acceptance reports
only. The existing roadmap becomes the high-level index and dependency map.

### Add a boundary registry

The statement “all inter-service communication uses gRPC” needs an auditable
definition. Add a small table to the design that lists every boundary and its
approved transport:

| Caller | Callee | Boundary type | Allowed transport | Exception/owner |
| --- | --- | --- | --- | --- |
| API delivery | in-process runtime | same process | direct interface | composition root |
| API/runtime/evaluator | Codex broker | Librarian service | gRPC | none |
| Retrieval adapter | OpenSearch/Ollama | third-party product | vendor API | adapter owner |
| Browser | API delivery | public client API | HTTPS JSON/SSE | API owner |

Make the migration inventory an extension of this table. Add a CI-oriented
check for known prohibited targets such as `http://codex-broker` outside the
retired compatibility code, then use code review to enforce the broader rule.

### Re-sequence the burn-down

M01 currently asks one milestone to settle the protocol, security, contracts,
toolchain, configuration, dependencies, test commands, numeric defaults, and
baseline. Split it so each result can be reviewed:

1. **M00 — Publish design source of truth and ADR.** Fix the broken tracker
   link; approve the boundary registry and trust model.
2. **M01 — Contract and toolchain baseline.** Freeze the initial proto/public
   event semantics, generated-code workflow, and reproducible fixtures.
3. **M02 — In-process runtime extraction.** Demonstrate behavioral parity with
   no transport change.
4. **M03 — Complete broker migration.** Replace HTTP for every inventoried
   client in one compatible release and prove cancellation/health/security.
5. **M04–M10 — Delivery adapters, UI, acceptance, measured optimization, and
   deployment decision.** Keep their existing intent, but require the preceding
   design artifacts as inputs.

This separation makes it possible to reject a contract/security decision
without mixing that decision with a large runtime refactor.

## Required decisions checklist for the next implementer

Do not open M02 or M03 until each item has an approved answer in the formal
design:

- [ ] Boundary inventory includes API, runtime, evaluator, selector, support
  review, and all broker clients.
- [ ] One gRPC broker operation model is selected; streaming has a concrete
  consumer and no duplicate-work path.
- [ ] Proto message, event, error, versioning, evidence snapshot, and public
  SSE projection specifications are complete.
- [ ] Authentication, authorization, local transport encryption exception,
  health/readiness, secret rotation, and log-redaction policies are decided.
- [ ] Cancellation reaches a real Codex subprocess with defined process cleanup
  and an integration test.
- [ ] Queuing, concurrency, deadlines, fairness, and shutdown are numerically
  bounded and tied to the eight/30-second user targets.
- [ ] Compose/CI toolchain and migration/rollback matrix are reproducible from
  a clean checkout.
- [ ] Tracked deterministic fixtures and separate private-library UAT evidence
  are defined.

## Approval condition

Approve the architecture for M02 only when the formal design set resolves every
P0 and P1 finding, its links are published from #87, and the M01 contract
fixtures pass in a clean checkout. The existing roadmap can then remain the
useful burn-down it is intended to be, rather than serving as the only
specification for a cross-process protocol change.
