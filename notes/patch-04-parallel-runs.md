# Patch 04 — per-run output path, so repositories can run concurrently

**Priority: apply before the next full sweep.** Largest available throughput win. It changes
no measurement, only where a run writes its manifest.

## The constraint today

Every run writes `/out/manifest.json`. `run_one.sh` clears that path at the start of each run:

    mkdir -p "$RUN" /out; rm -f /out/manifest.json /out/lint.log

Two concurrent runs would overwrite each other, so the whole corpus is strictly serial. The
21-run baseline sweep was 5.3 hours of pure generation; elapsed time was far worse because
usage-limit waits sat on top of it.

Measured per-run durations make the ceiling obvious: MAVSDK rep 0 alone was 59 minutes, and
the median run was 12.

| scheduling | wall-clock |
|---|---|
| serial (today) | 5.3 h |
| 7-way, one worker per repo | ~2 h (bound by MAVSDK's three replicates) |
| 21-way, one worker per run | ~59 min (bound by the single slowest run) |

## The change

Three files. `LU_OUT` defaults to `/out`, so nothing breaks if a caller does not set it.

### harness/run_one.sh

```bash
# before
mkdir -p "$RUN" /out; rm -f /out/manifest.json /out/lint.log
...
export CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 CLAUDE_PROJECT_DIR="$WORK"
...
cp /out/manifest.json "$RUN/manifest.json" 2>/dev/null || echo '{}' > "$RUN/manifest.json"
cp /out/lint.log "$RUN/lint.log" 2>/dev/null || true

# after
OUT="${LU_OUT:-/out/$NAME-$REP-$$}"
mkdir -p "$RUN" "$OUT"; rm -f "$OUT/manifest.json" "$OUT/lint.log"
...
export CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 CLAUDE_PROJECT_DIR="$WORK" LU_OUT="$OUT"
...
cp "$OUT/manifest.json" "$RUN/manifest.json" 2>/dev/null || echo '{}' > "$RUN/manifest.json"
cp "$OUT/lint.log" "$RUN/lint.log" 2>/dev/null || true
```

The clone path also has to be per-run, since `run_one.sh` does a `git checkout --force` plus
`git clean -qfdx` in `/work/$NAME`. Two workers on the same repo would corrupt each other:

```bash
# before
NAME="${REPO#*/}"; WORK="/work/$NAME"

# after — one checkout per (repo, sha), shared only by runs that want the same tree
NAME="${REPO#*/}"; WORK="/work/$NAME-${SHA:0:7}-$REP"
```

Disk is the trade: 21 clones instead of 7. Cheaper than 4 extra hours.

### overlay/.claude/hooks/guard_write.sh

```bash
# before
case "$path" in
  /out/manifest.json) exit 0 ;;

# after
case "$path" in
  "${LU_OUT:-/out}/manifest.json") exit 0 ;;
```

### overlay/.claude/hooks/lint_manifest.sh and require_manifest.sh

Replace each literal `/out/manifest.json` and `/out/lint.log` with `"${LU_OUT:-/out}/..."`.
`lint_manifest.sh` also writes `/tmp/lint.last`, which two concurrent runs would race over —
make it `"$OUT/lint.last"`.

### The skill

`SKILL.md` names `/out/manifest.json` in five places. The runs are what read that instruction,
so the path has to reach the model. Either interpolate it, or keep `/out` in the prose and
bind-mount the per-run directory there. **The prose is the instrument under study — changing
its wording changes what is being measured.** A bind mount keeps the skill byte-identical
across the change, which is the safer option and is what I would do.

## Then use it

`run_corpus.sh` already accepts `--shard i/n` (added in v1.2). With per-run outputs, sharding
becomes real parallelism on one machine:

    for i in 0 1 2 3 4 5 6; do
      ./harness/run_corpus.sh --reps 0,1,2 --shard $i/7 &
    done; wait

Watch the account rate limit before raising concurrency: seven concurrent runs reach the
usage cap roughly seven times faster. Patch 05 (the API key) should land first.
