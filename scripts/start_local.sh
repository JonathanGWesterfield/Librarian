#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_HOST_URL="${LIBRARIAN_LOCAL_OLLAMA_URL:-http://localhost:11434}"
OLLAMA_MODEL="${LIBRARIAN_EMBEDDING_MODEL:-all-minilm}"
PULL_MODEL="${LIBRARIAN_PULL_EMBEDDING_MODEL:-true}"

cd "$ROOT_DIR"
mkdir -p data

log() {
  printf '[librarian] %s\n' "$1"
}

wait_for() {
  local description="$1"
  local command="$2"
  local attempts="${3:-60}"
  local delay="${4:-2}"

  for _ in $(seq 1 "$attempts"); do
    if eval "$command" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done

  printf 'Timed out waiting for %s\n' "$description" >&2
  return 1
}

start_docker() {
  if docker info >/dev/null 2>&1; then
    log "Docker is already running"
    return 0
  fi

  if [[ "$(uname -s)" == "Darwin" ]]; then
    log "Starting Docker Desktop"
    open -a Docker
  else
    log "Docker is not running; start Docker and rerun this script"
    return 1
  fi

  wait_for "Docker" "docker info" 90 2
}

start_ollama() {
  if curl -fsS "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
    log "Ollama is already running at $OLLAMA_HOST_URL"
  else
    if ! command -v ollama >/dev/null 2>&1; then
      log "Ollama CLI not found; install Ollama natively or set LIBRARIAN_PULL_EMBEDDING_MODEL=false"
      return 1
    fi

    log "Starting native Ollama"
    nohup ollama serve > data/ollama.log 2>&1 &
    wait_for "Ollama" "curl -fsS '$OLLAMA_HOST_URL/api/tags'" 60 2
  fi

  if [[ "$PULL_MODEL" == "true" && "$OLLAMA_MODEL" != "noop" ]]; then
    log "Ensuring embedding model is available: $OLLAMA_MODEL"
    ollama pull "$OLLAMA_MODEL"
  fi
}

start_services() {
  log "Starting Docker Compose services"
  docker compose up -d
}

start_docker
start_ollama
start_services

log "Local Librarian stack is ready"
log "API: http://localhost:8000"
log "Ollama: $OLLAMA_HOST_URL"
