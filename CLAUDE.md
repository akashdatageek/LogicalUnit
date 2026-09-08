# lu-bench — harness context (loaded every session)

This repo runs a benchmark, it is not the code under test. You orchestrate
extraction runs against external repos, score them, and iterate on ONE file.

## What you may edit
- overlay/.claude/skills/lu-decompose/SKILL.md   (the instruction under study)
- overlay/examples/*.json                         (worked examples; add sparingly)
- notes/*.md, results.tsv                         (your lab notebook)
Everything else is fixed for the experiment. A hook enforces this.

## Commands
    ./harness/run_one.sh <owner/name> <sha> <rep> [--condition noskill] [--hide-docs]
    ./harness/run_corpus.sh [--reps 0,1,2] [--only a,b] [--condition ..] [--hide-docs]
    python3 harness/aggregate.py [--label <sha>]          per-repo table, corpus primaries
    python3 harness/aggregate.py --decide <before> <after> KEEP/REVERT — final, not advisory
    python3 harness/aggregate.py --tsv >> results.tsv     one row per kept skill version

Second model for the transfer check (RQ5): set LU_MODEL to it. Ask the human to fill this in:
    LU_MODEL_SECONDARY=<model-id>

## Conventions
- Skill edits are git commits on this repo. One change per commit. Commit message
  starts with the edit category: [definition] [procedure] [example] [antipattern] [stopping].
- Keep/revert is decided by `aggregate.py --decide`, never by you. Revert = `git revert --no-edit HEAD`.
- Holdout repos (harness/holdout.txt) are never run by you.
- Runs live in runs/<repo>/<sha>/<skill_label>/<rep>/ and are never deleted, moved, or rerun.
- There is no human in the loop. Never ask a question. Never stop without a summary in notes/.
