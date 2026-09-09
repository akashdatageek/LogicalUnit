#!/usr/bin/env bash
# Pilot: baseline skill, all 10 repos incl. holdout, 6 replicates, no edits. Then the report.
set -euo pipefail
cd "$(dirname "$0")/.."
git rev-parse HEAD >/dev/null 2>&1 || { git init -q && git add -A && git commit -qm "lu-bench initial"; }
git tag -f pilot-baseline >/dev/null
LU_HOLDOUT_OK=1 ./harness/run_corpus.sh --reps 0,1,2,3,4,5 "$@"
python3 harness/pilot_check.py --label "$(git rev-parse --short HEAD)" | tee notes/pilot-report.txt
