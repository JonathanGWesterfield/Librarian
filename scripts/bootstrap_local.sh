#!/usr/bin/env bash
# Start the Docker Compose Librarian stack from a Bash-compatible shell.
#
# This is a thin convenience wrapper around setup_local.sh and start_local.sh.
# It does not install Homebrew, Python, Docker Desktop, or Ollama on the host.
# Use the portable `docker compose up --build` command documented in README.md
# from Windows PowerShell, Command Prompt, Linux, or macOS.
#
# Examples:
#   scripts/bootstrap_local.sh
#   scripts/bootstrap_local.sh --foreground
#   bash scripts/bootstrap_local.sh --with-workers
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -gt 0 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  cat <<'EOF'
Usage: scripts/bootstrap_local.sh [start options]

Checks the Docker Compose configuration and starts Librarian. This Bash helper
does not install host dependencies. On Windows PowerShell or Command Prompt,
run `docker compose up --build` directly.

Start options are forwarded to scripts/start_local.sh, including --foreground,
--no-build, and --with-workers.
EOF
  exit 0
fi

cd "$ROOT_DIR"
bash scripts/setup_local.sh
exec bash scripts/start_local.sh "$@"
