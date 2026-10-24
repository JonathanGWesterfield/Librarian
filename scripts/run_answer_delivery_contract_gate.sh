#!/usr/bin/env bash
# Run the M03 contract gate from a tracked, isolated source tree.
#
# The gate never uses the working tree as a Docker build context or bind mount:
# a temporary git-archive tree for the clean release is the only source exposed
# to Docker. The rendered Compose topology runs on the host because the test
# image deliberately has no Docker socket or CLI; it is required to pass before
# the read-only Python test container starts.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
release_sha="${LIBRARIAN_STACK_RELEASE_SHA:?LIBRARIAN_STACK_RELEASE_SHA is required}"
if ! [[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "[librarian] LIBRARIAN_STACK_RELEASE_SHA must be a lowercase 40-character SHA." >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "[librarian] Docker is required for the isolated answer-delivery contract gate." >&2
  exit 2
fi

stage_dir="$(mktemp -d "${TMPDIR:-/tmp}/librarian-answer-delivery-contract.XXXXXX")"
cleanup() {
  local exit_code=$?
  rm -rf "$stage_dir"
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

git -C "$root_dir" archive --format=tar "$release_sha" | tar -x -C "$stage_dir"
# These are ignored user-owned inputs. Failing closed here prevents a future
# ignore-rule regression from giving the test image local config or credentials.
test ! -e "$stage_dir/config/librarian.json"
test ! -e "$stage_dir/config/secrets"

# This invokes docker compose config against the staged tree and fails on a
# skipped or invalid topology assertion. It intentionally runs outside the
# Python image, whose lack of Docker access is part of its isolation boundary.
(
  cd "$stage_dir"
  LIBRARIAN_STACK_RELEASE_SHA="$release_sha" \
    PYTHONPATH="$stage_dir/packages" \
    python3 - <<'PYTEST'
import sys
import unittest

suite = unittest.defaultTestLoader.loadTestsFromName("tests.e2e.test_r2_compose_overlay")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    raise SystemExit("[librarian] R2 Compose topology gate was skipped")
raise SystemExit(not result.wasSuccessful())
PYTEST
)

image="librarian-answer-delivery-contract-gate:${release_sha}"
docker build \
  -f "$stage_dir/apps/api/Dockerfile" \
  --target answer-delivery-contract-gate \
  --tag "$image" \
  "$stage_dir"
# The test image copied its source from the staged archive during docker build.
# Do not bind mount any host directory: `/app` is that isolated image layout.
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --workdir /app \
  --env PYTHONPATH=/app/packages \
  "$image" \
  python -m unittest -v \
  tests.contracts.test_answer_delivery_contract \
  tests.contracts.test_compose_security \
  tests.e2e.test_r2_cutover_preflight
