#!/usr/bin/env bash
# Commit run artifacts and notes so nothing is lost when the session or VM ends. Pushes if a remote exists.
# Usage: checkpoint.sh "message"
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
git add -A runs notes results.tsv harness/corpus.txt 2>/dev/null || true
if ! git diff --cached --quiet; then git commit -qm "checkpoint: ${1:-runs and notes}"; echo "committed"; else echo "nothing to checkpoint"; fi
if git remote get-url origin >/dev/null 2>&1; then git push -q origin HEAD 2>/dev/null && echo "pushed" || echo "push failed (continue; retry next checkpoint)" >&2; fi
