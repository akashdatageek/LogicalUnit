#!/usr/bin/env bash
# night_sweep.sh — run ONE usage-window's worth of the corpus, then stop cleanly (fix #3, windowed).
#
# The account resets usage on a rolling ~5h window. Overnight windows are free capacity you would
# otherwise lose. This wrapper runs a time-boxed, resumable sweep sized to fit inside one window and
# then EXITS, so an external scheduler can re-invoke it each window; because sweep.sh is resumable
# (run_one.sh skips any slot with a score.json), each window simply continues where the last stopped,
# and sweep.sh's exit-4 back-off handles a limit hit mid-window.
#
# It deliberately does NOT sleep for hours inside one process: this VM is ephemeral and reclaimed on
# inactivity, so a long in-process sleep would not survive. Schedule the WINDOWS externally:
#
#   cron (a persistent host), fire every 5h:      0 */5 * * *  cd /path/to/lu-bench && ./harness/night_sweep.sh
#   Claude Code routine (this environment):       create a trigger that sends "run ./harness/night_sweep.sh"
#                                                 on a 5-hourly cron; each firing does one window.
#
# Usage: night_sweep.sh [--window-min M] [any sweep.sh args]
#   --window-min M   stop launching new runs after M minutes (default 270 = 4.5h, margin inside a 5h window)
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WINDOW=270; PASS=()
while [ $# -gt 0 ]; do case "$1" in
  --window-min) WINDOW="$2"; shift 2;; *) PASS+=("$1"); shift;; esac; done

echo "=== night_sweep $(date -u +%FT%TZ): one window, budget ${WINDOW}m ==="
"$HERE/harness/sweep.sh" --deadline-min "$WINDOW" "${PASS[@]}"
rc=$?
echo "=== window done (rc=$rc). Re-invoke next window to continue; progress is in notes/sweep-ledger.tsv ==="
# Show what is still outstanding so the operator (or the next firing) knows if another window is needed.
done_ct=$(grep -c $'\tdone\t' "$HERE/notes/sweep-ledger.tsv" 2>/dev/null || echo 0)
fail_ct=$(grep -cE $'\tFAILED-' "$HERE/notes/sweep-ledger.tsv" 2>/dev/null || echo 0)
echo "ledger so far: ${done_ct} done, ${fail_ct} failed/limited (see notes/sweep-ledger.tsv)"
