# Patches — apply order and rationale

Everything outside `SKILL.md`, `overlay/examples/*.json`, `notes/*.md` and `results.tsv` is
fixed for the experiment and a hook enforces it. These changes are in fixed files, so they are
written here as reviewable patches rather than applied. Each one has been built and run against
real data; the verified output is quoted in the patch.

Apply in this order. Patches 01 and 03 belong together: 03 is how you verify 01.

| # | Change | Files | Verified |
|---|--------|-------|----------|
| 01 | Honour directory-prefix exclusions; tolerate a malformed manifest | `harness/score.py`, `overlay/.claude/hooks/lint_stub.py` | reproduced the defect and its cost |
| 02 | `harness/headroom.py` — pre-flight a repo before it costs a model call | new file | run against all 7 clones |
| 03 | `harness/test_score.py` — fixture tests for the scorer | new file | 4/7 pass on the current scorer |
| 04 | Per-run output path so repositories run concurrently | `run_one.sh`, 3 overlay hooks | measured ceiling, not run |
| 05 | Set `ANTHROPIC_API_KEY` in the environment | environment only | — |

Patch 05 has no file: the inner `claude -p` runs inherit subscription auth and hit the account
cap. That killed one entire sweep (18 of 28 slots, ~$60) and stalled the surviving sweep for
about four hours across two windows. It is the cheapest fix on this list and it should land
before patch 04, because running seven repositories concurrently reaches the cap seven times
faster.

## Why 01 is first

It is one bug in two files and it causes three separate problems. `excluded` is matched by
exact path, so excluding a directory excludes nothing. That inflates the coverage denominator
(fastapi scored 0.09 where prefix-aware coverage is 1.00), it crashes the scorer on a manifest
entry with no `path` key, and — the part that was not obvious — the lint hook reports every
file under an excluded directory as unassigned, which pushes the model into enumerating files
one at a time. That enumeration is generated output, output drives runtime at 7,200 tokens per
minute, and runtime drives the turn cap that killed 8 of 21 baseline runs.

Fixing it changes both what is measured and how the runs behave, which is why it goes first
and why the next baseline has to be re-run rather than compared against `cac873e`.

## What is deliberately not here

**No untested edits to SKILL.md.** Phase 1 produced four more hypotheses than the single
iteration tested. They are written as pre-registered predictions under
`## QUEUED iteration N` in `notes/rq2.md`, to be run one at a time. Applying them as
"improvements" would be exactly the anti-pattern the ratchet exists to prevent.

**No change to `score.py`'s hardcoded SKIP list.** It looks like a companion to patch 01 but
it is not: it silently redefines what counts as source, changes every historical score, and is
a sampling-frame decision belonging in pre-registration. With prefix exclusion working, a
manifest can declare its own scope, which is the more principled design.

**No change to the primary outcome metric.** `notes/rq1.md` H4 and the readout argue that
`q_gain_dir` cannot reward good work on four of seven dev repos, and recommend promoting gold
agreement to primary. That is a pre-registration change to `program.md`, which says explicitly
not to edit it during a run. It needs a deliberate decision, not a patch.

## After applying

1. `python3 harness/test_score.py` — all seven must pass.
2. `python3 harness/headroom.py --corpus` — expect 3 of 7 MEASURABLE; decide the corpus on it.
3. Re-score existing runs in place rather than re-running them (command in patch 01), and
   record which scorer sha produced each `results.tsv` row.
4. Re-baseline. Do not compare a post-patch label against `cac873e`: the scorer changed, so
   the comparison is not paired.
