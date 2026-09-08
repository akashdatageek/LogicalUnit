#!/usr/bin/env bash
# Where is the loop? Derives the current phase from repo state alone, so a fresh session can resume.
# Prints:  PHASE <n>  <one-line reason>   then  NEXT: <command or instruction>
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
MAX_ITER="${LU_MAX_ITER:-12}"
say(){ echo "PHASE $1  $2"; echo "NEXT: $3"; exit 0; }

[ -f notes/BLOCKED.md ]      && { echo "BLOCKED  $(head -1 notes/BLOCKED.md)"; echo "NEXT: human action; see notes/BLOCKED.md. Delete it after fixing to resume."; exit 2; }
[ -f notes/SUMMARY.md ]      && { echo "DONE  notes/SUMMARY.md exists"; echo "NEXT: nothing; the run is finished."; exit 0; }
[ -f notes/NEED_CORPUS.md ]  && { echo "WAITING  dev set too small"; echo "NEXT: human runs build_corpus.py as described in notes/NEED_CORPUS.md, updates holdout.txt, deletes NEED_CORPUS.md."; exit 2; }

grep -q PIN_ME harness/corpus.txt && say 0 "corpus has PIN_ME rows" "./harness/pin_corpus.sh && git commit -am 'pin corpus'"
python3 -c "import tree_sitter_language_pack, networkx" 2>/dev/null || say 0 "tree-sitter deps missing" "hook should have installed them; if still missing write notes/BLOCKED.md"
[ -f notes/phase0.md ]       || say 0 "no phase0 note" "run_one.sh psf/requests <sha> 0 --max-turns 40, read the manifest, write notes/phase0.md"

git rev-parse -q --verify baseline >/dev/null || say 1 "no baseline tag" "git tag baseline; then ./harness/run_corpus.sh --reps 0,1,2"
BASE=$(git rev-parse --short baseline)
NDEV=$(python3 harness/aggregate.py --n-dev); HAVE=$(find runs -path "*/$BASE/*/score.json" 2>/dev/null | wc -l)
[ "$HAVE" -lt $((NDEV*3)) ]  && say 1 "baseline runs $HAVE/$((NDEV*3))" "./harness/run_corpus.sh --reps 0,1,2   (resumable) then ./harness/run_corpus.sh --reps 0 --condition noskill"
[ -f notes/rq1.md ]          || say 1 "baseline complete, no rq1.md" "aggregate.py --label $BASE; code failures with CODEBOOK; write notes/rq1.md"

NEED=$(python3 harness/power.py --from-runs --label "$BASE" --delta 0.02 --min-n 2>/dev/null | tail -1)
[ "${NEED:-999}" -gt "$NDEV" ] 2>/dev/null && say 2 "gate: need $NEED dev repos, have $NDEV" "write notes/NEED_CORPUS.md (both numbers + build_corpus command), then Phase 3"
ITER=$(grep -c '^## iteration' notes/rq2.md 2>/dev/null || echo 0)
[ "$ITER" -ge "$MAX_ITER" ]  && { [ -f notes/rq4.md ] || say 3 "ratchet budget spent ($ITER/$MAX_ITER)" "recall control: run_corpus.sh --reps 0 --hide-docs --only ripgrep,MAVSDK,flask,nest; write notes/rq4.md"; say 6 "phases 2-3 complete" "write notes/SUMMARY.md"; }
HEAD_L=$(git rev-parse --short HEAD)
if [ "$HEAD_L" != "$BASE" ] && [ -z "$(find runs -path "*/$HEAD_L/*/score.json" 2>/dev/null)" ]; then
  say 2 "iteration $((ITER+1)): HEAD ($HEAD_L) is an unscored edit" "run the targeted repos named in notes/rq2.md, then full dev, then aggregate.py --decide <prev> $HEAD_L"
fi
say 2 "iteration $((ITER+1)) of $MAX_ITER" "pick next hypothesis from notes/rq1.md; write prediction to notes/rq2.md under '## iteration $((ITER+1))'; edit SKILL.md; commit"
