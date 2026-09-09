#!/usr/bin/env bash
# PostToolUse on Write. Runs the deterministic checker and feeds violations back.
# Exit 2 + stderr = Claude sees the violations as feedback (the write already happened).
set -uo pipefail
input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
OUT="${LU_OUT:-/out}"
[ "$path" = "$OUT/manifest.json" ] || exit 0
mkdir -p "$OUT"
{
  echo "=== lint round $(date +%s) ==="
  if command -v ent >/dev/null 2>&1; then
    ent ci --lint "$OUT/manifest.json" --repo "$CLAUDE_PROJECT_DIR" 2>&1; echo "exit=$?"
  else
    python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/lint_stub.py "$OUT/manifest.json" "$CLAUDE_PROJECT_DIR" 2>&1; echo "exit=$?"
  fi
} | tee -a "$OUT/lint.log" > "$OUT/lint.last"
if grep -q '^exit=0$' "$OUT/lint.last"; then exit 0; fi
cat "$OUT/lint.last" >&2
exit 2
