# lu-bench — Logical Unit extraction benchmark

Point Claude Code at a repo, get back an LU manifest, score it deterministically.
Then let an agent iterate on the skill overnight.

## Layout

    CLAUDE.md                   harness rules the outer agent sees every session
    program.md                  PRE-REGISTERED outcomes, decision rule, RQ1–RQ5
    REVIEW.md                   research-methodology review: what was wrong in v0 and what changed
    CORPUS_PLAN.md              sampling frame, strata, gold subset, dev/holdout split
    PILOT.md                    what the 10-repo pilot must establish before scaling; pass criteria
    LOOP.md                     the procedure: Phase 0 sanity -> 1 baseline -> 2 ratchet -> 3 confounds -> 4 write-up
    .claude/settings.json       outer-agent permissions + guard_edit hook (may only edit SKILL.md/examples/notes)
    results.tsv                 one row per skill version (appended by aggregate.py --tsv)
    notes/                      the agent's lab notebook; CODEBOOK.md = failure-mode codes
    gold/<repo>.json            human gold decompositions (optional; enables gold_ari/nmi)
    overlay/                    copied INTO each repo checkout before a run
      .claude/skills/lu-decompose/SKILL.md   the decomposition instruction (the thing RQ2 edits)
      .claude/agents/unit-scout.md           read-only subagent, one per candidate unit
      .claude/settings.json                  hooks + permissions
      .claude/hooks/*.sh                     guard writes, lint manifest, refuse to stop without one
      lu-manifest.schema.json                output contract
      examples/                              one worked example the skill references
    harness/
      run_one.sh                 clone at pinned hash, apply overlay, run `claude -p`, collect outputs
      run_corpus.sh              all repos x seeds, resumable
      resolver.py                tree-sitter static analysis: exported symbols, cross-file refs, public API, effects
      score.py                   invariants 1–4 + null baselines + co-change + gold + cost -> score.json (a vector)
      power.py                   sample-size planning (paired design with effect heterogeneity); Phase-2 gate
      build_corpus.py            stratified random sample from the GitHub API, pinned shas, frame recorded
      aggregate.py               per-repo table + --decide (paired bootstrap, validity/stability gates)
      holdout.txt                repos the agent may not run
      pilot.sh / pilot_check.py  10-repo instrument validation + automated go/no-go report
      kickoff.sh                 starts the overnight loop
      corpus.txt                 repo  sha  (pinned)

## Pilot first (validate the instrument, then scale)

    ./harness/pilot.sh                 # baseline skill, 10 repos x 6 reps, then go/no-go report
    # rank the 10 repos by eye into notes/human_rank.txt (best first), then:
    python3 harness/pilot_check.py     # adds the human-agreement check

See PILOT.md for pass criteria. Do not edit SKILL.md during the pilot.

## Growing the corpus (when power.py says the dev set is too small)

    python3 harness/build_corpus.py --n 30 --seed 7 --strata lowvis,famous --cutoff 2026-01-01
    # appends to harness/corpus.txt with pinned shas; writes harness/corpus.meta.json (the citable frame)
    # then add a stratified fraction of the new repos to harness/holdout.txt BEFORE any skill edit

## Start the loop

    ./harness/kickoff.sh        # runs LOOP.md end to end, ~8h, writes notes/SUMMARY.md

## One run

    ./harness/run_one.sh psf/requests <sha> 0      # repo, sha, replicate

Outputs land in  runs/<repo>/<sha>/<skill_label>/<rep>/  as:
    manifest.json      the LU manifest (or partial + unpartitioned[])
    result.json        claude -p JSON result: cost, turns, duration, session_id
    lint.log           every ent ci --lint round the hooks ran
    score.json         from score.py (a vector; no composite)
    meta.json          provenance: skill_label, overlay_hash, model, claude_code version, condition, session_id

## Before the first run

1. Decide whether `ent ci --lint <manifest>` exists as a CLI entry. The hooks call it.
   If not yet, point `.claude/hooks/lint_manifest.sh` at a stub that validates against
   lu-manifest.schema.json and checks invariants 1–4 (5 is computed, not judged).
2. Strip or record each repo's own CLAUDE.md — it is a confound (see program.md).
3. Install code-intelligence plugins for py/ts/go/rust/java in the container image.
   Also: `pip install tree-sitter tree-sitter-language-pack networkx` — the resolver (invariants 2/4)
   and the Louvain ceiling need them. score.json reports graph_source so you can tell.
4. Set CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 so the only subagent is unit-scout.
