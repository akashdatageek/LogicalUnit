# RQ2 — the ratchet

Decisions are made by `aggregate.py --decide`, never here. Each iteration records its
hypothesis and a falsifiable prediction BEFORE the edit is run.

Phase 2 entry state (label cac873e = `baseline`):
VALID 0.571, GAIN(dir) -0.0315, jaccard 0.452, n_dev 7, power gate 7 needed / 7 have (passes).
STABILITY FIRST is in force: baseline jaccard 0.452 < 0.6, so edits target the Procedure
section until stability reaches 0.6 (LOOP.md Phase 2).

## iteration 1

**Hypothesis (rq1 H2 + H3).** The skill forbids one-unit-per-file in its anti-patterns but
never says when to *stop* splitting, so the lead splits until it runs out of files. This shows
up as singleton_unit_frac 0.36-0.75 on requests and 0.72 on flask, and it is the mechanical
cause of negative modularity on flat repos: cutting a dense cohesive import graph into
single-file units puts densely connected files in different units, which drives q_llm below
the one-unit baseline. It should also drive instability, because with no stopping criterion
the candidate count is free to vary run to run (requests produced 11, 14 and 12 units).

**Edit.** Procedure Step 3 (Reconcile) gains one positive, testable merge criterion: a pair of
units must be merged unless each side has an entrypoint that the other's files actually call or
that the outside world enters directly. Splitting is justified by a crossed interface, never by
a file boundary or a topic. Category: [procedure]. Nothing is weakened: the anti-patterns, the
invariants, the schema and the stop rule are untouched, and the rule names no repo, library or
path.

**Prediction (falsifiable).**
- q_gain_dir rises on requests and flask (the two valid, most over-split repos). These are the
  targeted repos for the signal run.
- singleton_unit_frac falls on requests and flask; unit counts fall toward the middle of the
  observed range.
- jaccard rises on requests (0.23 at baseline).
- valid_nontrivial does not fall anywhere. cobra and ripgrep, which are already coarse
  (singleton_unit_frac 0.33-0.57 and 0.0-0.08), should not move materially.
- If requests and flask do not move up in gain, the prediction has failed: revert and go to
  H1 (F8 budget: move Step 1 enumeration off the lead).

**Risk noted in advance.** program.md keeps a natural-partition guard: if the gain comes >70%
from ripgrep and MAVSDK, revert. This edit predicts movement on requests and flask, which are
not natural-partition repos, so the guard should not bind.

### iteration 1 — RESULT: REVERTED (prediction failed)

Signal run: requests and flask, 3 replicates each, label 17e40da. Full dev set NOT run
(the operator asked to stop the loop after these two repos), so no KEEP was available to
earn and results.tsv gets no new row.

| repo | gain (baseline -> edit) | delta | valid (baseline -> edit) | units | singleton_frac |
|---|---|---|---|---|---|
| requests | -0.0452 -> -0.0606 | **-0.0154** | 1.00 -> 0.67 | 12.3 -> 10.0 | 0.61 -> 0.59 |
| flask | -0.0383 -> -0.0329 | +0.0054 | 0.33 -> **1.00** | 18,18,0 -> 13,16,15 | 0.72 -> 0.66 |

Harness verdict, recorded verbatim:

    $ python3 harness/aggregate.py --decide cac873e 17e40da
    REVERT  (only 2 repos in common; need >=3)

Reverted in 15a0cb4. Two independent grounds: the deterministic rule refuses a two-repo
comparison, and requests moved *opposite* to the prediction on both the primary quality
metric and validity.

**What the edit actually did.** The mechanism fired exactly as designed — the merge test
reduced unit counts on both repos (requests 12.3 -> 10.0, flask 18 -> 14.7) and lowered
singleton_unit_frac on both. So the instruction was followed. It simply did not buy what
was predicted.

**The split result is the interesting part, and it is not noise.** On flask the edit
converted a repo that failed two of three replicates on turn exhaustion into one that passed
all three, with gain improving slightly. On requests it made both outcomes worse. The two
repos are close in size (24 vs 19 source files) and both are flat single-package Python, so
size and language do not separate them. The plausible reading, for a future iteration to
test properly: fewer units means fewer scouts and less lead-loop work, which rescues repos
that were dying on budget (flask, rq1 H1) but costs quality on repos that were already
completing comfortably, because the merges it forces there destroy real seams. If so, the
right edit is conditional on budget pressure rather than unconditional, and H1 (move Step 1
enumeration off the lead) is the cleaner way to get the same benefit without the cost.

**Null result recorded.** Category [procedure]: 1 attempted, 0 kept, 1 reverted.
Stability was not measurably improved: requests jaccard could not be recomputed against
baseline from a two-repo run, and the mandate that opened this iteration (baseline jaccard
0.452 < 0.6) still stands for whoever resumes.
