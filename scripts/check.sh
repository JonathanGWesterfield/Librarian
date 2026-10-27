#!/usr/bin/env bash
# Run the full local validation suite used before PRs.
#
# This script compiles Python files, runs the unit test suite through
# scripts/test.sh, and regenerates/checks the deterministic evaluation report.
# Use it before raising or updating a PR when you want the broadest quick local
# signal that the repo is healthy.
#
# Examples:
#   scripts/check.sh
#   PYTHONPATH="$PWD/packages" scripts/check.sh
#   scripts/test.sh tests.ingestion.test_summarize
#   python3 scripts/evaluate_retrieval.py --check
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${LIBRARIAN_CONFIG_WRITE_LEASE_HELD:-}" != "1" ]]; then
  exec python3 "$root_dir/scripts/config_write_lease.py" --root "$root_dir" -- bash "$0" "$@"
fi

# Every package entry point uses the required user-facing JSON configuration.
# Keep this complete validation isolated from a developer's provider and
# container-only file paths, then restore the ignored configuration afterward.
test_config_path="config/librarian.json"
test_config_fixture="tests/fixtures/config/librarian.test.json"
test_config_backup=""
test_config_cleaned=false
if [[ -f "$test_config_path" ]]; then
  test_config_backup="$(mktemp)"
  cp "$test_config_path" "$test_config_backup"
fi
cp "$test_config_fixture" "$test_config_path"
cleanup_test_config() {
  if [[ "$test_config_cleaned" == "true" ]]; then
    return
  fi
  test_config_cleaned=true
  if [[ -n "$test_config_backup" ]]; then
    if cmp -s "$test_config_path" "$test_config_fixture"; then
      cp "$test_config_backup" "$test_config_path"
    else
      printf '%s\n' '[librarian] Test configuration changed during the run; preserving it instead of restoring the prior local configuration.' >&2
    fi
    rm -f "$test_config_backup"
  else
    rm -f "$test_config_path"
  fi
}
cleanup_test_config_on_signal() {
  cleanup_test_config
  trap - EXIT
  exit "$1"
}
trap cleanup_test_config EXIT
trap 'cleanup_test_config_on_signal 130' INT
trap 'cleanup_test_config_on_signal 143' TERM

scripts/generate_contracts.sh --check
python3 scripts/check_contract_breaking.py
python3 -m compileall apps/api apps/codex_broker packages scripts tests
# This runner already owns the temporary test configuration.  Let the nested
# test runner reuse it so a signal cannot make two cleanup handlers race to
# restore different snapshots.
LIBRARIAN_TEST_CONFIG_INSTALLED=1 scripts/test.sh
python3 scripts/evaluate_retrieval.py --check
