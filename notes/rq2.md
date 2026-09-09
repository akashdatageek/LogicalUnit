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

---

# Queued hypotheses — pre-registered, NOT applied

The Phase 1 analysis produced more hypotheses than the one iteration tested. They are written
here as predictions so a later session can run them one at a time. **None of these is applied
to SKILL.md.** Applying five untested edits at once is precisely the anti-pattern the ratchet
exists to prevent, and an unmeasured "improvement" is not an improvement.

Order matters. Iterations 2 and 3 are Procedure edits, which the stability-first rule
(baseline jaccard 0.452 < 0.6) requires before anything aimed at quality. Run patches 01-04
first: patch 01 changes the failure landscape these predictions describe, so re-baseline
before testing them.

## QUEUED iteration 2 — [procedure] delegate enumeration off the lead

**Hypothesis (rq1 H1).** F8 exhaustion is driven by the lead doing per-file work in the main
loop, not by repo size. Step 1 tells the lead to list the tree and classify every file itself
before any scout runs. Evidence: flask (24 files) exhausted twice, ripgrep (84) never; every
exhausted run enumerated heavily; fastapi rep 0 drew 50 I1 lines and then died.

**Edit.** Step 1 states that the lead classifies *directories*, not files, and that any tree it
can name as out of scope is excluded as a single entry. Individual file paths appear only where
a directory is genuinely mixed.

**Prediction.** valid_nontrivial rises on flask, fastapi and nest. Output tokens per run fall
by more than 20% on repos with large non-source trees. q_gain_dir does not move on cobra,
requests or ripgrep. Targeted repos: flask, fastapi, nest.

**Caveat.** Patch 01 removes the lint pressure that causes this behaviour, so part of the
effect may already be gone. If patch 01 lands first, this iteration tests only the residual;
re-read the post-patch baseline before predicting a magnitude.

## QUEUED iteration 3 — [procedure] batch the scout calls

**Hypothesis.** The skill says Step 2 is parallel, but every baseline run requested its
subagents in the foreground and none in the background: 14 scouts on average, up to 31 on nest.
If they are issued one per turn, ordering dominates both wall-clock and the main-loop turn
budget.

**Edit.** Step 2 says to issue every scout call for the candidate list in a single message, and
to cap the candidate list before scouting rather than after.

**Prediction.** Wall-clock per run falls materially on repos with many candidates (nest,
MAVSDK, flask). valid_nontrivial rises on nest. Cost per run is roughly unchanged, because the
same scouts still run. Targeted repos: nest, MAVSDK, flask.

## QUEUED iteration 4 — [definition] a stopping rule stated as a test

**Hypothesis (rq1 H2).** The skill forbids one-unit-per-file but gives no positive criterion
for when a split is justified, so the lead splits until it runs out of files. Singleton
fraction reached 0.75 on requests and 0.72 on flask.

**Edit.** A unit must have at least one entrypoint that is entered from outside itself. The
static resolver already computes exactly this, so the rule is checkable rather than advisory.

**Prediction.** singleton_unit_frac falls on requests and flask. jaccard rises on requests
(0.23 at baseline). valid_nontrivial does not fall anywhere.

**Note.** Iteration 1 tested a *different* merge rule — "keep two units apart only if each has
an entrypoint the other calls" — and it failed: requests lost gain and validity while flask
gained both. This version differs by testing each unit against the outside world rather than
against its neighbour, which does not force leaf utilities into their single caller. That
distinction is the reason to run it rather than treat iteration 1 as having settled the
question.

## QUEUED iteration 5 — [definition] allow a declared shared kernel

**Hypothesis (rq1 B3).** Exclusive file ownership forces cross-cutting code into one unit. In a
modularity metric a misplaced hub is maximally expensive, which is a plausible mechanical cause
of the negative scores on flat repos.

**Evidence available before running.** `harness/headroom.py` (patch 02) reports the share of
import-edge endpoints landing on the top 5% most-connected files: fastapi 50%, nest 38%,
MAVSDK 30%, flask 11%. The prediction should be strongest where that number is highest.

**Edit.** A unit may be declared `kind: kernel`, owning files that other units legitimately
import without that counting as an internal-reach violation.

**Prediction.** q_gain_dir rises on the repos with the highest hub share. Requires a scorer
change to treat kernel-owned files correctly, so it is blocked until that exists — and a
scoring change of this kind is a pre-registration decision, not a bug fix.

**Do not run this before the metric question in rq1 H4 is settled.** If gold agreement becomes
the primary outcome, this hypothesis needs rewriting against that measure instead.
