#!/usr/bin/env bash
# Validate Docker memory before running the Compose verification stack.
#
# The verifier runs OpenSearch, Ollama, the production API image, and a
# short-lived test-harness image. Docker's VM needs more memory than the
# runtime image occupies on disk; this script checks VM memory only and never
# changes Docker Desktop or Colima settings.
#
# Examples:
#   scripts/verify_preflight.sh
#   scripts/verify_preflight.sh --minimum-gb 6
#   LIBRARIAN_VERIFY_MIN_MEMORY_GB=8 scripts/verify_preflight.sh
set -euo pipefail

minimum_gb="${LIBRARIAN_VERIFY_MIN_MEMORY_GB:-4}"

usage() {
  cat <<'EOF'
Usage: scripts/verify_preflight.sh [--minimum-gb GB]

Checks the memory assigned to Docker before Compose verification.

Examples:
  scripts/verify_preflight.sh
  scripts/verify_preflight.sh --minimum-gb 6
  LIBRARIAN_VERIFY_MIN_MEMORY_GB=8 scripts/verify_preflight.sh
EOF
}

while (($#)); do
  case "$1" in
    --minimum-gb)
      minimum_gb="${2:?--minimum-gb requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$minimum_gb" =~ ^[0-9]+$ ]] || ((minimum_gb < 1)); then
  echo "[librarian] Minimum memory must be a positive whole number of GB." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[librarian] Docker is required for Compose verification." >&2
  exit 2
fi

memory_bytes="$(docker info --format '{{.MemTotal}}' 2>/dev/null || true)"
if ! [[ "$memory_bytes" =~ ^[0-9]+$ ]]; then
  echo "[librarian] Could not read Docker VM memory from 'docker info'." >&2
  exit 2
fi

minimum_bytes=$((minimum_gb * 1000000000))
available_gb="$(awk -v bytes="$memory_bytes" 'BEGIN { printf "%.2f", bytes / 1000000000 }')"
if ((memory_bytes < minimum_bytes)); then
  cat >&2 <<EOF
[librarian] Compose verification requires at least ${minimum_gb} GB assigned to Docker; detected ${available_gb} GB.
Increase Docker Desktop's Resources > Memory, or start Colima with a larger
memory allocation (for example: colima start --memory ${minimum_gb}). Then rerun
this preflight. This is Docker VM runtime memory, not the on-disk image size.
EOF
  exit 1
fi

echo "[librarian] Docker VM memory is ${available_gb} GB (minimum ${minimum_gb} GB)."
