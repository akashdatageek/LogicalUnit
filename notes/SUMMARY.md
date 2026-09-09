# SUMMARY — lu-bench run, 2026-09-08/09

Stopped by operator request after Phase 2 iteration 1's two-repo signal run. Phases 3
(recall control), 4 (transfer) and 5 (holdout) were not run. **Holdout not run.**

Model under test: claude-sonnet-5 (pinned via LU_MODEL). Claude Code 2.1.265, max_turns 60.

## 1. Baseline and final

Baseline = final. The one skill edit attempted was reverted, so `overlay/.../SKILL.md` is
byte-identical to its state at the `baseline` tag.

    label cac873e (tag `baseline`), 7 dev repos x 3 replicates
    VALID 0.571   GAIN(dir) -0.0315   jaccard 0.452   mean cost $7.25/run

    repo       valid   gain   cochg   cov  edge  units   jac  exh
    requests    1.00  -0.045  -0.054  1.00  1.00   12.3  0.23   0
    cobra       1.00  -0.038  -0.182  1.00  1.00    6.7  0.88   0
    flask       0.33  -0.038  -0.037  0.67  1.00   12.0  0.33   2
    fastapi     0.00  -0.014  -0.161  0.03  1.00    5.0  0.33   3
    nest        0.00  -0.046  -0.108  0.13  1.00   10.3  0.33   1
    ripgrep     1.00  +0.024  +0.040  1.00  1.00   11.7  0.84   0
    MAVSDK      0.67  -0.063  -0.056  0.72  1.00   11.0  0.22   1

    git log --oneline baseline..HEAD
    2fe230c [notes] iteration 1 result: reverted, prediction failed
    15a0cb4 Revert "[procedure] Step 3: merge test"
    17e40da [procedure] Step 3: merge test — a split must be earned by a crossed interface
    0525a76 [notes] rq2 iteration 1 hypothesis and prediction
    c7300a7 checkpoint: phase 1 complete
    (plus checkpoints)

## 2. RQ1 — what predicts failure

1. **Turn exhaustion (F8), 8 of 21 runs.** Does not track repo size: flask (24 source
   files) exhausted twice, ripgrep (84) never. What the dying runs share is the lead
   enumerating files itself before delegating — flask listed 56 excluded files one by one.
2. **Over-split (F4).** singleton_unit_frac 0.36-0.75 on requests, 0.72 on flask. The skill
   forbids one-unit-per-file but states no positive stopping criterion.
3. **Instability (F10).** jaccard 0.23 requests, 0.22 MAVSDK. Unit *names* stay recognisable
   across replicates; file ownership and candidate count do not (requests: 11, 14, 12).

## 3. RQ2 — the ratchet

Sample-size gate passed: 7 dev repos needed for 80% power at the pre-registered MDE 0.02
(sd_within 0.0165 from runs), 7 available. STABILITY FIRST was in force (jaccard 0.452 < 0.6).

Category [procedure]: **1 attempted, 0 kept, 0 replicated, 1 reverted.** No other category
was attempted. No CI is reportable: `--decide` refused the comparison ("only 2 repos in
common; need >=3") because the full dev set was not run.

Iteration 1 added a merge test to Step 3. The mechanism worked — unit counts and singleton
fractions fell on both targeted repos — but the outcomes split: flask went from 1/3 to 3/3
valid, requests went from 3/3 to 2/3 with gain falling -0.045 to -0.061. Reverted per the
deterministic rule and the failed direction check. The split is recorded in notes/rq2.md as
the most useful lead for a future iteration: fewer units rescues budget-starved repos and
costs quality on repos that were already finishing.

## 4. RQ3 — skill vs noskill

Skill 11/12 valid on comparable repos vs noskill 3/4. The whole difference is one behaviour:
on requests the bare prompt emitted exactly one unit per file (19 units, 19 files,
trivial=true) where the skill produced 11-14. Where module boundaries are obvious the two are
indistinguishable (cobra 6 vs 7 units; ripgrep 12 vs 12, noskill gain +0.042 slightly better
than skill +0.024). At baseline the skill's contribution is preventing degenerate output, not
finding better seams. n=4; two noskill runs were lost to infrastructure.

## 5. RQ4, RQ5 — not run.

## 6. Threats — what I distrust most

**The primary quality metric has almost no headroom on most of this corpus.** q_gain_dir is
q_llm minus max(q_one, q_dir), and q_one is 0 by construction. On flat single-package repos
(requests, cobra, flask, and fastapi's real 48-file package) q_dir is also ~0, so gain equals
q_llm, and any partition that cuts a dense cohesive import graph scores negative. Only
ripgrep, which is genuinely multi-crate, produced a positive gain. Four of seven dev repos
can essentially never show improvement on the pre-registered primary. This is the single
biggest threat to the whole design: the ratchet is being asked to optimise a quantity that is
bounded above by roughly zero on most of its sample.

Second: **coverage does not honour directory-prefix exclusions** (score.py matches exact
paths only). fastapi decomposed all 48 real package files and scored coverage 0.09. It changed
no verdict here but will suppress genuine future improvement, and it rewards verbose per-file
exclusion lists over better structure. Details and three further harness defects (SKIP list
misses docs_src/integration/sample; score.py crashes on a malformed manifest;
run_corpus.sh loses its corpus list to the inner CLI's stdin) are in notes/rq1.md.

Third: replicates are not seeded, so all stability figures are run-to-run variance of the
model, not a controlled quantity.

## 7. Cost

$253.32 across 47 billed runs. Roughly $60 of that was lost to an abandoned first Phase 1
sweep (label dfb7d01), where an account usage limit killed 18 of 28 slots; that label is
excluded from all analysis. Setting ANTHROPIC_API_KEY in the environment would remove this
failure class. Mean wall-clock 15 min/run, driven almost entirely by output volume
(correlation between output tokens and duration 0.996, ~7,200 output tokens/min).
