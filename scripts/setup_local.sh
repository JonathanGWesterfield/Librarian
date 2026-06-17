#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SYSTEM_DEPS="false"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: scripts/setup_local.sh [--install-system-deps]

Sets up local Librarian development dependencies.

By default, this script:
  - reports missing system dependencies
  - creates .venv when needed
  - installs Python editable packages and dev dependencies

Options:
  --install-system-deps  Use Homebrew to install missing CLI dependencies.
  -h, --help             Show this help message.

Dependencies that cannot be bundled into the repo:
  - Homebrew, for installing macOS CLI packages
  - Docker runtime: Docker Desktop, or Docker CLI plus Colima
  - Ollama, for local embedding models
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-system-deps)
      INSTALL_SYSTEM_DEPS="true"
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

have() {
  command -v "$1" >/dev/null 2>&1
}

install_brew_package() {
  local package="$1"
  if [[ "$INSTALL_SYSTEM_DEPS" != "true" ]]; then
    return 1
  fi
  if ! have brew; then
    log "Homebrew is required for --install-system-deps"
    return 1
  fi
  log "Installing $package with Homebrew"
  brew install "$package"
}

ensure_command() {
  local command_name="$1"
  local package_name="${2:-$1}"
  local install_hint="$3"

  if have "$command_name"; then
    log "$command_name found"
    return 0
  fi

  if install_brew_package "$package_name"; then
    return 0
  fi

  log "$command_name not found"
  log "$install_hint"
  return 1
}

ensure_python_env() {
  if [[ ! -d ".venv" ]]; then
    log "Creating Python virtual environment"
    "$PYTHON_BIN" -m venv .venv
  fi

  log "Installing Python packages into .venv"
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install \
    -e "apps/api[dev]" \
    -e "apps/codex_broker[dev]" \
    -e "packages[dev]"
}

ensure_docker_runtime_guidance() {
  if docker info >/dev/null 2>&1; then
    log "Docker daemon is running"
    return 0
  fi

  if [[ -d "/Applications/Docker.app" ]]; then
    log "Docker Desktop is installed but not running; scripts/start_local.sh can start it"
    return 0
  fi

  if have colima; then
    log "Colima is installed; scripts/start_local.sh can start it"
    return 0
  fi

  if [[ "$INSTALL_SYSTEM_DEPS" == "true" ]] && have brew; then
    log "Installing Colima with Homebrew"
    brew install colima
    return 0
  fi

  log "No Docker runtime found"
  log "Install Docker Desktop, or install Colima with: brew install colima"
  return 1
}

missing=0

ensure_command "$PYTHON_BIN" "python" "Install Python 3.12+ or set PYTHON_BIN=/path/to/python" || missing=1
ensure_command docker docker "Install Docker Desktop, or run: brew install docker docker-compose" || missing=1
ensure_command ollama ollama "Install Ollama from https://ollama.com/download or run: brew install ollama" || missing=1
ensure_docker_runtime_guidance || missing=1

if [[ "$missing" -ne 0 ]]; then
  log "Some system dependencies are missing"
  log "Rerun with --install-system-deps to install Homebrew-managed CLI dependencies where possible"
  exit 1
fi

ensure_python_env

log "Local setup complete"
log "Next: scripts/start_local.sh"
