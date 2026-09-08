# BLOCKED — Phase 0 step 4: harness (score.py) mis-detects budget exhaustion (2026-09-08 22:35 UTC)

## What is wrong

`harness/score.py` line ~155:

    budget_exhausted = bool(max_turns and turns and turns >= max_turns)

`turns` is `num_turns` from the CLI's JSON result. In Claude Code 2.1.265 that counter
includes turns spent by subagents (the skill spawns one unit-scout per candidate unit),
so it routinely exceeds `--max-turns` on runs that finished normally. Evidence, run
runs/requests/dae7ef6…/f82b175/0:

    result.json: subtype=success  is_error=false  terminal_reason=completed  stop_reason=end_turn
                 num_turns=57  subagent_stats.spawned=13
    meta.json:   max_turns=40
    score.json:  budget_exhausted=true  ->  valid_nontrivial=false   (coverage 1.0, edge_res 1.0, 13 units)

`valid_nontrivial` is the pre-registered PRIMARY gate. With this bug nearly every run that
uses scouts is scored invalid, `aggregate.py --decide` would REVERT every edit on the
validity gate, and the ratchet cannot run. score.py is a fixed file (guard hook), so the
fix is a human action.

## Proposed fix (one line, harness/score.py)

    budget_exhausted = res.get('subtype') == 'error_max_turns' or res.get('terminal_reason') not in (None, 'completed')

(`subtype` is `error_max_turns` when --max-turns is actually hit; keep the old expression
only as a fallback for result.json files that lack both fields.) Commit as a harness
change. Optionally re-score the existing Phase 0 run without rerunning it:

    python3 harness/score.py runs/requests/dae7ef63b4df6eded86637f251fc4e3a06c3b479/f82b175/0 /work/requests \
      > runs/requests/dae7ef63b4df6eded86637f251fc4e3a06c3b479/f82b175/0/score.json

## Not blocking, but decide before Phase 1

- `.claude/hooks/lint_stub.py` I4 regex for `network` is `\b(requests|…)\b`; it matches the
  word "requests" anywhere (the psf/requests package name, docstrings), so every file is
  flagged and the model declares bogus `network` effects to pass lint (effects_p 0.19 on
  this run). Same for all skill versions, but it burns a lint round per run and makes
  effects precision meaningless on that repo. Consider anchoring to `import requests` /
  `from requests`.
- Cost/time per run at 40 turns: $3.73, 13.5 min. Phase 1 is 7 repos x 3 reps + 7 noskill
  = 28 runs at --max-turns 60: expect roughly $100–150 and 6–8 h sequential (runs share
  /out, so they cannot be parallelised). Usage limits: the account's session limit
  killed attempt 1; a long sweep will hit it again unless LU_MODEL / plan allow it.
- `LU_MODEL` is unset (runs use the CLI default, currently claude-sonnet-5). Pin it before
  Phase 1 so the baseline label is comparable across days. `LU_MODEL_SECONDARY` also unset
  (Phase 4 will be skipped).
- Workspace trust warning ("Ignoring 6 permissions.allow entries") is harmless: hooks,
  skill and agents load; --allowedTools from run_one.sh governs. The agent's own attempt
  to pre-trust /work/* in /root/.claude.json was denied by the sandbox policy.

## To resume

Fix score.py (and optionally lint_stub.py), commit, delete this file, re-run the resume
prompt. status.sh will find notes/phase0.md and go to Phase 1 (tag baseline, sweep).

## Resolution (2026-09-08 ~23:00 UTC)
Human shipped lu-bench v1.2 (REVIEW.md F1-F4): score.py now derives budget_exhausted from the
result subtype/terminal_reason and reports run_error, result_subtype, singleton_unit_frac;
resolver ignores in-repo imports as effects; lint stub regex anchored to import forms;
run_corpus.sh gained --shard. Archived; loop resumes.
