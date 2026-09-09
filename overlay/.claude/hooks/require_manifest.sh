#!/usr/bin/env bash
# Stop hook. Refuses to let the session end without a manifest.
# stop_hook_active guards against an infinite loop. Verify Stop-hook blocking
# semantics against the current hooks reference before relying on this.
set -uo pipefail
input=$(cat)
active=$(printf '%s' "$input" | jq -r '.stop_hook_active // false')
[ "$active" = "true" ] && exit 0
OUT="${LU_OUT:-/out}"
if [ ! -s "$OUT/manifest.json" ]; then
  echo "You must write $OUT/manifest.json before stopping. Write the best partial manifest you have, with an honest 'unpartitioned' list." >&2
  exit 2
fi
python3 -c "import json,os; json.load(open(os.environ.get('LU_OUT','/out')+'/manifest.json'))" 2>/dev/null || {
  echo "$OUT/manifest.json is not valid JSON. Fix it before stopping." >&2; exit 2; }
exit 0
