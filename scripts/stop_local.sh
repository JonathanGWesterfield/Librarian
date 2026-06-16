#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STOP_OLLAMA="false"
STOP_DOCKER_RUNTIME="false"

usage() {
  cat <<'EOF'
Usage: scripts/stop_local.sh [--ollama] [--docker-runtime]

Stops Librarian's Docker Compose services.

Options:
  --ollama          Also stop native Ollama processes started outside Docker.
  --docker-runtime  Also stop Colima when it is the active Docker runtime.
  -h, --help        Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ollama)
      STOP_OLLAMA="true"
      shift
      ;;
    --docker-runtime)
      STOP_DOCKER_RUNTIME="true"
      shift
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
done

cd "$ROOT_DIR"

log() {
  printf '[librarian] %s\n' "$1"
}

stop_compose() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Docker CLI not found; skipping Docker Compose shutdown"
    return 0
  fi

  if ! docker compose version >/dev/null 2>&1; then
    log "Docker Compose is not available; skipping Docker Compose shutdown"
    return 0
  fi

  if ! docker info >/dev/null 2>&1; then
    log "Docker daemon is not running; Docker Compose services are already stopped"
    return 0
  fi

  log "Stopping Docker Compose services"
  docker compose down
}

stop_ollama() {
  if [[ "$STOP_OLLAMA" != "true" ]]; then
    log "Leaving native Ollama running; pass --ollama to stop it"
    return 0
  fi

  if ! pgrep -x ollama >/dev/null 2>&1; then
    log "Ollama is not running"
    return 0
  fi

  log "Stopping native Ollama"
  pkill -x ollama
}

stop_docker_runtime() {
  if [[ "$STOP_DOCKER_RUNTIME" != "true" ]]; then
    log "Leaving Docker runtime running; pass --docker-runtime to stop Colima"
    return 0
  fi

  if command -v colima >/dev/null 2>&1; then
    log "Stopping Colima Docker runtime"
    colima stop
    return 0
  fi

  log "No supported script-managed Docker runtime found to stop"
}

stop_compose
stop_ollama
stop_docker_runtime

log "Local Librarian stack is stopped"
