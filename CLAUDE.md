# lu-bench — harness context (loaded every session)

This repo runs a benchmark, it is not the code under test. You orchestrate
extraction runs against external repos, score them, and iterate on ONE file.

## What you may edit
- overlay/.claude/skills/lu-decompose/SKILL.md   (the instruction under study)
- overlay/examples/*.json                         (worked examples; add sparingly)
- notes/*.md, results.tsv                         (your lab notebook)
Everything else is fixed for the experiment. A hook enforces this.

## Every session starts with
    ./harness/status.sh          # which phase, what next — the repo is the memory, not you
and ends with
    ./harness/checkpoint.sh "…"  # commit + push runs/ notes/ results.tsv; uncommitted work dies with the VM

## Before you trust a number
    python3 harness/test_score.py                         8 scorer fixtures; must be 8/8 (2 s)
    python3 harness/calibrate.py                          instrument sensitivity/specificity on synthetic gold; 8/8 (3 s, no model call)
    python3 harness/headroom.py --corpus                  which repos can show a gain at all (48 s, no model call)
A repo whose q_dir is ~0 cannot produce a positive q_gain_dir however good the decomposition
is. Four of the seven current dev repos are in that state; treat them as controls.

## Commands
    ./harness/pin_corpus.sh                               replace PIN_ME with HEAD shas (mechanical; allowed)
    ./harness/run_one.sh <owner/name> <sha> <rep> [--condition noskill] [--hide-docs] [--ablate SECTION]
    ./harness/run_corpus.sh [--reps 0,1,2] [--only a,b] [--condition ..] [--hide-docs] [--ablate SECTION]
    ./harness/sweep.sh [--reps ..] [--only ..] [--parallel N] [--retries K] [--deadline-min M] [..]   resumable, limit-aware driver; writes notes/sweep-ledger.tsv
    ./harness/night_sweep.sh [--window-min M] [sweep args]   one usage-window's worth, then stop cleanly (schedule per window externally)
    ./harness/ablation_sweep.sh [reps] [repos]            full skill vs each single-section ablation vs bare prompt
    python3 harness/aggregate.py [--label <sha>]          per-repo table, corpus primaries
    python3 harness/aggregate.py --decide <before> <after> KEEP/REVERT — final, not advisory
    python3 harness/aggregate.py --decide-transfer <before> <after> --models m1,m2   KEEP only if it holds on every model
    python3 harness/units.py [--label <sha>] | --decide <before> <after>   unit-level analysis (~200 units, not ~16 runs)
    python3 harness/aggregate.py --budget [--label <sha>] [--weekly-tokens N]   per-repo token/cost rollup + runs/week capacity
    python3 harness/aggregate.py --tsv >> results.tsv     one row per kept skill version
    python3 harness/rescore.py [--apply]                  re-score runs in place after a scorer change (backfills per-unit records)

--ablate SECTION strips ONE top-level SKILL.md section from the per-run copy only (the tracked
instrument is never touched). SECTION in: definition invariants procedure antipatterns example budget.

Transfer is now part of the KEEP gate, not a final phase (program.md, notes/architecture.md change 4):
an edit must hold on two models. Set the primary model with LU_MODEL and the second with the id below,
then confirm an edit with `aggregate.py --decide-transfer`. Ask the human to fill this in:
    LU_MODEL_SECONDARY=<model-id>

## Conventions
- Skill edits are git commits on this repo. One change per commit. Commit message
  starts with the edit category: [definition] [procedure] [example] [antipattern] [stopping].
- Keep/revert is decided by `aggregate.py --decide`, never by you. Revert = `git revert --no-edit HEAD`.
- Holdout repos (harness/holdout.txt) are never run by you.
- Runs live in runs/<repo>/<sha>/<skill_label>/<rep>/ and are never deleted, moved, or rerun.
- There is no human in the loop. Never ask a question. Never stop without checkpointing.
- You may be resumed by a supervisor, a cloud session, or a routine. Assume no memory of prior sessions.
