# Research architecture — structural changes worth making

Written after running Phase 0 through Phase 2 iteration 1. These are distinct from the
patches in `notes/patch-0*.md`, which fix defects. These change how the experiment is
designed, and each one is a pre-registration decision rather than a bug fix.

Ordered by how much they change what the program can conclude.

---

## 1. The unit of analysis is wrong, and it is costing an order of magnitude of power

Every outcome is currently computed per *run*: one `q_gain_dir`, one `valid_nontrivial`, one
`jaccard` per run, with repositories as the sample for pairing. The baseline sweep therefore
produced 16 usable observations, and `power.py` says 7 dev repos give 80% power only under a
generous assumption about effect heterogeneity.

But each run emits many independently checkable objects. Counted over the same baseline runs:

| level of analysis | observations available |
|---|---|
| run (what is used today) | 16 |
| unit | 207 |
| entrypoint | 2,213 |

The resolver already computes ground truth per unit — which symbols are entered from outside,
which effect kinds are detected — so this information exists and is being collapsed into a
single number per run before anything statistical happens.

**Change.** Score per unit, with repository as a random effect (or a cluster-robust paired
bootstrap over repos, which fits the existing machinery more cheaply). Outcomes become:
is this unit entered from outside at all; is its entrypoint list right; are its effects right;
is it a singleton. An edit's effect is then estimated over hundreds of observations instead
of sixteen.

**Why this matters more than adding repos.** `power.py` correctly says only more repositories
reduce effect heterogeneity, tau. That is true for a *repo-level* effect. But most of the
hypotheses in `rq2.md` are claims about units — "the lead splits until it runs out of files",
"a unit must be entered from outside" — and those are testable at the unit level where n is
already large. Match the analysis to the level the hypothesis is actually about.

---

## 2. The instrument has never been calibrated against a known answer

Right now there is no way to distinguish "the model produced a bad decomposition" from "the
metric cannot see a good one". Figure 1 of the readout is exactly this problem discovered
by accident, after $253.

**Change.** Build three to five *synthetic* repositories with known correct decompositions:
construct them so the module boundaries, the interfaces, and the hub files are known by
construction. Then score the known-correct manifest and a set of deliberately degraded ones
(one unit merged wrongly, one file misassigned, one entrypoint omitted, one giant unit, one
unit per file).

That gives what no amount of real-repo running gives:

- the score a perfect answer receives, per metric
- the metric's sensitivity — how much degradation is needed before the score moves
- the metric's specificity — whether it penalises things that are not actually wrong

`harness/test_score.py` (patch 03) is the unit-test version of this idea. This is the
measurement-theory version, and it should gate any change to the primary outcome.

---

## 3. Ablate the existing skill before adding to it

The ratchet only adds. Twelve iterations of one-change-at-a-time costs roughly $1,000 and
answers twelve binary questions, each conditional on the ones before it, in an order that
determines what gets found.

Meanwhile nobody knows which parts of the current ~120-line skill are load-bearing. The
`noskill` control tests all-or-nothing; there is nothing in between.

**Change.** Run an ablation sweep as its own condition set: full skill, minus the anti-patterns
section, minus the procedure, minus the definition, minus the worked example, and bare prompt.
On the three MEASURABLE repos at three replicates that is 108 runs — comparable to one baseline
sweep — and it answers a question no sequence of additions can: what is already doing the work.

If, say, the anti-pattern list carries most of the effect and the worked example carries none,
that reshapes every subsequent hypothesis and may shorten the ratchet considerably.

---

## 4. Transfer belongs in the KEEP criterion, not in a final phase

Phase 4 tests the final skill on a second model, once, at the end. That ordering means twelve
iterations of optimisation happen against one model's idiosyncrasies, and only afterwards is it
asked whether any of it generalises. If it does not, the whole ratchet was prompt-tuning rather
than a finding about instructions.

**Change.** Make an edit KEEP only if it holds on two models. Cheaper than it sounds if paired
with change 1: with unit-level outcomes, the confirmation run needs fewer runs per model.

This is the difference between "this wording helps sonnet-5" and "this is a better
instruction", and only the second is a thesis result.

---

## 5. One primary outcome cannot fit both repository classes

`headroom.py` (patch 02) sorts repositories into FLAT and MEASURABLE, and the split is 4/3 on
the current corpus. Applying `q_gain_dir` to a FLAT repo is not a weak measurement, it is a
meaningless one: the null is zero and every partition scores negative.

**Change.** Declare the primary outcome per class, in advance.

- MEASURABLE repos: partition quality — `q_gain_dir`, plus gold agreement where gold exists.
- FLAT repos: contract fidelity — entrypoint and effect precision and recall at unit level.
  These repos are still perfectly good evidence about whether the model identifies interfaces
  correctly; they are simply useless for evidence about clustering.

Report the two separately and never pool them. This also answers the "what is the point of
decomposition" question honestly: on a 19-file library the value was never the clustering.

---

## 6. Cost and latency belong in the decision record

`--decide` weighs quality gates only. An edit that improves gain by 0.01 while doubling tokens
is a bad trade for a tool people run in CI, and nothing in the current rule notices.

**Change.** Report cost and wall-clock deltas alongside every verdict, and pre-register a
tolerance — for instance, an edit that raises median cost per run by more than 25% must clear a
higher quality bar. Both numbers are already in `result.json`.

---

## 7. Smaller structural notes

- **The scorer decides what "source" means.** `SKIP` is hardcoded, so the harness's opinion
  about which directories count determines coverage, which is a validity gate. After patch 01
  the manifest can declare its own scope; the scorer should then verify that declaration is
  reasonable rather than impose its own.
- **Hypothesis provenance is not recorded against a baseline.** Iteration 1 was tested against
  `cac873e`. Patch 01 changes the scorer, so that result is no longer comparable to anything
  measured afterwards. Each queued hypothesis should record the baseline label it was predicted
  against, and be re-predicted if the instrument changes underneath it.
- **The holdout is three repos.** Correct discipline, but too small to confirm much. If the
  corpus grows, grow the holdout with it and keep the stratification.
- **There is no human anchor anywhere.** Every outcome is a proxy. The gold directory is empty
  and the rater study is deferred. Until at least a handful of decompositions have been judged
  by a person, there is no evidence that any proxy points at something a maintainer would call
  a good decomposition.

---

## Suggested order

1. Patches 01 and 03, then re-score and re-baseline (defects first, they change the data).
2. Calibration repos (change 2) — cheap, and it gates everything about the metric.
3. Unit-level analysis (change 1) — the largest gain in what the experiment can detect.
4. Per-class primary outcome (change 5) — follows directly from `headroom.py`.
5. Ablation sweep (change 3) — before spending the ratchet budget on additions.
6. Transfer in KEEP (change 4) and cost in the record (change 6).
