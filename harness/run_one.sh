#!/usr/bin/env bash
# Usage: run_one.sh owner/name sha rep [--max-turns N] [--condition skill|noskill] [--hide-docs] [--model ID] [--stratum S]
# One headless extraction. Runs are keyed by the SKILL VERSION (git sha of this harness) so
# before/after comparisons are explicit:  runs/<repo>/<sha>/<skill_label>/<rep>/
set -euo pipefail
REPO="$1"; SHA="$2"; REP="${3:-0}"; shift 3
MAX_TURNS=60; CONDITION=skill; HIDE_DOCS=0; MODEL="${LU_MODEL:-}"; STRATUM=unknown; ABLATE=""
while [ $# -gt 0 ]; do case "$1" in
  --max-turns) MAX_TURNS="$2"; shift 2;; --condition) CONDITION="$2"; shift 2;;
  --hide-docs) HIDE_DOCS=1; shift;; --model) MODEL="$2"; shift 2;; --stratum) STRATUM="$2"; shift 2;;
  --ablate) ABLATE="$2"; shift 2;; *) shift;; esac; done

HERE="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${REPO#*/}"
# Per-run checkout and output dir so repos can run concurrently. LU_WORK/LU_OUT let a
# caller pin them; the defaults keep every run isolated.
WORK="${LU_WORK:-/work/$NAME-${SHA:0:7}-$REP}"
OUT="${LU_OUT:-/out/$NAME-${SHA:0:7}-$REP}"
SKILL_LABEL="$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo nogit)"
# The model changes the measurement, so it belongs in the label. aggregate.py groups by label
# alone, so two models under one label are silently pooled — exactly the confound REVIEW.md B5
# warns about. meta.json still carries the full id. Runs before 2026-09-09 predate this and
# carry a bare label; they were all claude-sonnet-5.
if [ -n "$MODEL" ]; then
  MODEL_SLUG=$(printf '%s' "$MODEL" | sed 's/^claude-//; s/-[0-9]\{8\}$//; s/[^a-zA-Z0-9]//g')
  SKILL_LABEL="${SKILL_LABEL}-${MODEL_SLUG}"
fi
[ "$CONDITION" = skill ] || SKILL_LABEL="${SKILL_LABEL}-${CONDITION}"
[ "$HIDE_DOCS" = 1 ] && SKILL_LABEL="${SKILL_LABEL}-nodocs"
[ -n "$ABLATE" ] && SKILL_LABEL="${SKILL_LABEL}-abl${ABLATE}"
RUN="$HERE/runs/$NAME/$SHA/$SKILL_LABEL/$REP"
if [ -f "$RUN/score.json" ]; then echo "have $RUN"; exit 0; fi
mkdir -p "$RUN" "$OUT"; rm -f "$OUT/manifest.json" "$OUT/lint.log"

# 1. checkout (full clone: co-change scoring needs history)
[ -d "$WORK/.git" ] || git clone --quiet "https://github.com/$REPO" "$WORK"
git -C "$WORK" checkout --quiet --force "$SHA"; git -C "$WORK" clean -qfdx

# 2. confounds: strip the repo's own CLAUDE.md always; docs only under --hide-docs
HAS_CLAUDE_MD=$([ -f "$WORK/CLAUDE.md" ] && echo 1 || echo 0)
[ "$HAS_CLAUDE_MD" = 1 ] && mv "$WORK/CLAUDE.md" "$WORK/.CLAUDE.md.orig"
if [ "$HIDE_DOCS" = 1 ]; then
  find "$WORK" -path "$WORK/.git" -prune -o \( -iname '*.md' -o -iname '*.rst' -o -iname '*.txt' -o -iname 'ARCHITECTURE*' \) -type f -print0 | xargs -0 rm -f
  rm -rf "$WORK/docs" "$WORK/doc"
fi

# 3. overlay (skill condition) or bare schema (noskill condition)
if [ "$CONDITION" = skill ]; then
  cp -r "$HERE/overlay/." "$WORK/"; cp "$HERE/harness/resolver.py" "$WORK/.claude/hooks/"
  # Point the per-run copy of the skill at this run's output dir. The file in git is never
  # touched, so the instrument under study and overlay_hash are unchanged.
  [ "$OUT" = /out ] || sed -i "s#/out/#$OUT/#g" "$WORK/.claude/skills/lu-decompose/SKILL.md"
  # Ablation (architecture.md change 3): remove ONE top-level section from the per-run copy to
  # measure what part of the skill carries the effect. The tracked instrument is never touched;
  # only this run's copy is edited, exactly like the /out sed above. Label records which section.
  if [ -n "$ABLATE" ]; then
    case "$ABLATE" in
      definition)   HDR="## What a Logical Unit is";;
      invariants)   HDR="## The five invariants";;
      procedure)    HDR="## Procedure";;
      antipatterns) HDR="## Anti-patterns";;
      example)      HDR="## Worked example";;
      budget)       HDR="## Budget";;
      *) echo "run_one.sh: unknown --ablate section '$ABLATE'" >&2; exit 2;;
    esac
    SK="$WORK/.claude/skills/lu-decompose/SKILL.md"
    awk -v hdr="$HDR" 'BEGIN{skip=0} /^## /{ if (index($0,hdr)==1){skip=1; next} else {skip=0} } skip!=1{print}' "$SK" > "$SK.abl" && mv "$SK.abl" "$SK"
  fi
  PROMPT="/lu-decompose"
else
  mkdir -p "$WORK/.claude"; cp "$HERE/overlay/.claude/settings.json" "$WORK/.claude/"; cp -r "$HERE/overlay/.claude/hooks" "$WORK/.claude/"; cp "$HERE/harness/resolver.py" "$WORK/.claude/hooks/"
  cp "$HERE/overlay/lu-manifest.schema.json" "$WORK/"
  PROMPT="Partition this repository's source files into named units, each with entrypoints, dependencies on other units' entrypoints, and external effects. Write the result to $OUT/manifest.json conforming to lu-manifest.schema.json. Do not edit source. Do not ask questions."
fi
OVERLAY_HASH=$(find "$HERE/overlay" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-12)

# 4. run
cd "$WORK"
export CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 CLAUDE_PROJECT_DIR="$WORK" LU_OUT="$OUT"
MODEL_FLAG=(); [ -n "$MODEL" ] && MODEL_FLAG=(--model "$MODEL")
set +e
claude -p "$PROMPT" "${MODEL_FLAG[@]}" \
  --allowedTools "Read,Grep,Glob,Agent,Write,Bash(ent:*)" \
  --max-turns "$MAX_TURNS" --output-format json \
  > "$RUN/result.json" 2> "$RUN/stderr.log"
EXIT=$?
set -e

# 5. collect + provenance
# A zero-byte result.json means the CLI never returned: killed, or the container died. That is
# operator/infra action, never model behaviour, so it must not enter the record as a data point.
# Scoring it anyway consumes the (repo,label,rep) slot forever AND lands with run_error=false
# and no subtype, i.e. indistinguishable from a model that genuinely produced zero units.
# A run that really failed still writes JSON (error_max_turns, terminal_reason=api_error).
# Distinguish an account usage/rate-limit death from a generic kill. The limit message lands on
# stderr whether or not result.json was written; the driver (harness/sweep.sh) backs off and
# retries a LIMITED slot, but only retries a killed slot a few times. Either way the slot is left
# free (no score.json), so it never enters the record as a model data point.
if grep -qiE 'usage limit|rate limit|429|quota exceeded|overloaded' "$RUN/stderr.log" 2>/dev/null; then
  echo "LIMITED $RUN -- account usage/rate limit; slot left free for retry." >&2
  exit 4
fi
if [ ! -s "$RUN/result.json" ]; then
  echo "ABORTED $RUN — CLI produced no result (killed, or the container died)." >&2
  echo "  Leaving the slot free: no score.json written." >&2
  exit 3
fi
cp "$OUT/manifest.json" "$RUN/manifest.json" 2>/dev/null || echo '{}' > "$RUN/manifest.json"
cp "$OUT/lint.log" "$RUN/lint.log" 2>/dev/null || true
jq -n --arg repo "$REPO" --arg sha "$SHA" --arg rep "$REP" --arg skill "$SKILL_LABEL" --arg overlay "$OVERLAY_HASH" \
      --arg cond "$CONDITION" --argjson hide_docs "$HIDE_DOCS" --argjson has_claude_md "$HAS_CLAUDE_MD" --arg stratum "$STRATUM" \
      --argjson exit "$EXIT" --argjson max_turns "$MAX_TURNS" --arg model "${MODEL:-default}" \
      --arg cc_version "$(claude --version 2>/dev/null | head -1)" --arg date "$(date -u +%FT%TZ)" \
      --arg session "$(jq -r '.session_id // ""' "$RUN/result.json")" \
      '{repo:$repo, sha:$sha, rep:$rep, skill_label:$skill, overlay_hash:$overlay, condition:$cond, hide_docs:$hide_docs,
        has_claude_md:$has_claude_md, exit:$exit, max_turns:$max_turns, model:$model, claude_code:$cc_version, date:$date, session_id:$session, stratum:$stratum}' \
      > "$RUN/meta.json"
python3 "$HERE/harness/score.py" "$RUN" "$WORK" > "$RUN/score.json"
echo "done $RUN exit=$EXIT cost=$(jq -r '.total_cost_usd // "?"' "$RUN/result.json")"
