#!/usr/bin/env bash
# Replace every PIN_ME in corpus.txt with the current HEAD sha of that repo. Mechanical, so the agent may run it.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; C="$HERE/harness/corpus.txt"
n=0
for r in $(grep -v '^#' "$C" | awk '$2=="PIN_ME"{print $1}'); do
  sha=$(git ls-remote "https://github.com/$r" HEAD 2>/dev/null | cut -f1)
  if [ -n "$sha" ]; then sed -i "s|^$r .*PIN_ME|$r $sha|" "$C"; n=$((n+1)); echo "pinned $r $sha"; else echo "could not pin $r" >&2; fi
done
echo "pinned $n repo(s); remaining PIN_ME: $(grep -c PIN_ME "$C" || true)"
