# Answer-delivery acceptance charter

**Status:** Required for M01 fixtures and M04–M10 acceptance.

**Related:** [technical design](technical-design.md),
[compatibility plan](compatibility-and-migration.md), and
[roadmap](README.md).

## Two required suites

CI and local UAT answer different questions. Neither substitutes for the other.

| Suite | Data and provider | Gates | Evidence retained |
| --- | --- | --- | --- |
| Tracked deterministic fixtures | Small synthetic corpus and fake provider responses in `tests/fixtures/answer_delivery/v1/` | contract semantics, event lifecycle, parity, cancellation, migration | test output and checked-in fixture IDs only |
| Local Chrome UAT | Ignored private EPUBs, configured broker/Codex account, actual React UI through Compose/nginx | usefulness, citation relevance, browser delivery, real operational behavior | redacted report; no EPUB text, secrets, or local config |

## Deterministic fixture suite

M01 adds cases with fixed request IDs, source revisions, candidate IDs, provider
responses, expected `AnswerResult`, and event sequence. Fixtures contain only
synthetic passages. The minimum bank is:

| Case | Required result |
| --- | --- |
| point fact | accepted answer with one final body-text citation |
| bounded explanation | accepted answer with two distinct final citations |
| broad synthesis | readable answer with ten distinct, relevant final citations |
| insufficient evidence | scoped refusal, no model call, no purported final citations |
| wrong scope | refusal plus eligible whole-library retry option |
| stale source revision or content hash | reload by book/chunk proves exact revision **and** SHA mismatch yields `source_changed`, no final citation |
| malformed provider structure | one bounded repair then generation-unavailable |
| broker unavailable / deadline / queue full | safe terminal outcome mapped from gRPC status |
| cancellation | one `cancelled` terminal event and no late completion |
| oversized request, message, excerpt, snapshot, or result | `INVALID_ARGUMENT` before queue admission, or domain `TOO_LARGE` for an otherwise valid model result |
| unspecified / unknown enum and operation-output mismatch | `INVALID_ARGUMENT`, no provider process, no retry |
| incompatible major, minor, descriptor, or release SHA | `FAILED_PRECONDITION` with `CONTRACT_MISMATCH`, no admission |

Tests must assert the complete state table: monotonic sequence numbers, one
terminal event, `answer_validated` only for an accepted result, identical
terminal JSON and SSE results, no raw draft token, and split UTF-8/CRLF SSE
decoding. They also verify that unauthenticated and wrongly authorized callers
cannot invoke a broker operation.

The cancellation integration test runs a real child process that records its
PID, waits on a controlled latch, then proves it and its process group are gone
after the RPC is cancelled. A fake provider test may supplement this test but
cannot replace it.

### Inventory, authorization, and compatibility coverage

M03's deterministic and Compose suites test every disposition in the technical
design inventory. The generated-client suite covers API chat synthesis,
selection, support review, chapter/book summary, genres, recommendation,
summary-worker summary, metadata-worker tag/genre, and evaluator judgement. A
parameterized authorization suite tries every operation with every principal;
only the approved cells in the operation matrix may reach the fake provider.

The Compose suite asserts the rendered network and secret topology as well as
behavior:

- `api` contains only `/run/secrets/codex-broker-api`; it cannot read evaluator
  or worker secret paths and cannot join their private networks;
- every R2 service receives only its generated
  `/config/librarian.json`; recursive `config/`, `config/secrets/`, and ancestor
  mounts are absent, `/config/secrets` is unreadable/nonexistent, and no runtime
  JSON contains `api_key_file` or another principal's secret path;
- summary and metadata workers receive only their own credential and are denied
  each other's operations;
- evaluator is denied every API/worker operation, and an unauthenticated
  request is denied before queue admission;
- the broker has no HTTP listener/host port, while `compose-health` can call
  Health/Capabilities but cannot call `Generate`; and
- API, summary worker, metadata worker, and evaluator complete a matching
  capabilities handshake. For each client, a different release SHA, descriptor
  hash, out-of-range minor, and wrong major produces `CONTRACT_MISMATCH` before
  browser admission/job claim/evaluation.

The host-entrypoint suite invokes each listed host CLI with
`docker_codex_broker` selected and no Compose secret mount. It repeats the test
with a forged `LIBRARIAN_EXECUTION_PRINCIPAL=api`. Both attempts must fail before
opening a broker target/channel, direct HTTP URL, or provider subprocess, and
direct the operator to a named Compose profile or another provider. Positive
container tests prove each valid principal has the matching role in sanitized
runtime JSON and exactly its expected non-symlink `/run/secrets` file.

### Reproducible commands and retained evidence

M01 adds the following commands with these stable names; a review cannot mark a
milestone complete until they exist and match this charter. They are intentionally
separate from the private-library UAT.

```sh
scripts/test.sh tests.contracts.test_answer_delivery tests.broker.test_grpc tests.api.test_answer_delivery
VERIFY_PROJECT=librarian-answer-delivery-r2 \
  ANSWER_DELIVERY_REPORT_DIR=/tmp/librarian-answer-delivery-r2 \
  scripts/run_answer_delivery_compose.sh
```

The first command runs fixtures, proto/descriptor drift, status/size validation,
host guards, and in-process cancellation without Docker, credentials, a model,
or private books. The second command builds the R2 Compose stack with the
`codex-broker`, `workers`, `metadata-workers`, and `evaluation` profiles;
executes the principal/operation, secret-mount, network, handshake, migration,
and real-subprocess tests; and writes only the following redacted artifacts:

```text
/tmp/librarian-answer-delivery-r2/compose-summary.json
/tmp/librarian-answer-delivery-r2/authorization.json
/tmp/librarian-answer-delivery-r2/compatibility.json
/tmp/librarian-answer-delivery-r2/cancellation.json
```

The script fails if Docker is unavailable, a required profile is unhealthy, a
report would include a secret/source excerpt, or a required assertion is skipped.
It always performs its own `docker compose down` for `VERIFY_PROJECT` and leaves
the developer's normal stack untouched. M03 adds a checked-in invocation and
expected-schema test for this script; operators must not approximate it with a
manual Compose command.

## Local Chrome UAT

After the R2 Compose harness passes, run the user-acceptance agent in Chrome
against the actual React UI through the same Compose/nginx path used by the
user. The M04+ launcher command is:

```sh
scripts/start_local.sh --with-workers --with-metadata-worker
```

The implementation extends this command to load the R2 profiles and perform the
authenticated API capability preflight before opening the browser. Do not accept
a direct API client in place of Chrome. Before each run, record the Git SHA,
branch, image IDs, delivery mode, redacted configuration fingerprint, model
identity, fixture/UAT corpus label, start condition (cold or warm), and local
service health.

Exercise buffered and progressive modes with:

- a tightly scoped character or identity question;
- a bounded explanation;
- a broad scoped synthesis that has at least ten relevant, distinct body-text
  citations and readable, original prose;
- an insufficient-evidence question that refuses rather than using priors;
- wrong-book scope followed by explicit whole-library retry;
- a typo/retry path; and
- Stop during retrieval, generation, and review, followed by a new question.

For progressive mode, prove in the UI that candidate/progress state appears
while a controlled generation is blocked, final prose appears only after
validation, Stop does not leak a late answer, and the UI recovers from broker
unhealthy, network interruption, malformed event, and disabled-feature cases.
Inspect service logs for redacted credentials, cancellation cleanup, queue wait,
and the matching request ID; do not paste book text or tokens into the report.

## Timing and report format

Measure browser submit to first event, first candidate, first validated answer,
and terminal completion separately with monotonic server timing and correlated
request IDs. Include channel connection, queue wait, broker execution,
provider/model work where observable, validation, repair, status, and outcome.
Use at least five documented cold and twenty warm observations per question
class when measuring a release candidate. A p95 from this small sample is
descriptive, not a service-level guarantee.

The current local targets remain: warm terminal completion within eight seconds
and cold completion within thirty seconds. Misses are reported, never hidden by
changing completion definitions or disabling validation. First-progress targets
are tested independently: first event within one second of admission and first
candidate within 250 ms of completed retrieval.

Each report uses this template:

```text
Git SHA / images:
Environment and redacted configuration fingerprint:
Mode / cold-or-warm definition:
Question class and scope (no book text):
Expected evidence floor / observed distinct relevant citations:
Event sequence and terminal outcome:
Timing samples and failures:
Cancellation, health, auth, and migration checks:
Chrome UAT operator / independent reviewer:
Known unavailable conditions or blockers:
Linked PR and issue milestone:
```

## Release rule

M04 and later milestones require deterministic fixtures first, Chrome UAT
second, independent code and live review third, then the full suite. An
unavailable local broker, model, Docker service, or private corpus is recorded
as unavailable and blocks the claim it would have tested. Performance work in
#86 remains separate from correctness acceptance.
