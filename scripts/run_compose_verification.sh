#!/usr/bin/env bash
# Run the isolated, one-shot Compose verification pipeline.
#
# This starts only the runtime dependency services in a dedicated Compose
# project, then explicitly runs the profile-gated verifier. The EXIT trap
# removes that project's named fixture, OpenSearch, and model volumes without
# touching the normal local stack's data.
#
# Examples:
#   scripts/run_compose_verification.sh
#   LIBRARIAN_VERIFY_PROJECT=librarian-verify-pr-42 scripts/run_compose_verification.sh
#   LIBRARIAN_VERIFY_MIN_MEMORY_GB=6 scripts/run_compose_verification.sh
set -euo pipefail

project_name="${LIBRARIAN_VERIFY_PROJECT:-librarian-verify}"
compose=(
  docker compose
  --project-name "$project_name"
  -f docker-compose.yml
  -f docker-compose.verify.yml
)

cleanup() {
  local status=$?
  trap - EXIT
  "${compose[@]}" down --volumes --remove-orphans || true
  exit "$status"
}

trap cleanup EXIT

scripts/verify_preflight.sh
# Do not enable the verify profile here. Compose's `up --wait` expects running
# services, so wait for the successful one-shot initializer separately.
"${compose[@]}" up --build --detach --wait opensearch ollama
"${compose[@]}" up --build --detach ollama-init
"${compose[@]}" wait ollama-init
"${compose[@]}" up --build --detach --wait api
"${compose[@]}" run --build --rm --no-deps verifier
