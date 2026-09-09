#!/usr/bin/env bash
# Local / self-hosted supervisor: keeps re-launching the loop until DONE, BLOCKED, or WAITING.
# Each launch is a fresh headless session that resumes from repo state via status.sh.
# Usage: supervise.sh [max_launches=20] [turns_per_launch=300]
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
MAX="${1:-20}"; TURNS="${2:-300}"
for i in $(seq 1 "$MAX"); do
  ./harness/status.sh > /tmp/lu-status.txt 2>&1; rc=$?
  cat /tmp/lu-status.txt
  case "$rc" in 2) echo "supervise: stopped (human action needed)"; exit 2;; esac
  grep -q '^DONE' /tmp/lu-status.txt && { echo "supervise: done"; exit 0; }
  echo "=== launch $i/$MAX $(date -u +%FT%TZ) ==="
  claude -p "Read CLAUDE.md, program.md, and LOOP.md. Run ./harness/status.sh and resume LOOP.md at the phase it names. Work until that phase (or one ratchet iteration) is complete, run ./harness/checkpoint.sh, then stop." \
    --max-turns "$TURNS" --output-format json > "notes/launch-$i.json" 2> "notes/launch-$i.err" || true
  ./harness/checkpoint.sh "launch $i" || true
  sleep 5
done
echo "supervise: launch budget exhausted; run again to continue"
