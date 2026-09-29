# ADR 001: Use gRPC for Librarian-owned service boundaries

**Status:** Accepted as a planning constraint; implementation begins only after
M01's contract and toolchain gate passes.

**Date:** 2026-09-29

**Related:** [answer-delivery design](../design/answer-delivery.md), and
[roadmap](../modular-answer-streaming-roadmap.md).

## Context

Librarian currently has a private, Docker-resident Codex broker with an
OpenAI-compatible HTTP endpoint. The default `docker_codex_broker` generation
configuration reaches chat answer generation, semantic source selection,
support review, book summaries, tags, genres, recommendations, the summary
worker, and the evaluator. Host CLI entry points can also inherit that default,
although the broker has no host port. The user wants every Librarian-owned,
inter-process boundary to use gRPC for a typed, versioned contract and
measurable lifecycle behavior.

The browser remains a public client. OpenSearch and Ollama are independently
owned products, and Codex is presently a CLI subprocess. Their adapters do not
become Librarian services merely because they are called by one.

## Decision

Every **Librarian-owned, inter-process** call uses Protocol Buffers and gRPC.
The v1 Codex broker contract has one provider-execution RPC,
`GenerationBroker.Generate`, plus an authenticated, non-execution
`GetCapabilities` compatibility check. `Generate` supports the exhaustive
operation matrix in the technical design: grounded synthesis, semantic source
selection, support review, evaluator judgement, chapter/book summarization,
tag generation, genre generation, and recommendation synthesis. A caller sets
one operation; the broker performs one provider execution and returns one
typed result. There is no `ObserveGenerate` RPC in v1.

The answer runtime is initially an in-process component. If it is later
deployed as a process, API-to-runtime calls use `AnswerRuntime.Run` gRPC, a
server-streaming event RPC. Browser SSE remains an API-owned projection of the
same domain events; the browser is not a gRPC client.

## Boundary policy

| Caller | Callee | Boundary | Required transport | Owner / exception |
| --- | --- | --- | --- | --- |
| API delivery | in-process answer runtime | same process | direct Python interface | API composition root |
| API answer path | Codex broker | Librarian service | gRPC | none |
| API semantic selection | Codex broker | Librarian service | gRPC | none |
| API support review | Codex broker | Librarian service | gRPC | none |
| API summary, tag, genre, recommendation | Codex broker | Librarian service | gRPC | none |
| summary worker | Codex broker | Librarian service | gRPC | none |
| metadata worker | Codex broker | Librarian service | gRPC | none |
| evaluator container | Codex broker | Librarian service | gRPC | none |
| future answer runtime | Codex broker | Librarian service | gRPC | none |
| host CLI with Docker broker selected | Codex broker | invalid topology | rejected before transport | configuration owner |
| browser | API delivery | public client interface | HTTPS JSON and SSE | API delivery owner |
| retrieval adapter | OpenSearch or Ollama | third-party product | vendor-native API | retrieval owner |
| broker | Codex CLI | local executable | subprocess interface | broker owner |

No new or retained HTTP endpoint may serve an owned service boundary after M03.
The current `/v1/chat/completions` broker route is retired in the M03 atomic
release. A temporary dual-protocol period would require a new ADR amendment,
an owner, a removal release, a test, and an issue entry before it is added.

## Local-Compose trust model

The initial single-host Compose deployment uses plaintext gRPC **only** over
four dedicated, `internal: true` two-service networks: broker/API,
broker/summary-worker, broker/metadata-worker, and broker/evaluator. The broker
is not on the normal application network, exposes no host port, and is the only
service on a separate non-internal egress network needed by Codex. This gives
each caller reachability only to its own private broker path. Every RPC,
including health probes, presents a caller credential in gRPC metadata. The
broker maps a credential to one principal and permits only that principal's
operations:

| Principal | Permitted operation |
| --- | --- |
| `api` | synthesis, semantic selection, support review, chapter/book summary, tags, genres, recommendations |
| `summary-worker` | chapter/book summary |
| `metadata-worker` | tags and genres |
| `evaluator` | evaluator judgement |
| `answer-runtime` | synthesis, semantic selection, support review when extracted |
| `compose-health` | Health and capability check only |

Each principal has a separate random secret under ignored `config/secrets`, but
it is mounted with a Docker Compose `secrets` declaration only into the broker
and its one caller at `/run/secrets/<role>`. The API cannot read evaluator or
worker secrets; workers cannot read each other's secrets. Shared configuration
is resolved into one sanitized, single-file runtime JSON per service; no R2
container recursively mounts `config/`, `config/secrets/`, or an ancestor.
Runtime JSON contains logical role/target data but no secret values,
`api_key_file`, or secret paths. Credentials are sent in the `authorization`
metadata key; the broker derives identity from that value and ignores a
caller-name header. A Docker-broker client requires matching sanitized role,
environment role, and exact non-symlink `/run/secrets/codex-broker-<role>`
mount before constructing a target; an environment variable alone is not
admission. Payloads never contain credentials. Logs redact authorization
metadata, prompts, excerpts, and provider stderr that might contain either.

Initial rotation is an atomic, planned Compose restart: create a new credential,
replace the caller and broker secret files, recreate the affected services, and
invalidate the old value. There is no claim of seamless rotation or expiry in a
single-host deployment. A multi-host or host-published deployment is forbidden
until a follow-on ADR selects TLS plus mutual service authentication, certificate
issuance/rotation, and revocation.

## Health and readiness

The broker implements the standard gRPC Health `Check` service. Its health
secret is mounted in the broker only because the Compose health check runs in
that container; the derived `compose-health` principal may call Health and
Capabilities but cannot call `Generate`. `SERVING` means configuration and
credential material are valid and the bounded scheduler can admit work. It does
not claim that a Codex login or a remote model is available. Liveness only
asserts that the process can serve the health RPC. Provider availability is an
operation outcome and metric.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Keep the broker's OpenAI-compatible HTTP API | It leaves an owned inter-process boundary untyped and conflicts with the stated transport policy. |
| Use gRPC-Web in the browser | It adds a proxy and public transport without changing the owned broker boundary. |
| Put a gRPC-to-HTTP sidecar in front of the current broker | It adds a hop but leaves the broker's owned contract as HTTP. |
| Make the answer runtime a microservice now | SSE does not require a service boundary; extraction needs an operational reason. |

## Consequences

M01 must add a reproducible protobuf/gRPC toolchain, source-owned contracts,
generated Python stubs, health support, typed error handling, descriptor
fingerprinting, and contract drift checks. M03 must migrate every row in the
boundary registry in one atomic release, including summary/metadata workers and
the evaluator, before removing the HTTP listener. An authenticated capability
handshake compares release SHA, protocol range, and descriptor digest before a
client admits work; an R0/R2 or otherwise mixed stack is refused.

gRPC is an interface and lifecycle decision, not a latency guarantee. M08 must
measure connection, queue, broker, provider, review, and repair time before
claiming an improvement.

## Amendment rule

An exception needs an ADR amendment that names the exact boundary, rationale,
security implications, owner, expiry release/date, removal test, and linked
issue. Code review rejects undocumented `http://codex-broker` targets and any
new owned HTTP service endpoint.
