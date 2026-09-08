#!/usr/bin/env bash
# Usage: run_corpus.sh [--reps 0,1,2] [--only a,b] [--max-turns N] [--condition skill|noskill] [--hide-docs] [--model ID]
# Holdout repos are skipped unless LU_HOLDOUT_OK=1 (human only). corpus.txt columns: repo sha [stratum] [lang]
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPS="0,1,2"; ONLY=""; PASS=()
while [ $# -gt 0 ]; do case "$1" in
  --reps) REPS="$2"; shift 2;; --only) ONLY="$2"; shift 2;;
  --max-turns|--condition|--model) PASS+=("$1" "$2"); shift 2;; --hide-docs) PASS+=("$1"); shift;; *) shift;; esac; done
HOLD=$(grep -v '^#' "$HERE/harness/holdout.txt" 2>/dev/null | tr '\n' ' ')
grep -v '^#' "$HERE/harness/corpus.txt" | while read -r repo sha stratum lang; do
  [ -z "$repo" ] && continue
  [ "$sha" = "PIN_ME" ] && { echo "skip $repo: not pinned"; continue; }
  name="${repo#*/}"
  [ -n "$ONLY" ] && ! grep -qw "$name" <<< "$ONLY" && continue
  if grep -qw "$name" <<< "$HOLD" && [ "${LU_HOLDOUT_OK:-0}" != 1 ]; then echo "skip $name: HOLDOUT"; continue; fi
  for r in ${REPS//,/ }; do
    "$HERE/harness/run_one.sh" "$repo" "$sha" "$r" --stratum "${stratum:-unknown}" "${PASS[@]}" || echo "FAILED $name/$r"
  done
done
