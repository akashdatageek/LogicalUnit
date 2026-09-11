# program.md — research goals (pre-registered; do not edit during the run)

You are improving ONE file: overlay/.claude/skills/lu-decompose/SKILL.md
(and, sparingly, overlay/examples/*). Everything else is fixed. A hook enforces this.

## Pre-registered outcomes

PRIMARY (the ratchet decides on these, lexicographically):
  1. valid_nontrivial rate — fraction of runs whose manifest satisfies coverage >= 0.95,
     edge_resolution >= 0.90, is not trivial (>=2 units, < 80% of files as singleton
     units), and did not exhaust the turn budget.  This is a GATE: an edit that lowers it
     is rejected regardless of anything else.
  2. q_gain_dir — import-graph modularity of the model's partition minus the best
     zero-intelligence baseline (one-unit, one-unit-per-directory). Positive means the
     model found structure a directory listing does not give you.

SECONDARY (reported, never optimised directly):
  - q_cochange_gain: the same gain on the git co-change graph (orthogonal proxy)
  - gold_ari / gold_nmi: agreement with a human gold decomposition where one exists
  - stability: mean pairwise Jaccard across replicates (a GATE: may not fall by > 0.15)
  - entrypoint / effects precision-recall (invariants 2 and 4), from harness/resolver.py
    (tree-sitter static analysis); contract_r = mean recall. GATE in --decide: may not drop > 0.05.
    Precision is only interpretable once pilot P7 confirms the resolver against ent ci.
  - cost_usd, turns, tokens, lint_rounds, unpartitioned

Louvain / label-propagation modularity is a CEILING for the proxy, not a baseline.
There is no composite score. Trade-offs are reported, not hidden.

## Minimum detectable effect and the sample-size gate

MDE (pre-registered): delta = 0.02 in q_gain_dir. Edits with a smaller true effect are
below what this experiment can see and are expected to come back REVERT; that is not a
harness failure. Required dev-set size for 80% power at 3 replicates comes from
    python3 harness/power.py --from-runs --label <pilot label> --delta 0.02 --min-n
(tau defaults to delta until a before/after pair exists to estimate it.) With the pilot's
sd_within around 0.02 and tau around 0.03 that is ~14 dev repos; at delta = 0.01 it is ~50.
Phase 2 does not start until `aggregate.py --n-dev` >= that number. Below it, the loop
stops and asks for more corpus (harness/build_corpus.py), which is a human action.

## Decision rule (deterministic; the agent may not override it)

    python3 harness/aggregate.py --decide <label_before> <label_after>

KEEP only if: validity gate holds, stability gate holds, contract-recall gate holds, and the 90% paired-bootstrap CI
of per-repo delta q_gain_dir excludes zero. Then REPLICATE with 3 fresh replicates
(reps 3,4,5) on the after-label; if --decide flips, revert and log "did not replicate".

TRANSFER (pre-registration amendment 2026-09-10; notes/architecture.md change 4). An edit is KEEP
only if it ALSO holds on a second model. Confirm with
    python3 harness/aggregate.py --decide-transfer <before> <after> --models <m1>,<m2>
which requires the paired-bootstrap CI to exclude zero on EVERY model (model is a run-label suffix,
e.g. sonnet5, opus5; the token `base` means the bare label). This moves the RQ5 transfer test out of
a final phase and into the KEEP gate, so the ratchet cannot tune one model's idiosyncrasies for
twelve iterations before anyone checks whether the edit generalises. Set LU_MODEL_SECONDARY below.

UNIT-LEVEL VIEW (secondary, advisory; does NOT override the run-level rule above). Each run emits
many independently-checkable units, so score.py persists per-unit ground truth and
    python3 harness/units.py --decide <before> <after>
reports the edit at unit granularity (entrypoint recall, effects recall, entered-from-outside,
singleton fraction) with a cluster-robust paired bootstrap over repos (the repo is the independent
cluster). Most RQ2 hypotheses are claims about units, and that is where the sample is large. It
informs a decision; it never makes one.

COST IN THE DECISION RECORD (notes/architecture.md change 6). `aggregate.py --decide` now reports
cost/run before->after and the % change alongside every verdict, and `aggregate.py --budget` gives a
per-repo token/cost rollup and a runs/week capacity figure. This is REPORTED, not gated: making an
edit's cost increase flip a KEEP is a pre-registration change to this decision rule and is not in
effect. Record the cost delta with each kept version.

INSTRUMENT CALIBRATION (gate on any future change to the primary outcome). Before altering how the
primary metric is computed, `python3 harness/calibrate.py` must pass: it scores a known-correct
synthetic decomposition and a set of degraded ones and asserts the score moves the right way
(sensitivity) and does not move for a pure contract error (specificity). A metric change that
breaks calibration is rejected regardless of its effect on real repos.

## Research questions

RQ1 (exploratory) Under the baseline skill, which repo properties predict failure?
    Coded with the failure-mode codebook (notes/CODEBOOK.md). Output: ranked hypotheses.
RQ2 (confirmatory on dev, then holdout) Which categories of skill edit move the primary
    outcomes? Categories: [definition] [procedure] [example] [antipattern] [stopping].
RQ3 (control) How much of the gain is the skill? Compare condition=skill vs noskill.
RQ4 (control) How much is recall vs. derivation? Compare default vs --hide-docs, and
    famous-repo stratum vs low-visibility stratum (see CORPUS_PLAN.md).
RQ5 (transfer) Does the final skill's gain survive on a second model?

## Constraints
- One change per experiment. Never batch.
- Never weaken the invariants, the schema, the anti-patterns, or the stop rule.
- Never add repo-, library-, or path-specific hints. The skill must be repo-agnostic.
- Never run the holdout. Never look at holdout results.
- Runs are keyed by skill git sha. Never delete or move a run directory.
- If an edit's gain comes >70% from the natural-partition repos (ripgrep, MAVSDK), revert.
