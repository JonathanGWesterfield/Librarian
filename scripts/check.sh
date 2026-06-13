#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall apps packages scripts tests
scripts/test.sh
