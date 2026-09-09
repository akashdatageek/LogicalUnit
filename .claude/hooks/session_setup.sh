#!/usr/bin/env bash
# SessionStart hook for the harness repo. Installs the resolver's dependencies when missing.
# Runs as a hook (outside the agent's permission list), so the agent's pip deny rule does not apply.
# Fast no-op when already installed; cached by the cloud environment snapshot if you also put it in a setup script.
set -u
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
REQ="$HERE/requirements.txt"

if ! python3 -c "import tree_sitter_language_pack, networkx" 2>/dev/null; then
  if [ -f "$REQ" ]; then
    pip install -q -r "$REQ" 2>/dev/null || pip install -q --break-system-packages -r "$REQ" 2>/dev/null || true
  else
    pip install -q tree-sitter tree-sitter-language-pack networkx 2>/dev/null \
      || pip install -q --break-system-packages tree-sitter tree-sitter-language-pack networkx 2>/dev/null || true
  fi
  python3 -c "import tree_sitter_language_pack, networkx" 2>/dev/null \
    || echo "session_setup: tree-sitter deps missing; score.json will report regex-fallback" >&2
fi

# Check the instrument before the session trusts a number. Warn only: a failing scorer is a
# finding to write up, not a reason to refuse the session.
if [ -f "$HERE/harness/test_score.py" ]; then
  python3 "$HERE/harness/test_score.py" >/tmp/lu-test_score.out 2>&1 \
    || echo "session_setup: harness/test_score.py FAILED — scores are suspect; see /tmp/lu-test_score.out" >&2
fi
exit 0
