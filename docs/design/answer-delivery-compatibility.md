# Answer-delivery compatibility and migration plan

**Status:** Proposed. This plan is a prerequisite to M03, not permission to run
HTTP and gRPC indefinitely.

**Related:** [ADR 001](../adr/001-internal-rpc-transport.md),
[technical design](answer-delivery.md), [acceptance charter](../acceptance/answer-delivery.md),
and [roadmap](../modular-answer-streaming-roadmap.md).

## Compatibility promise

`POST /chat` retains buffered JSON behavior. The existing `/chat/stream` route
retains its current framing until a separately reviewed public API deprecation.
New `POST /chat/events` SSE uses the v1 event schema. All delivery paths execute
one runtime and apply the same grounding rules.

The Codex broker is internal-only. Its HTTP OpenAI-compatible endpoint has no
public compatibility promise and is removed during M03 after all known callers
migrate. The selected rollout is an **atomic Compose release**, never an
indefinite dual-protocol period.

## Version matrix and enforced handshake

| Stack version | API/runtime | broker | summary/metadata workers | evaluator | Expected action |
| --- | --- | --- | --- | --- | --- |
| R0 current | HTTP client | HTTP broker | configured HTTP generator when a worker runs | HTTP judge | current baseline only |
| R1 M01/M02 | no behavior change | HTTP broker | HTTP generator | HTTP judge | build contracts and prove in-process parity |
| R2 M03 | generated gRPC client | gRPC only | generated gRPC clients | generated gRPC client | deploy all five together; legacy/mixed combinations are refused |
| R3 M04–M10 | R2 plus JSON/SSE adapters | gRPC only | gRPC clients | gRPC client | buffered default, progressive opt-in |

R2 does not support an R0 API, worker, or evaluator talking to an R2 broker,
nor an R2 client talking to an R0 broker. It does not rely on an informal
launcher check. Every R2 image contains the same immutable
`librarian-stack-contract.json` with a clean source Git SHA, `v1` major/minor,
and the canonical descriptor SHA-256. At startup each API, summary worker,
metadata worker, and evaluator sends its manifest to authenticated
`GenerationBroker.GetCapabilities`. The broker requires:

1. a credential which grants the caller the control-plane RPC;
2. equal 40-character release SHA in request body, metadata, and its own
   manifest;
3. major `1`, a minor within the broker's advertised inclusive range; and
4. an exact descriptor digest match.

On any disagreement the broker returns `FAILED_PRECONDITION` and
`ErrorDetail.CONTRACT_MISMATCH`; API marks itself unready and rejects browser
admission, while worker/evaluator exits before it claims work. The broker makes
the same release/descriptor checks on every `Generate`, so a stale client cannot
continue after a broker replacement. Standard gRPC Health is only a liveness and
scheduler check; it does not substitute for this handshake. Each client also
validates every returned capability value itself: major, inclusive minor range,
descriptor digest, release SHA, and its required operations. Any missing or
different value is `CONTRACT_MISMATCH` and keeps that client unready.

## Configuration and Compose migration

M03 replaces the HTTP broker URL/key configuration with a versioned, non-secret
broker section in the user-owned JSON configuration:

```json
{
  "services": {
    "codex_broker": {
      "transport": "grpc",
      "target": "dns:///codex-broker:50051",
      "contract_major": 1,
      "credential_role": "process-assigned"
    }
  }
}
```

`credential_role` must agree with the runtime role manifest and is not
operator-selectable. Compose assigns one principal and one secret file per
process. The configuration contains no token value and no path that grants
access to another principal's token. The implementation reads only its
`LIBRARIAN_BROKER_CREDENTIAL_FILE` mount under `/run/secrets`. Docker supplies
`dns:///codex-broker:50051`; it is neither browser nor host setting. A profile
selecting `docker_codex_broker` rejects the retired HTTP base URL after R2, and
rejects host execution unless the logical role, environment role, and exact
non-symlink `/run/secrets/codex-broker-<role>` mount agree. An environment
variable alone is insufficient. Other external OpenAI-compatible providers
retain their provider behavior but receive a distinct role-specific Compose
secret; their input `api_key_file` is consumed by the resolver and stripped from
the runtime JSON.

The R2 Compose manifest declares five `codex-broker-*` secrets and the five
named networks in the technical design. It mounts each caller's one secret only
into that caller and broker, attaches API/summary/metadata/evaluator only to
their own broker network, keeps broker off `application`, adds the
`metadata-worker` profile, and gives broker alone the dedicated egress network.
The resolver emits exactly one sanitized runtime JSON per container and Compose
bind-mounts only that file, never `./config`, `config/secrets`, or an ancestor.
The R2 health check is an authenticated in-container gRPC Health call using the
health secret. `docker compose config`, a rendered mount/network assertion, and
an in-container assertion that `/config/secrets` is absent are release gates,
not documentation-only checks.

Before R2, the launcher creates timestamped local backups of the ignored
configuration file and role-specific secret files, validates the R2 shape and
required secret readability, and fails before stopping the current stack if
anything is missing. It does not partially migrate configuration or secrets.

## Atomic deployment and rollback

1. Build API, broker, summary worker, metadata worker, evaluator, and contracts
   from one clean Git SHA. Fail the build if the stack manifest SHA or descriptor
   digest differs from compiled artifacts.
2. Run contract fixtures, generator drift checks, and the R2 Compose
   interoperability suite, including every principal/operation and secret-mount
   assertion, before touching the local stack.
3. Stop new browser admission; let existing R0 requests finish or cancel them
   after the documented drain period.
4. Back up and validate local configuration and role-specific secret files;
   build/recreate broker, API, summary worker, metadata worker, and evaluator
   together. Broker has gRPC only and no host port.
5. Wait for authenticated Health. Require authenticated API, summary, metadata,
   and evaluator `GetCapabilities` calls with the release manifest; API reports
   ready only after its own call succeeds.
6. Run deterministic smoke work for chat, summary, tag, genre, recommendation,
   and evaluator. Admit browser traffic only if all pass.
7. If deployment fails, stop the entire R2 stack, restore R0 images,
   configuration, and role-specific secrets as one operation, then confirm the
   R0 baseline. Do not point R2 clients at an R0 HTTP service or add an ad-hoc
   fallback.

Delivery-mode rollback is separate: changing `chat.delivery_mode` from
`progressive` to `buffered` leaves the R2 gRPC broker in place and cannot lower
evidence requirements or replay a request.

## HTTP retirement proof

M03 may remove the old HTTP route only when all are true:

- the boundary inventory in the technical design is marked migrated with tests;
- chat synthesis, semantic selection, support review, summary, tag, genre,
  recommendation, summary worker, metadata worker, and evaluator use generated
  gRPC stubs in a Compose test, or the documented host guard rejects the path;
- the broker image exposes no HTTP route or port and Compose health uses gRPC;
- configuration validation rejects an HTTP broker URL and host Docker-broker
  execution for this mode;
- every principal completes `GetCapabilities` against the matching manifest,
  while old API/worker/evaluator manifests are rejected with
  `CONTRACT_MISMATCH` before admission;
- rendered Compose configuration proves per-principal secret mounts and private
  network membership, and negative in-container reads prove isolation;
- a repository scan has no `http://codex-broker` target outside an approved ADR
  amendment; and
- R2 rollback succeeds from documented local backups without data migration.

## Public event evolution

Browser event schema v1 remains additive within its major version. A client
ignores unknown fields inside a known event, rejects unknown event types or
unsupported majors, and treats EOF without a terminal event as interruption.
An event-route deprecation requires a documented supported-version window,
capability response, README/API documentation, and a migration test. The event
projection is not a direct gRPC-to-browser bridge.
