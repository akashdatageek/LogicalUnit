#!/usr/bin/env bash
# SessionStart hook for the harness repo. Installs the resolver's dependencies when missing.
# Runs as a hook (outside the agent's permission list), so the agent's pip deny rule does not apply.
# Fast no-op when already installed; cached by the cloud environment snapshot if you also put it in a setup script.
set -u
if python3 -c "import tree_sitter_language_pack, networkx" 2>/dev/null; then exit 0; fi
pip install -q tree-sitter tree-sitter-language-pack networkx 2>/dev/null \
  || pip install -q --break-system-packages tree-sitter tree-sitter-language-pack networkx 2>/dev/null \
  || echo "session_setup: could not install tree-sitter deps; score.json will report regex-fallback" >&2
exit 0
