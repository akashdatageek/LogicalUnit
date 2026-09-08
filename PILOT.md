# PILOT.md — validating the instrument on 10 repos before 100

The pilot answers one question: **if we run this on 100 repos, will the numbers mean
anything?** It does NOT try to improve the skill. Any skill edit during the pilot
contaminates the answer, because you can no longer tell whether a metric moved
because the metric is sensitive or because the skill changed.

Run with the baseline skill only. Six replicates per repo, all 10 repos (holdout
included — there is nothing to protect yet). Then `python3 harness/pilot_check.py`.

## What the pilot must establish, and the pass criteria

### P1. The pipeline is reliable
| Check | Pass | Why |
|---|---|---|
| Harness failures (exit != 0 with no manifest, hook errors) | < 5% of runs | those are bugs, not data |
| Runs ending with a manifest (valid or partial) | > 90% | the stop hook is doing its job |
| `budget_exhausted` rate | < 20% | else `--max-turns` is the thing being measured |
| Lint hook fires on every write (lint_rounds >= 1 when manifest exists) | 100% | |

### P2. The metrics discriminate between repos more than between replicates
This is the single most important check. If replicate noise is as large as the
differences between repos, no edit to the skill can ever be detected.

For each metric, compute the **variance ratio** = between-repo variance / within-repo
(replicate) variance, and the **ICC(1)**.

| Metric | Pass | Marginal | Fail |
|---|---|---|---|
| `q_gain_dir` | ICC >= 0.6 | 0.4–0.6 | < 0.4 |
| `coverage`, `edge_resolution` | ICC >= 0.5 | | |
| `n_units` | ICC >= 0.7 | | |

Fail on `q_gain_dir` means: change the metric or the procedure (more scouts,
stricter reconcile step) before scaling. Do not scale a metric that cannot see repos.

### P3. The metrics agree with a human
Rank the 10 repos' *best* manifests by eye — "how much would a maintainer agree with
this decomposition?" — WITHOUT looking at scores. Then compute Spearman rho between
the human rank and each metric's rank.

| | Pass |
|---|---|
| rho(human, q_gain_dir) | >= 0.5 |
| rho(human, q_cochange_gain) | >= 0.4 |
| rho(q_gain_dir, q_cochange_gain) | 0.3–0.8 (correlated but not redundant) |

If the human disagrees with q_gain_dir, the proxy is wrong for LUs and the 100-repo
run will optimise the wrong thing. This check costs one hour and is not optional.

### P4. The decision rule has an acceptable false-positive rate (A/A test)
Compare the same skill against itself: replicates {0,1,2} as "before", {3,4,5} as
"after". `pilot_check.py` does this for every 3-vs-3 split of the six replicates
(10 splits). The rule should say REVERT on (almost) all of them.

| | Pass |
|---|---|
| A/A KEEP rate at alpha = 0.10 | <= 10% (1 of 10 splits) |
| A/A KEEP rate at alpha = 0.05 | 0 |

If KEEP fires on A/A more often than alpha, the bootstrap is under-estimating
variance (too few repos) — raise the replicate count or the repo count before 100.

### P5. Stability tells us how many replicates 100 repos need
From mean pairwise Jaccard and the within-repo variance of q_gain_dir, compute the
replicates needed to detect a delta of 0.03 in q_gain_dir at 80% power with N=70
dev repos. `pilot_check.py` prints this. If it says > 5, the skill is too
unstable to benchmark; fix the Procedure section (that is a legitimate pre-100 edit,
then re-pilot).

### P6. The validity thresholds are not lying
Phase 0 already produced a case for this check: a requests manifest with 11 of 13 units
owning a single file passed `trivial=False` (the 80% singleton rule) with negative gain.
`singleton_unit_frac` is now reported per run. Decide from the pilot's distribution whether
the trivial rule should be tightened (e.g. singleton_frac >= 0.6) BEFORE tagging `baseline`;
after that it is pre-registered and stays.
Open every run that is `valid_nontrivial=True` and check the 3 with the lowest
`q_gain_dir`. If any of them is obviously bad to a maintainer, the thresholds
(coverage 0.95, edge 0.90, trivial 80%) are too loose. Open the 3 invalid runs with
the highest q_gain_dir; if any is obviously fine, the thresholds are too strict.
Record adjustments in notes/pilot.md with the manifest paths as evidence.

### P7. Static resolver vs `ent ci` (invariants 2 and 4)
The resolver (harness/resolver.py, tree-sitter) supplies ground truth for entrypoints and
effects. It is a static approximation; ent's runtime span evidence is the reference.
For every pilot manifest run `resolver.py score` and `ent ci --lint`, and compare:
| | Pass |
|---|---|
| I2: symbols the resolver calls "missed" that ent also flags | >= 80% |
| I2: symbols the resolver calls "missed" that ent says are fine (resolver false positives) | <= 20% |
| I4: effect kinds detected by both / detected by either | >= 0.7 |
Below these, contract_r is measuring the resolver, not the model: drop it from the
--decide gate until fixed, and say so in notes/pilot.md. Also spot-check 20 "missed"
entries by hand — the resolver's name-based resolution is where errors will hide.

### P8. Cost projection
mean cost × 100 repos × replicates-from-P5 × (1 + fraction of ratchet reruns, assume 4).
If that exceeds budget, decide now: fewer replicates, fewer max-turns, or smaller
dev set — not mid-run.

## Go / no-go

GO to 100 if P1, P2 (q_gain_dir), P3 (human rho), and P4 pass, and P5 gives <= 5
replicates. Otherwise fix the named component, re-pilot only the failed check
(most re-checks need 3 repos, not 10), and record what changed in notes/pilot.md.

## What the pilot does NOT tell you
- Whether the skill is any good (that is the 100-run).
- Anything about contamination (all 10 repos are famous; the low-visibility stratum
  comes with the corpus plan).
- Anything about entrypoint/effect quality (needs ent's resolver).
