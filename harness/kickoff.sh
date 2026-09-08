#!/usr/bin/env bash
# Start the overnight research loop. Run from the lu-bench root, inside the container.
# Prereqs: corpus.txt pinned, `claude` on PATH, ANTHROPIC_API_KEY set, git repo initialised.
set -euo pipefail
cd "$(dirname "$0")/.."
git rev-parse HEAD >/dev/null 2>&1 || { git init -q && git add -A && git commit -qm "lu-bench initial"; }
mkdir -p notes runs
claude -p "Read CLAUDE.md, program.md, and LOOP.md. Then execute LOOP.md from Phase 0." \
  --max-turns 800 \
  --output-format json \
  > notes/loop-result.json 2> notes/loop-stderr.log
echo "loop finished: $(jq -r '.subtype // .type' notes/loop-result.json)  cost=$(jq -r '.total_cost_usd // "?"' notes/loop-result.json)"
