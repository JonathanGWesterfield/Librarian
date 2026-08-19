#!/usr/bin/env bash
# Verify the Docker Compose prerequisite for the container-first Librarian stack.
#
# This Bash helper performs no host-Python, Homebrew, virtualenv, Docker, or
# Ollama installation. The API image supplies its pinned Python 3.12 runtime and
# Compose supplies Ollama. Use the direct `docker compose up --build` command on
# platforms where Bash is unavailable.
#
# Examples:
#   scripts/setup_local.sh
#   bash scripts/setup_local.sh
#   scripts/setup_local.sh && scripts/start_local.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/setup_local.sh

Checks that Docker Compose is installed and validates docker-compose.yml.

This helper requires Bash. It does not install host dependencies. On Windows
PowerShell or Command Prompt, run `docker compose config` and then
`docker compose up --build` directly.
EOF
}

if [[ $# -gt 0 ]]; then
  case "$1" in
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
fi

if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' '[librarian] Docker CLI not found. Install and start a Docker runtime, then rerun.' >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' '[librarian] Docker Compose v2 is required. Install Docker Desktop or Docker Compose, then rerun.' >&2
  exit 1
fi

cd "$ROOT_DIR"
docker compose config --quiet
printf '%s\n' '[librarian] Docker Compose configuration is valid.'
