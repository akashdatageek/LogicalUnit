#!/usr/bin/env bash
# sweep.sh — resumable, bounded-parallel, limit-aware corpus driver (notes/architecture.md fix 5)
#
# Why this exists
#   run_corpus.sh is strictly serial and has no memory of a killed run: a usage-limit death in the
#   middle of a sweep silently drops that slot, and because slow/expensive runs are the ones most
#   likely to be killed, the surviving data is biased toward the cheap runs. This driver makes the
#   operational reality part of the harness:
#     - RESUMABLE: run_one.sh already skips a slot whose score.json exists, so re-running sweep.sh
#       continues where it stopped. The ledger records every slot's final outcome, so a lost run is
#       visible instead of missing.
#     - LIMIT-AWARE: a slot that exits 4 (run_one.sh classified an account usage/rate limit) is
#       backed off and retried, not counted as a failure.
#     - BOUNDED-PARALLEL: per-run output/checkout dirs (already isolated) let N runs proceed at once.
#       Raising N reaches the account cap N times faster, so default is 1; raise it only with an API
#       key set (patch 05) and headroom to spare.
#
# Usage: sweep.sh [--reps 0,1,2] [--only a,b] [--parallel N] [--retries K]
#                 [--condition ..] [--model ID] [--ablate SEC] [--hide-docs] [--max-turns N]
set -uo pipefail    # deliberately NOT -e: one failed slot must not abort the sweep
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPS="0,1,2"; ONLY=""; PAR=1; MAX_RETRY=3; DEADLINE=0; PASS=()
while [ $# -gt 0 ]; do case "$1" in
  --reps) REPS="$2"; shift 2;; --only) ONLY="$2"; shift 2;;
  --parallel) PAR="$2"; shift 2;; --retries) MAX_RETRY="$2"; shift 2;;
  --deadline-min) DEADLINE="$2"; shift 2;;
  --max-turns|--condition|--model|--ablate) PASS+=("$1" "$2"); shift 2;;
  --hide-docs) PASS+=("$1"); shift;; *) shift;; esac; done

RUNNER="${LU_RUNNER:-$HERE/harness/run_one.sh}"      # overridable for testing the orchestration
LEDGER="${LU_LEDGER:-$HERE/notes/sweep-ledger.tsv}"
[ -f "$LEDGER" ] || printf 'utc\trepo\trep\toutcome\tattempts\tpass_args\n' > "$LEDGER"
HOLD=$(grep -v '^#' "$HERE/harness/holdout.txt" 2>/dev/null | tr '\n' ' ')
START=$(date +%s)

ledger() {   # utc repo rep outcome attempts
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$2" "$3" "$4" "${PASS[*]:-}" >> "$LEDGER"
}

run_slot() {   # repo sha rep
  local repo="$1" sha="$2" rep="$3" attempt=1 ec
  while :; do
    "$RUNNER" "$repo" "$sha" "$rep" "${PASS[@]}"; ec=$?
    case "$ec" in
      0) ledger "$repo" "$rep" done "$attempt"; return 0;;
      4) local reason=limit; local back=$((60*attempt));;   # usage/rate limit: long back-off
      3) local reason=killed; local back=$((5*attempt));;    # infra kill: short back-off
      *) local reason="exit$ec"; local back=$((5*attempt));;
    esac
    if [ "$attempt" -ge "$MAX_RETRY" ]; then
      echo "GIVEUP $repo/$rep after $attempt attempts ($reason)" >&2
      ledger "$repo" "$rep" "FAILED-$reason" "$attempt"; return "$ec"
    fi
    echo "retry $repo/$rep in ${back}s (attempt $attempt, $reason)" >&2
    sleep "$back"; attempt=$((attempt+1))
  done
}

# Bounded-parallel job pool.
active=0
while read -r repo sha stratum lang; do
  [ -z "${repo:-}" ] && continue
  case "$repo" in \#*) continue;; esac
  [ "$sha" = "PIN_ME" ] && { echo "skip $repo: not pinned"; continue; }
  name="${repo#*/}"
  [ -n "$ONLY" ] && ! grep -qw "$name" <<< "$ONLY" && continue
  if grep -qw "$name" <<< "$HOLD" && [ "${LU_HOLDOUT_OK:-0}" != 1 ]; then echo "skip $name: HOLDOUT"; continue; fi
  for r in ${REPS//,/ }; do
    # Window budget: stop LAUNCHING new slots past the deadline (in-flight ones finish). sweep is
    # resumable -- run_one.sh skips a slot with a score.json -- so the next window continues here.
    if [ "$DEADLINE" -gt 0 ] && [ $(( ($(date +%s) - START) / 60 )) -ge "$DEADLINE" ]; then
      echo "deadline ${DEADLINE}m reached; stopping new launches (resume next window)" >&2; break 2
    fi
    run_slot "$repo" "$sha" "$r" &
    active=$((active+1))
    if [ "$active" -ge "$PAR" ]; then wait -n 2>/dev/null || wait; active=$((active-1)); fi
  done
done < <(grep -v '^#' "$HERE/harness/corpus.txt")
wait
echo "sweep complete; ledger: $LEDGER"
