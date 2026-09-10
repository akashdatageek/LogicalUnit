# Patch 05 — a killed run must not consume its slot, or masquerade as a model failure

> **APPLIED** 2026-09-10, once the ripgrep case study finished. Verified both directions: a
> zero-byte `result.json` writes no score and leaves the slot free; a genuine `error_max_turns`
> result is still scored. Kept as the rationale and evidence record.

## What happened

The ripgrep case study was started on `claude-sonnet-5`, then stopped 90 seconds in to switch
to `claude-opus-5`. `pkill` killed the inner `claude -p`, but `run_one.sh` continued past it:

    cp "$OUT/manifest.json" "$RUN/manifest.json" 2>/dev/null || echo '{}' > "$RUN/manifest.json"
    ...
    python3 "$HERE/harness/score.py" "$RUN" "$WORK" > "$RUN/score.json"

So the aborted attempt was scored anyway. `runs/ripgrep/3fce3b5.../1bb2d73/0/` now holds:

    result.json   0 bytes          the CLI never returned
    score.json    {"valid_nontrivial": false, "n_units": 0, "coverage": 0.0,
                   "q_gain_dir": -0.1231, "run_error": false, "result_subtype": null,
                   "cost_usd": 0.0}

## Why this matters more than it looks

Two separate problems, and the second is the serious one.

**It consumed the slot.** `(repo, label, rep)` is never rerun once `score.json` exists, so
`ripgrep/1bb2d73/0` can never be measured. Here that costs nothing — the switch to Opus moved
the work to a new label — but a kill during a real sweep permanently burns that cell.

**It is indistinguishable from a model failure.** `run_error` is `false` and `result_subtype`
is `null`, so nothing in the score says "an operator killed this". It reads exactly like a run
where the model produced zero units, and it carries a real-looking `q_gain_dir` of -0.1231
(the modularity of the empty partition, not of anything the model did). Aggregated, it would
drag down the mean for that label as if the model had failed. The earlier lost-sweep runs at
least set `run_error` and an `error_max_turns` subtype; this is worse, because it is silent.

## The fix

In `run_one.sh`, treat a zero-byte `result.json` as "the CLI never returned" and refuse to
score it, leaving the slot free:

```bash
# after the run, before collecting
if [ ! -s "$RUN/result.json" ]; then
  echo "ABORTED $RUN — the CLI produced no result (killed, or the container died)."
  echo "  Leaving the slot free: no score.json written."
  exit 3
fi
```

A zero-byte `result.json` is a clean discriminator. A run that genuinely failed still writes
JSON: the usage-limit deaths carried `terminal_reason=api_error` with a message, and a real cap
hit carries `subtype=error_max_turns`. Only a process killed before it returned leaves nothing,
and that is never the model's behaviour, so it should never enter the record as a data point.

Add a fixture alongside it: a run directory with an empty `result.json` must not produce a
score, and one with a genuine `error_max_turns` result must.

## Housekeeping for the stub already on disk

`runs/ripgrep/3fce3b5.../1bb2d73/0/` is an operator abort, not data. CLAUDE.md forbids deleting
run directories, so it stays, and this note is its provenance. Do not include label `1bb2d73`
for ripgrep in any analysis. Nothing else was ever run under that label, so the simplest rule
is to ignore the label entirely.

Note also that `1bb2d73` predates patch 06 (model in the label), which is why it is a bare sha
rather than `1bb2d73-sonnet5`.
