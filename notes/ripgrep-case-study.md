# Case study — BurntSushi/ripgrep, all conditions, two models

Complete. 9 runs under label base `d096702` (post-fix harness), compared against the 4 runs at
`cac873e` (pre-fix). Total ~$110.

Repo chosen by pre-flight rather than preference: `headroom.py` rates ripgrep MEASURABLE
(q_dir 0.123, ceiling 0.258, headroom 0.135) while cobra and requests are FLAT, where no
decomposition can score positive. ripgrep is also the only repo in the project that ever
produced a positive gain. Pinned at `3fce3b5`, 89 in-scope source files, Rust.

## Results

Same harness, same commit, model isolated:

| arm | valid | gain | units | jaccard | min/run | $/run |
|---|---|---|---|---|---|---|
| sonnet-5, skill | 3/3 | **+0.0240** | 12, 12, 17 | 0.705 | 8.7–10.0 | 6.3–7.4 |
| sonnet-5, no skill | 1/1 | **+0.0508** | 11 | — | 9.4 | 1.82 |
| opus-5, skill | 2/3 | **−0.0185** | 20, 19 | 0.561 | 32–44 | 19–24 |
| opus-5, no skill | 1/1 | **+0.0189** | 17 | — | 13.8 | 4.43 |
| opus-5, hide-docs | 1/1 | −0.0097 | 18 | — | 25.1 | 17.68 |

Sonnet under the *old* harness (`cac873e`) scored +0.0238. The new harness gives +0.0240. **The
patch-01 change did not move this repo's gain**, which retires the confound I flagged before the
sonnet arm ran and makes the two-model comparison clean.

Opus replicate 1 was lost to the account usage limit mid-run after $15.59. The driver's probe
protects runs not yet started; it cannot protect one already in flight.

## The finding: on this repo the metric measures granularity, not quality

Across all 12 valid ripgrep runs — both models, all conditions, both harness versions:

    correlation(n_units, q_gain_dir) = −0.823

    units   q_llm     gain      arms
    11–12   +0.147…+0.174   +0.024…+0.051   sonnet skill, sonnet noskill, cac873e
    17      +0.142…+0.147   +0.019…+0.024   sonnet skill rep1, opus noskill
    18–20   +0.097…+0.113   −0.026…−0.010   opus skill, opus nodocs

`q_dir` is constant at 0.1231 — it is a property of the repository, not the run. So gain is
almost entirely determined by how finely the model divides ripgrep. Fewer, larger units win.

**The mechanism is subdivision, not boundary-crossing.** I initially assumed the skill was
being punished for cutting across crates, as SKILL.md tells it to ("directories are a hint, not
a boundary"). That is wrong, and checking it is what produced the real answer: 91–100% of units
in *every* arm stay inside a single top-level directory. Nothing crosses crates. What differs
is depth. The bare prompt names units after ripgrep's crates —

    sonnet noskill (11 units):  core, cli, globset, grep, ignore, index, matcher, pcre2

— while the skill subdivides inside them, splitting the `ignore` crate into three:

    opus skill (19 units):  gitignore-rules, file-type-filter, directory-walker, …

`q_dir` partitions by *immediate parent directory*, which is finer than a crate. Grouping
directories up to crate level beats it (+0.05). Matching it scores ~0. Cutting below it destroys
within-crate edges and goes negative. The skill's anti-pattern section pushes away from coarse
partitions ("fewer than 3 units for a repo over 2k LOC means you have not found the seams") and
says nothing about a floor, so it systematically lands on the losing side of that curve.

## RQ3 — the skill hurts both models here

| model | skill | no skill | skill effect |
|---|---|---|---|
| sonnet-5 | +0.0240 | +0.0508 | **−0.0268** |
| opus-5 | −0.0185 | +0.0189 | **−0.0374** |

The best score in the entire project is the **bare prompt on Sonnet**: +0.0508, 11 units, 9.4
minutes, **$1.82** — cheapest and best.

This reverses the Phase 1 reading, and both are true. On requests the bare prompt emitted one
unit per file (19 units, 19 files, trivial) and the skill's value was preventing that collapse.
On ripgrep, which has real structure, the bare prompt just follows the crates and wins, while
the skill talks the model into finer units. The skill helps where structure is absent and hurts
where it is obvious. Neither Phase 1 nor this case study alone would have shown that.

## RQ5 — transfer fails

Model isolated, same harness: sonnet **+0.0240**, opus **−0.0185**, delta **−0.0425**. The
skill's benefit does not survive a change of model. It is worse than not transferring: the same
instruction that is roughly neutral on Sonnet is actively harmful on Opus, because Opus
subdivides more readily.

Under program.md's framing this is the RQ5 answer for this repo: what was tuned is not a better
instruction but a fit to one model's granularity preference.

## RQ4 — no recall effect

Hiding every README, doc and .rst moved the score by less than a hundredth: −0.0097 without docs
against −0.0185 with them, i.e. marginally *better* hidden. Unit names stayed semantic and the
structure held. On a repo this famous, recall was the confound most worth ruling out. No `F11`.

## Stability

Sonnet 0.705, Opus 0.561, both below the 0.6 threshold that governs Phase 2 (Opus at it,
Sonnet above). Sonnet's old-harness run was 0.839; the drop comes from rep1 producing 17 units
where the others produced 12 — one replicate choosing a different depth, again granularity.

## Directory exclusions are still enumerated by hand

    sonnet noskill   31 entries, 11 directory-shaped
    opus skill rep0  30 entries,  4 directory-shaped
    opus skill rep2  24 entries,  0 — every path listed individually
    opus nodocs      25 entries,  0

The lint hook now accepts directory exclusions (patch 01), but SKILL.md only says "list them
under `excluded` with a reason" and never says a directory is acceptable, so the model keeps
enumerating. The bare prompt, with no skill text at all, used directories more readily than the
skill did. This is exactly what **QUEUED iteration 2** in `notes/rq2.md` predicts against.

## Cost

Opus 32–44 min at $19–24 per run; Sonnet 8.7–10 min at $6.3–7.4; Sonnet with no skill 9.4 min
at $1.82. Opus is roughly 3× the wall-clock and 3–4× the cost for a worse score on this metric.

## What this case study changes

1. **`q_gain_dir` is not a quality measure on a structured repo.** It is a granularity measure
   with r = −0.82 against unit count. Any ratchet optimising it here is selecting for coarser
   output, not better decomposition. This is the strongest evidence yet for `notes/architecture.md`
   change 1 (score per unit) and change 5 (declare the primary outcome per repo class).
2. **RQ5 has an answer and it is negative** — for one repo, so treat it as a strong signal
   rather than a settled result.
3. **The skill's value is conditional on the repo having no obvious structure.** That should be
   stated in program.md as a scope condition before any further ratchet work.
4. The queued iteration-2 hypothesis (directory-level exclusions) is confirmed as still live
   under the new harness.
