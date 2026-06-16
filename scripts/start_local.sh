#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_HOST_URL="${LIBRARIAN_LOCAL_OLLAMA_URL:-http://localhost:11434}"
OLLAMA_MODEL="${LIBRARIAN_EMBEDDING_MODEL:-all-minilm}"
PULL_MODEL="${LIBRARIAN_PULL_EMBEDDING_MODEL:-true}"
HOMEBREW_DOCKER_PLUGIN_DIR="/opt/homebrew/lib/docker/cli-plugins"

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

ensure_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    return 0
  fi

  if [[ -d "$HOMEBREW_DOCKER_PLUGIN_DIR" ]]; then
    log "Configuring Docker to find Homebrew CLI plugins"
    python3 - "$HOMEBREW_DOCKER_PLUGIN_DIR" <<'PY'
import json
import sys
from pathlib import Path

plugin_dir = sys.argv[1]
config_path = Path.home() / ".docker" / "config.json"
config_path.parent.mkdir(parents=True, exist_ok=True)

if config_path.exists():
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        raise SystemExit(f"{config_path} is not valid JSON; fix it before continuing")
else:
    config = {}

plugin_dirs = config.setdefault("cliPluginsExtraDirs", [])
if plugin_dir not in plugin_dirs:
    plugin_dirs.append(plugin_dir)
config_path.write_text(json.dumps(config, indent=2) + "\n")
PY
  fi

  if ! docker compose version >/dev/null 2>&1; then
    log "Docker Compose is not available to the Docker CLI"
    log "Install Docker Compose or add Homebrew's plugin directory to ~/.docker/config.json"
    return 1
  fi
}

start_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Docker CLI not found; install Docker Desktop or Docker via Homebrew"
    return 1
  fi

  ensure_docker_compose

  if docker info >/dev/null 2>&1; then
    log "Docker is already running"
    return 0
  fi

  if [[ "$(uname -s)" == "Darwin" ]]; then
    if [[ -d "/Applications/Docker.app" ]]; then
      log "Starting Docker Desktop"
      open -a Docker
    elif command -v colima >/dev/null 2>&1; then
      log "Starting Colima Docker runtime"
      colima start
    else
      log "Docker daemon is not running, and Docker Desktop.app was not found"
      log "Install/start Docker Desktop, or install Colima with: brew install colima"
      return 1
    fi
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
