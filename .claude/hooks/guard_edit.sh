#!/usr/bin/env bash
# Outer-loop guard: the research agent may only touch the skill, examples, and its notebook.
set -euo pipefail
input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
rel="${path#$CLAUDE_PROJECT_DIR/}"
case "$rel" in
  overlay/.claude/skills/lu-decompose/SKILL.md) exit 0 ;;
  overlay/examples/*.json) exit 0 ;;
  notes/*.md|results.tsv) exit 0 ;;
  *) echo "BLOCKED: '$rel' is fixed for this experiment. Editable: SKILL.md, overlay/examples/*.json, notes/*.md, results.tsv" >&2; exit 2 ;;
esac
