#!/usr/bin/env bash
# ablation_sweep.sh — which parts of SKILL.md carry the effect? (notes/architecture.md change 3)
#
# The noskill control is all-or-nothing; this fills in the middle. It runs, at the current skill
# sha, the full skill and each single-section ablation, plus the bare prompt, on the MEASURABLE
# repos. Each arm lands under its own label so aggregate.py compares them directly:
#
#   <sha>                full skill
#   <sha>-abl<section>   skill minus that one section   (section in: definition procedure antipatterns example)
#   <sha>-noskill        bare prompt (no skill at all)
#
# Usage: ablation_sweep.sh [reps] [repos]
#   reps   default 0,1,2
#   repos  default 'ripgrep' (the one MEASURABLE dev repo; pass a comma list to widen)
#
# Cost warning: this is (2 + #sections) arms x #repos x #reps model calls. On ripgrep at 3 reps
# that is 18 runs. Pre-flight with headroom.py and watch the account limit; drive it through
# harness/sweep.sh so a killed run is retried, not lost.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPS="${1:-0,1,2}"
REPOS="${2:-ripgrep}"
SECTIONS="definition procedure antipatterns example"

echo "== full skill =="
"$HERE/harness/run_corpus.sh" --reps "$REPS" --only "$REPOS"
for sec in $SECTIONS; do
  echo "== ablate: $sec =="
  "$HERE/harness/run_corpus.sh" --reps "$REPS" --only "$REPOS" --ablate "$sec"
done
echo "== bare prompt (noskill) =="
"$HERE/harness/run_corpus.sh" --reps "$REPS" --only "$REPOS" --condition noskill

SHA="$(git -C "$HERE" rev-parse --short HEAD)"
echo
echo "Compare arms (per label):"
echo "  python3 harness/aggregate.py --label $SHA"
for sec in $SECTIONS; do echo "  python3 harness/aggregate.py --label $SHA-abl$sec"; done
echo "  python3 harness/aggregate.py --label $SHA-noskill"
echo "  python3 harness/units.py    --label $SHA        # unit-level view of the same arms"
