#!/usr/bin/env bash
# Usage: run_one.sh owner/name sha rep [--max-turns N] [--condition skill|noskill] [--hide-docs] [--model ID] [--stratum S]
# One headless extraction. Runs are keyed by the SKILL VERSION (git sha of this harness) so
# before/after comparisons are explicit:  runs/<repo>/<sha>/<skill_label>/<rep>/
set -euo pipefail
REPO="$1"; SHA="$2"; REP="${3:-0}"; shift 3
MAX_TURNS=60; CONDITION=skill; HIDE_DOCS=0; MODEL="${LU_MODEL:-}"; STRATUM=unknown
while [ $# -gt 0 ]; do case "$1" in
  --max-turns) MAX_TURNS="$2"; shift 2;; --condition) CONDITION="$2"; shift 2;;
  --hide-docs) HIDE_DOCS=1; shift;; --model) MODEL="$2"; shift 2;; --stratum) STRATUM="$2"; shift 2;; *) shift;; esac; done

HERE="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${REPO#*/}"; WORK="/work/$NAME"
SKILL_LABEL="$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo nogit)"
[ "$CONDITION" = skill ] || SKILL_LABEL="${SKILL_LABEL}-${CONDITION}"
[ "$HIDE_DOCS" = 1 ] && SKILL_LABEL="${SKILL_LABEL}-nodocs"
RUN="$HERE/runs/$NAME/$SHA/$SKILL_LABEL/$REP"
if [ -f "$RUN/score.json" ]; then echo "have $RUN"; exit 0; fi
mkdir -p "$RUN" /out; rm -f /out/manifest.json /out/lint.log

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
  PROMPT="/lu-decompose"
else
  mkdir -p "$WORK/.claude"; cp "$HERE/overlay/.claude/settings.json" "$WORK/.claude/"; cp -r "$HERE/overlay/.claude/hooks" "$WORK/.claude/"; cp "$HERE/harness/resolver.py" "$WORK/.claude/hooks/"
  cp "$HERE/overlay/lu-manifest.schema.json" "$WORK/"
  PROMPT="Partition this repository's source files into named units, each with entrypoints, dependencies on other units' entrypoints, and external effects. Write the result to /out/manifest.json conforming to lu-manifest.schema.json. Do not edit source. Do not ask questions."
fi
OVERLAY_HASH=$(find "$HERE/overlay" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-12)

# 4. run
cd "$WORK"
export CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 CLAUDE_PROJECT_DIR="$WORK"
MODEL_FLAG=(); [ -n "$MODEL" ] && MODEL_FLAG=(--model "$MODEL")
set +e
claude -p "$PROMPT" "${MODEL_FLAG[@]}" \
  --allowedTools "Read,Grep,Glob,Agent,Write,Bash(ent:*)" \
  --max-turns "$MAX_TURNS" --output-format json \
  > "$RUN/result.json" 2> "$RUN/stderr.log"
EXIT=$?
set -e

# 5. collect + provenance
cp /out/manifest.json "$RUN/manifest.json" 2>/dev/null || echo '{}' > "$RUN/manifest.json"
cp /out/lint.log "$RUN/lint.log" 2>/dev/null || true
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
