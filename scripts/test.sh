#!/usr/bin/env bash
# Run the Librarian Python unit test suite.
#
# This is the fast local test runner for day-to-day iteration. It sets
# PYTHONPATH to include the repo packages directory and then runs unittest
# discovery, or a specific unittest module if one is provided.
#
# Examples:
#   scripts/test.sh
#   scripts/test.sh --verbose
#   scripts/test.sh tests.ingestion.test_scan
#   scripts/test.sh --failfast tests.ingestion.test_epub
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/test.sh [--verbose] [--failfast] [TEST_NAME ...]

Runs the Librarian Python test suite with unittest.

Examples:
  scripts/test.sh
  scripts/test.sh --verbose
  scripts/test.sh tests.ingestion.test_scan
  scripts/test.sh --failfast tests.ingestion.test_epub
EOF
}

verbosity=1
failfast=false
tests=()

while (($#)); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -v|--verbose)
      verbosity=2
      shift
      ;;
    -f|--failfast)
      failfast=true
      shift
      ;;
    *)
      tests+=("$1")
      shift
      ;;
  esac
done

export PYTHONPATH="${PWD}/packages${PYTHONPATH:+:${PYTHONPATH}}"

# Package services require the same user-facing JSON configuration as the
# running app. Tests must not inherit a developer's provider, model, or
# container-only paths, so temporarily install the checked-in fixture and
# restore an existing ignored configuration byte-for-byte on exit.
test_config_path="config/librarian.json"
test_config_fixture="tests/fixtures/config/librarian.test.json"
test_config_backup=""
if [[ -f "$test_config_path" ]]; then
  test_config_backup="$(mktemp)"
  cp "$test_config_path" "$test_config_backup"
fi
cp "$test_config_fixture" "$test_config_path"
cleanup_test_config() {
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
trap cleanup_test_config EXIT

if ((${#tests[@]})); then
  command=(python3 -m unittest)
  if [[ "${failfast}" == "true" ]]; then
    command+=("-f")
  fi
  "${command[@]}" -v "${tests[@]}"
elif [[ "${verbosity}" == "2" ]]; then
  command=(python3 -m unittest discover -v -s tests)
  if [[ "${failfast}" == "true" ]]; then
    command+=("-f")
  fi
  "${command[@]}"
else
  command=(python3 -m unittest discover -s tests)
  if [[ "${failfast}" == "true" ]]; then
    command+=("-f")
  fi
  "${command[@]}"
fi
