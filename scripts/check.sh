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

python3 -m compileall apps packages scripts tests
scripts/test.sh
python3 scripts/evaluate_retrieval.py --check
