#!/usr/bin/env bash
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

export PYTHONPATH="${PWD}/packages/ingestion${PYTHONPATH:+:${PYTHONPATH}}"

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
