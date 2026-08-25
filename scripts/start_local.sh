#!/usr/bin/env bash
# Start the Docker Compose Librarian stack from a Bash-compatible shell.
#
# A Docker-resident resolver reads config/librarian.json, then selects either
# Docker Ollama, native Ollama, or a remote OpenAI-compatible gateway for
# embeddings and generation independently. It never reads settings or secrets
# from shell environment variables.
#
# Examples:
#   scripts/start_local.sh
#   scripts/start_local.sh --foreground
#   scripts/start_local.sh --with-workers
#   bash scripts/start_local.sh --no-build --foreground
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DETACH="true"
BUILD="true"
WITH_WORKERS="false"

usage() {
  cat <<'EOF'
Usage: scripts/start_local.sh [--foreground] [--no-build] [--with-workers]

Starts the local Docker Compose stack. This helper requires Bash; on Windows
PowerShell, use scripts/start_local.ps1. All settings are read from the
user-owned config/librarian.json file (copied from the example on first run).

Options:
  --foreground    Stream Compose output instead of starting in the background.
  --no-build      Do not rebuild the API image before starting.
  --with-workers  Enable the optional summary-worker Compose profile.
  -h, --help      Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground) DETACH="false" ;;
    --no-build) BUILD="false" ;;
    --with-workers) WITH_WORKERS="true" ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' '[librarian] Docker Compose v2 is required. Run scripts/setup_local.sh for a diagnostic.' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf '%s\n' '[librarian] Docker is not running. Start Docker Desktop or your Docker runtime, then rerun.' >&2
  exit 1
fi

cd "$ROOT_DIR"
mkdir -p data config/secrets .runtime
if [[ ! -f config/librarian.json ]]; then
  cp config/librarian.example.json config/librarian.json
  printf '%s\n' '[librarian] Created config/librarian.json from the example.'
fi

docker compose --profile config-resolver run --rm --build config-resolver
compose_args=(compose -f docker-compose.yml -f .runtime/librarian.compose.json)

read_state_value() {
  local key="$1"
  awk -F: -v expected="$key" '
    $0 ~ "\"" expected "\"[[:space:]]*:" {
      value = $2
      gsub(/[[:space:],}]/, "", value)
      print value
      exit
    }
  ' .runtime/librarian.state.json
}

docker_ollama_enabled="$(read_state_value docker_ollama_enabled)"
api_port="$(read_state_value api_port)"
web_port="$(read_state_value web_port)"
if [[ "$docker_ollama_enabled" != "true" && "$docker_ollama_enabled" != "false" ]]; then
  printf '%s\n' '[librarian] Configuration resolver did not produce a valid Docker-Ollama selection.' >&2
  exit 1
fi
if [[ ! "$api_port" =~ ^[0-9]+$ ]] || ((api_port < 1 || api_port > 65535)); then
  printf '%s\n' '[librarian] Configuration resolver did not produce a valid API port.' >&2
  exit 1
fi
if [[ ! "$web_port" =~ ^[0-9]+$ ]] || ((web_port < 1 || web_port > 65535)); then
  printf '%s\n' '[librarian] Configuration resolver did not produce a valid web UI port.' >&2
  exit 1
fi

if [[ "$WITH_WORKERS" == "true" ]]; then
  compose_args+=(--profile workers)
fi
if [[ "$docker_ollama_enabled" == "true" ]]; then
  compose_args+=(--profile docker-ollama)
  dependency_start=(up)
  [[ "$BUILD" == "true" ]] && dependency_start+=(--build)
  dependency_start+=(-d opensearch ollama)
  docker "${compose_args[@]}" "${dependency_start[@]}"
  initializer_start=(up)
  [[ "$BUILD" == "true" ]] && initializer_start+=(--build)
  initializer_start+=(-d ollama-init)
  docker "${compose_args[@]}" "${initializer_start[@]}"
  docker "${compose_args[@]}" wait ollama-init
fi

start_args=(up)
[[ "$BUILD" == "true" ]] && start_args+=(--build)
[[ "$DETACH" == "true" ]] && start_args+=(-d)
start_args+=(api web)
[[ "$WITH_WORKERS" == "true" ]] && start_args+=(summary-worker)
docker "${compose_args[@]}" "${start_args[@]}"
printf '[librarian] Stack started. API: http://localhost:%s\n' "$api_port"
printf '[librarian] Web UI: http://localhost:%s\n' "$web_port"
printf '%s\n' '[librarian] Inspect readiness with: docker compose ps'
