# lu-bench — Logical Unit extraction benchmark

Point Claude Code at a repo, get back an LU manifest, score it deterministically.
Then let an agent iterate on the skill overnight.

**State as of 2026-09-09:** one full run is complete. Baseline tagged (`baseline`, label
`cac873e`), one ratchet iteration attempted and reverted, findings in `notes/SUMMARY.md`.
Several harness defects that run exposed are now fixed. **The scorer changed afterwards, so
a re-baseline is required before any new label can be compared with `cac873e`.**

## Install

    pip install -r requirements.txt        # tree-sitter, tree-sitter-language-pack, networkx
    python3 harness/test_score.py          # 8 fixtures; must print 8/8 before you trust a score

`.claude/hooks/session_setup.sh` installs the same dependencies automatically at session
start, so the manual step is a convenience rather than a requirement. Also needed on PATH:
`claude`, `git`, `jq`. `ent` is optional — the lint hook falls back to a stub.

## Run the free checks first

Three things run before any model call. They cost nothing and they exist because the first
full run spent $253 discovering something two of them detect in under a minute.

    python3 harness/test_score.py          # is the instrument correct?     2 s
    python3 harness/headroom.py --corpus   # can this corpus show anything? 48 s

`headroom.py` is the one to run before choosing repos. `q_gain_dir` is the model's modularity
minus the better of two zero-intelligence baselines, and the one-unit baseline is 0 by
construction. On a repo whose source is a single flat package the directory baseline is also
~0, so gain collapses to raw modularity and goes negative for any partition that cuts a dense
import graph. Such a repo cannot show a positive result however good the decomposition is.
On the current corpus that is 4 of 7 repos. Admit them knowingly, as controls.

## Layout

    CLAUDE.md                   harness rules the outer agent sees every session
    program.md                  PRE-REGISTERED outcomes, decision rule, RQ1-RQ5
    REVIEW.md                   research-methodology review: what was wrong in v0 and what changed
    CORPUS_PLAN.md              sampling frame, strata, gold subset, dev/holdout split
    PILOT.md                    what the 10-repo pilot must establish before scaling; pass criteria
    LOOP.md                     the procedure: Phase 0 sanity -> 1 baseline -> 2 ratchet -> 3 confounds -> 6 write-up
    FILES.md                    every file, who reads it, whether it may change
    requirements.txt            pinned Python dependencies
    .claude/settings.json       outer-agent permissions + guard_edit hook (may only edit SKILL.md/examples/notes)
    results.tsv                 one row per kept skill version (appended by aggregate.py --tsv)
    notes/                      the agent's lab notebook (see below)
    gold/<repo>.json            human gold decompositions (optional; enables gold_ari/nmi)
    overlay/                    copied INTO each repo checkout before a run
      .claude/skills/lu-decompose/SKILL.md   the decomposition instruction (the thing RQ2 edits)
      .claude/agents/unit-scout.md           read-only subagent, one per candidate unit
      .claude/settings.json                  hooks + permissions
      .claude/hooks/*.sh                     guard writes, lint manifest, refuse to stop without one
      lu-manifest.schema.json                output contract
      examples/                              one worked example the skill references
    harness/
      run_one.sh                 clone at pinned sha, apply overlay, run `claude -p`, collect, score
      run_corpus.sh              all repos x replicates, resumable, --shard i/n
      resolver.py                tree-sitter static analysis: exported symbols, cross-file refs, public API, effects
      score.py                   invariants 1-4 + null baselines + co-change + gold + cost -> score.json (a vector)
      headroom.py                pre-flight: can a repo show a positive gain at all? no model call
      test_score.py              fixture tests for the scorer; run before trusting any number
      rescore.py                 re-score existing runs in place after a scorer change
      aggregate.py               per-repo table + --decide (paired bootstrap, validity/stability gates)
      power.py                   sample-size planning (paired design with effect heterogeneity); Phase-2 gate
      build_corpus.py            stratified random sample from the GitHub API, pinned shas, frame recorded
      status.sh                  derives the current phase from repo state; how a fresh session resumes
      checkpoint.sh              commit + push runs/, notes/, results.tsv
      pin_corpus.sh              replace PIN_ME with HEAD shas (mechanical)
      supervise.sh               re-launch fresh sessions until DONE/BLOCKED/WAITING
      pilot.sh / pilot_check.py  10-repo instrument validation + automated go/no-go report
      corpus.txt                 repo  sha  stratum  language   (pinned)
      holdout.txt                repos the agent may not run

## The loop

Every session starts and ends the same way. The repo is the memory, not the agent.

    ./harness/status.sh                 # which phase, what next; exit 2 = a human is needed
    ./harness/checkpoint.sh "..."       # commit + push; uncommitted work dies with the VM

Resume prompt, identical for a cloud session, a routine, or `supervise.sh`:

> Read CLAUDE.md, program.md, and LOOP.md. Run ./harness/status.sh and resume LOOP.md at the
> phase it names. Checkpoint after every phase and iteration. Keep going until status.sh
> reports DONE, BLOCKED, or WAITING.

## One run

    ./harness/run_one.sh psf/requests <sha> 0      # repo, sha, replicate

Outputs land in `runs/<repo>/<sha>/<skill_label>/<rep>/`:

    manifest.json      the LU manifest (or partial + unpartitioned[])
    result.json        claude -p JSON result: cost, turns, duration, session_id
    lint.log           every lint round the hooks ran
    score.json         from score.py (a vector; no composite)
    meta.json          provenance: skill_label, overlay_hash, model, CLI version, condition, session_id

Runs are keyed by the skill's git sha, so a before/after comparison is always explicit. A
`(repo, label, rep)` slot that already has a `score.json` is never rerun.

### Running repos concurrently

Each run gets its own output and checkout directory (`LU_OUT`, `LU_WORK`, defaulting to
per-run paths), so the corpus no longer has to run serially. Validated with two simultaneous
extractions: no cross-contamination, 13 min wall-clock against ~24 serial.

    for i in 0 1 2 3 4 5 6; do ./harness/run_corpus.sh --reps 0,1,2 --shard $i/7 & done; wait

Set `ANTHROPIC_API_KEY` before raising concurrency. The inner runs otherwise inherit
subscription auth, and N workers reach the account cap N times faster — this cost one entire
sweep (18 of 28 slots) during the first run.

## After a scorer change

The runs are still good; only the numbers derived from them are stale. Re-score rather than
re-run:

    python3 harness/rescore.py                 # dry run: shows every field that would move
    python3 harness/rescore.py --apply

Record which scorer sha produced a `results.tsv` row. A label scored by one version is not
paired with a label scored by another, so a scorer change means a re-baseline.

## The lab notebook

    notes/SUMMARY.md            the write-up; its existence makes status.sh report DONE
    notes/rq1.md                baseline failure coding (CODEBOOK codes), hypotheses, harness defects
    notes/rq2.md                the ratchet: one section per iteration, prediction BEFORE the run
    notes/architecture.md       seven structural changes to the research design, with an order
    notes/patch-0*.md           rationale and evidence for each harness change, and why
    notes/CODEBOOK.md           failure-mode codes F1-F11
    notes/BLOCKED.md            if present, the loop is stopped and a human is needed

`notes/rq2.md` distinguishes `## iteration N` (run) from `## QUEUED iteration N` (predicted,
not yet run). `status.sh` counts only the former.

## Growing the corpus

    python3 harness/build_corpus.py --n 30 --seed 7 --strata lowvis,famous --cutoff 2026-01-01
    python3 harness/headroom.py --corpus        # then drop or flag the FLAT ones

Add a stratified fraction of any new repos to `harness/holdout.txt` BEFORE any skill edit.
The holdout is scored once, by a human, after the last kept edit.

## Known limits

- The primary quality metric has almost no headroom on flat single-package repos. See
  `notes/rq1.md` H4 and `notes/architecture.md` change 5.
- Replicates are repetitions, not seeds — Claude Code exposes no RNG seed. Stability is
  reported honestly as run-to-run variance.
- Every outcome is a proxy. `gold/` is empty and the rater study is deferred, so nothing yet
  anchors the proxies to a judgement a maintainer would recognise.
