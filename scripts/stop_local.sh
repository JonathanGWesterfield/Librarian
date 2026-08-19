#!/usr/bin/env bash
# Stop the Docker Compose Librarian stack from a Bash-compatible shell.
#
# This leaves named volumes intact, including downloaded Ollama models and
# OpenSearch data. Use Docker Compose directly when Bash is unavailable.
#
# Examples:
#   scripts/stop_local.sh
#   bash scripts/stop_local.sh --remove-orphans
#   scripts/stop_local.sh && docker compose ps
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOVE_ORPHANS="false"

usage() {
  cat <<'EOF'
Usage: scripts/stop_local.sh [--remove-orphans]

Stops the local Docker Compose services without deleting named volumes.
This helper requires Bash; on Windows PowerShell or Command Prompt, use
`docker compose down` directly.

Options:
  --remove-orphans  Also remove services no longer in docker-compose.yml.
  -h, --help        Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove-orphans)
      REMOVE_ORPHANS="true"
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
  printf '%s\n' '[librarian] Docker Compose v2 is required to stop the stack.' >&2
  exit 1
fi

cd "$ROOT_DIR"
compose_args=(compose down)
if [[ "$REMOVE_ORPHANS" == "true" ]]; then
  compose_args+=(--remove-orphans)
fi
docker "${compose_args[@]}"
printf '%s\n' '[librarian] Stack stopped; named volumes were retained.'
