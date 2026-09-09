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
