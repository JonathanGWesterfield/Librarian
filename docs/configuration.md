# Configuration

Librarian has one operational source of truth: `config/librarian.json`.
The application and Compose resolver do not read `LIBRARIAN_*` environment
variables. This keeps local startup, Docker Compose, and command-line tools on
the same explicit configuration contract.

## Choose a starting profile

`config/librarian.json` is deliberately ignored. It can contain machine paths
and references to local secret files, so each clone owns it. Start with one of
the tracked, credential-free profiles:

| Profile | Use it when | Answer generation |
| --- | --- | --- |
| [`config/librarian.example.json`](../config/librarian.example.json) | You want the fully local default. The launchers copy this profile automatically on first run. | Docker Ollama, `qwen2.5:1.5b` |
| [`config/librarian.base.json`](../config/librarian.base.json) | You run a Codex-compatible, OpenAI-style gateway on the host. This is the populated baseline used for the maintained host-broker workflow. | Gateway model `codex` |

To select the base profile explicitly:

```bash
cp config/librarian.base.json config/librarian.json
mkdir -p config/secrets
# Put only the gateway token in this ignored file.
printf '%s\n' 'replace-with-your-token' > config/secrets/codex-bridge-token.txt
scripts/start_local.sh
```

The gateway profile keeps embeddings local: Docker Ollama downloads and uses
`all-minilm`, while answer generation calls
`http://host.docker.internal:3000/v1`. Docker Compose starts only the Docker
Ollama models selected by the embedding and generation sections.

## Configuration shape

Every profile has the following top-level sections.

| Section | Purpose |
| --- | --- |
| `version` | Configuration schema version. Current value: `1`. |
| `paths` | Container EPUB location, host EPUB mount, SQLite database URL, and log path. |
| `embedding` | Provider and model used to create chunk and query vectors. |
| `generation` | Provider and model used to write grounded answers and summaries. |
| `search` | OpenSearch URL/index and retrieval backend selection. |
| `summaries` | Summary timeout and worker parallelism limits. |
| `services` | Published ports, OpenSearch heap, Ollama listener, and worker settings. |
| `codex_executable` | Host executable used only by the direct `codex` generation mode. |

For normal Docker startup, retain `paths.books_dir` as `/books`,
`paths.database_url` as `sqlite:////data/librarian.db`, and
`paths.log_file` as `/data/librarian.log`. Their host directories are mounted
into the containers. Change `paths.host_books_dir` to point at your EPUB
directory; it must remain a relative or absolute host path that Docker can
mount.

## Providers

`embedding` and `generation` are independent. Their `mode` field determines
the required companion fields.

| Mode | Available for | Required fields | Docker behavior |
| --- | --- | --- | --- |
| `docker_ollama` | Embedding and generation | `model` | Starts Compose Ollama and downloads the selected model. |
| `native_ollama` | Embedding and generation | `model`, `base_url` | Calls an Ollama service already running on the host or network. |
| `openai_compatible` | Embedding and generation | `model`, `base_url`, `api_key_file` | Calls a gateway and does not start Ollama for that section. |
| `codex` | Generation only | `model` | Runs the configured host Codex CLI; this is for host-side tooling, not the Docker API container. |

For `native_ollama`, Docker Desktop users normally use
`http://host.docker.internal:11434`. For `openai_compatible`, the base URL must
be an HTTP(S) OpenAI-compatible API root such as
`http://host.docker.internal:3000/v1`; Librarian appends the standard endpoint.

`generation.answer_capability` is an explicit behavior declaration, not a
model-name guess. Use `lightweight` for a small local generator and `quality`
for a capable provider. If an API request changes its generation provider or
model, it must supply `answer_capability` too; otherwise `/chat` returns HTTP
400 rather than silently inheriting the configured behavior.

## Secrets and safe headers

Never put credentials directly in JSON. `config/secrets/` is ignored by Git,
and the parser permits credential values only through paths under that
directory:

```json
{
  "generation": {
    "mode": "openai_compatible",
    "model": "gateway-model",
    "base_url": "https://gateway.example/v1",
    "api_key_file": "secrets/gateway-token.txt",
    "headers": {"OpenAI-Project": "book-research"},
    "header_files": {"X-API-Key": "secrets/gateway-api-key.txt"},
    "answer_capability": "quality"
  }
}
```

`headers` is only for non-secret metadata. Literal `Authorization`, token,
API-key, secret, and subscription-key headers are rejected. Use
`api_key_file` for the standard bearer token or `header_files` for any
credential-bearing custom header. Secrets are read at runtime and are never
rendered into the generated Compose override.

## What the launcher does

`scripts/start_local.sh` and `scripts/start_local.ps1` create a local config
from `librarian.example.json` only when one is absent. They invoke the
containerized resolver, which writes non-secret values to `.runtime/`:

- selected API, web, and OpenSearch ports;
- whether Docker Ollama is needed; and
- the Docker Ollama model list.

For Docker Ollama, the launcher waits for the one-shot `ollama-init` service
to finish successfully, verifies every configured model with `ollama list`,
and only then starts API and web services. It prints service state and recent
initializer logs on a failure or timeout.

## Validate a change

Validate JSON and Compose wiring without starting the normal stack:

```bash
docker compose --profile config-resolver run --rm --build config-resolver
docker compose -f docker-compose.yml -f .runtime/librarian.compose.json config --quiet
```

Then start the application with `scripts/start_local.sh` (or
`./scripts/start_local.ps1` on Windows). The launcher prints the web and API
URLs selected by `services.web_port` and `services.api_port`.

For endpoint-level request and response examples, see
[`docs/api-endpoints.md`](api-endpoints.md). For the SQLite/OpenSearch data
relationship, see [`docs/search-storage-architecture.md`](search-storage-architecture.md).
