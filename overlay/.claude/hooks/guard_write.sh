#!/usr/bin/env bash
# PreToolUse on Write|Edit. Exit 2 blocks the call; stderr is fed back to Claude.
set -euo pipefail
input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
case "$path" in
  /out/manifest.json) exit 0 ;;
  *) echo "BLOCKED: only /out/manifest.json may be written. Attempted: $path" >&2; exit 2 ;;
esac
