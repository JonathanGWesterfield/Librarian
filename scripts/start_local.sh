#!/usr/bin/env bash
# Start the Docker Compose Librarian stack from a Bash-compatible shell.
#
# Compose builds the API image (which pins Python 3.12), starts OpenSearch and
# Ollama, persists Ollama models in a named volume, and waits for configured
# models before starting the API. No host Python or native Ollama is required.
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
PowerShell or Command Prompt, use `docker compose up --build` directly.

Options:
  --foreground    Stream Compose output instead of starting in the background.
  --no-build      Do not rebuild the API image before starting.
  --with-workers  Enable the optional summary-worker Compose profile.
  -h, --help      Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground)
      DETACH="false"
      ;;
    --no-build)
      BUILD="false"
      ;;
    --with-workers)
      WITH_WORKERS="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
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
mkdir -p data

compose_args=(compose)
if [[ "$WITH_WORKERS" == "true" ]]; then
  compose_args+=(--profile workers)
fi
compose_args+=(up)
if [[ "$BUILD" == "true" ]]; then
  compose_args+=(--build)
fi
if [[ "$DETACH" == "true" ]]; then
  compose_args+=(-d)
fi

docker "${compose_args[@]}"
printf '%s\n' '[librarian] Stack started. API: http://localhost:8000'
printf '%s\n' '[librarian] Inspect readiness with: docker compose ps'
