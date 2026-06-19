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

command=(python3 -m unittest)
if [[ "${failfast}" == "true" ]]; then
  command+=("-f")
fi

if ((${#tests[@]})); then
  "${command[@]}" -v "${tests[@]}"
elif [[ "${verbosity}" == "2" ]]; then
  "${command[@]}" discover -v -s tests
else
  "${command[@]}" discover -s tests
fi
