# RQ1 — baseline failure analysis (label cac873e, tag `baseline`, 2026-09-09)

Model claude-sonnet-5 (pinned via LU_MODEL), Claude Code 2.1.265, max_turns 60,
21 skill runs (7 dev repos x 3 replicates) + 7 noskill runs. Holdout untouched.
Corpus primaries from `aggregate.py --label cac873e`:

    repos=7 runs=21  VALID 0.57  GAIN(dir) -0.0315  jaccard 0.45  mean cost $7.25
    per stratum: famous valid 0.58 gain -0.034 (n=4) | natpart valid 0.50 gain -0.011 (n=2) | uav valid 0.67 gain -0.063 (n=1)

## Summary table

| repo | lang | src files (score.py) | stratum | valid | gain | cochange | jaccard | dominant code |
|------|------|------|---------|-------|------|----------|---------|---------------|
| requests | python | 19 | famous | 1.00 | -0.045 | -0.054 | 0.23 | F4 over-split, F10 unstable |
| cobra | go | 19 | famous | 1.00 | -0.038 | -0.182 | 0.88 | (clean) |
| flask | python | 24 | famous | 0.33 | -0.038 | -0.037 | 0.33 | F8 budget, F4 over-split |
| fastapi | python | 534 (48 real) | famous | 0.00 | -0.014 | -0.161 | 0.33 | F8 budget, M1 artifact |
| nest | typescript | 1546 | natpart | 0.00 | -0.046 | -0.108 | 0.33 | F8 budget, F1 unassigned |
| ripgrep | rust | 84 | natpart | 1.00 | +0.024 | +0.040 | 0.84 | (clean, only positive gain) |
| MAVSDK | cpp | 873-984 | uav | 0.67 | -0.063 | -0.056 | 0.22 | F8 budget, F10 unstable |

## Per-run coding (CODEBOOK codes; severity 1-3)

| repo/rep | code | evidence | sev |
|---|---|---|---|
| requests/0,1,2 | F4 | 11/14/12 units over 19 files; singleton_unit_frac 0.36/0.71/0.75 | 2 |
| requests/0-2 | F10 | unit count varies 11-14 across replicates; jaccard 0.23 | 3 |
| cobra/0,1,2 | — | 6-7 units, coverage 1.0, jaccard 0.88; cleanest repo in the set | — |
| flask/1,2 | F8 | main loop hit 60 turns (subtype error_max_turns); rep2 produced no units | 3 |
| flask/0 | F4 | 18 units over 24 files, singleton_unit_frac 0.72 | 2 |
| fastapi/0 | F8 + M1 | exhausted at 60 turns; scored coverage 0.09, prefix-aware coverage 1.00 | 3 |
| fastapi/1,2 | F8 | exhausted, zero units written | 3 |
| nest/1 | F1 | 31 units but coverage 0.40; integration/ and sample/ left unassigned | 2 |
| nest/2 | F8 | exhausted, zero units | 3 |
| nest/0 | (dead) | infrastructure loss: usage limit, 1 turn, no model output. Excluded from analysis. | — |
| MAVSDK/0,1 | — | 16 units both reps, coverage 1.0, only 19% of units confined to one directory | — |
| MAVSDK/2 | F8 | exhausted, 1 unit, coverage 0.15 | 3 |
| ripgrep/0,1,2 | — | 11-12 units, coverage 1.0, jaccard 0.84, the only positive gain | — |

F8 is the single largest failure mode: 8 of 21 runs (38%). Every one stopped at
num_turns 61 against a cap of 60.

## Hypotheses, ranked by repos explained

**H1 (4 repos: flask, fastapi, nest, MAVSDK) — F8 is driven by lead-loop work, not repo size.**
Turn exhaustion does not track file count. ripgrep (84 files) and MAVSDK (873) never
exhausted on reps 0-1, while flask (24 files) exhausted twice. What the exhausted runs share
is main-loop enumeration: flask/0 listed 56 excluded files one by one, fastapi enumerated
directories then re-derived them, and every exhausted run wrote its excluded/unpartitioned
lists from the lead rather than delegating. The skill's Procedure tells the lead to "list the
tree" and classify every file itself before any scout runs. Prediction: an edit that makes
Step 1 delegate enumeration, or cap the lead's per-file work, raises valid_nontrivial on
flask/fastapi/nest without changing cobra/requests/ripgrep.

**H2 (3 repos: requests, flask, and the noskill control) — the skill under-defines when to
stop splitting, producing F4.** singleton_unit_frac is 0.36-0.75 on requests and 0.72 on
flask, and the noskill condition on requests produced exactly one unit per file (19/19,
caught by the trivial rule). The skill's anti-pattern section forbids "one unit per file"
but gives no positive stopping criterion, so the lead splits until it runs out of files.
Prediction: a stopping rule stated as a test (a unit must have at least one entrypoint
entered from outside, and merging two units must lose a real distinction) lowers
singleton_unit_frac and raises jaccard on requests and flask.

**H3 (3 repos: requests, MAVSDK, flask) — instability comes from Step 1, not Step 3.**
jaccard is 0.23 (requests), 0.22 (MAVSDK), 0.33 (flask) while the unit *names* stay
recognisable across replicates; what moves is file ownership and the candidate count
(requests: 11, 14, 12). The candidate list in Step 1 is generated free-form with no
tie-breaking rule, and Step 3 reconciles whatever it is given. Prediction: a deterministic
seam-selection rule in Step 1 raises jaccard on requests and MAVSDK; expect no gain change.

**H4 (2 repos: ripgrep, MAVSDK) — the metric only has headroom where directories already
disagree with logic.** q_gain_dir = q_llm - max(q_one, q_dir), and q_one is 0 by construction.
On flat single-package repos (requests, cobra, flask, and fastapi's real 48-file package)
q_dir is also ~0, so gain equals q_llm, and any partition that cuts a dense cohesive import
graph scores negative. Only ripgrep (multi-crate, q_dir 0.123) produced a positive gain
(+0.024, ceiling 0.258). This is a property of the metric, not of the decompositions, and it
caps what Phase 2 can demonstrate on 4 of 7 dev repos. Treat as a threat, not a hypothesis to
edit against; do not chase it with skill changes.

## RQ3 — skill vs noskill

Comparable scoreable pairs (rep 0, same repos): skill valid 4/4, noskill valid 3/4.
Over all skill replicates on those repos: 11/12 (0.92) vs noskill 3/4 (0.75). The skill is
beating the bare prompt on validity, so the first Phase 2 hypothesis is not required to be
about noskill (LOOP.md Phase 1 step 7).

The difference is concentrated in one behaviour: on requests the bare prompt emitted one unit
per file (19 units, 19 files, trivial=true, gain -0.074) where the skill produced 11-14 units.
On repos with obvious module boundaries the two conditions are indistinguishable
(cobra 6 vs 7 units; ripgrep 12 vs 12, noskill gain +0.042 slightly better than skill +0.024;
MAVSDK 10 vs 16). Reading: the skill's contribution at baseline is preventing degenerate
decomposition, not finding better seams. flask and fastapi noskill runs were lost
(usage limit; output-token limit), so n=4, and this reading is provisional.

## Phase 2 entry conditions

- Mean jaccard at baseline is 0.45 (harness figure, all runs) and 0.62 counting only valid
  runs in the 4 repos with two or more. Both readings sit at or below the LOOP.md threshold,
  and the harness figure is the pre-registered one, so **STABILITY FIRST applies**: edits
  target the Procedure section until jaccard reaches 0.6. H3 then H1 are the entry points;
  H2 is the natural follow-up since a stopping rule should also stabilise ownership.

## Measurement problems found (harness is fixed; these are for the human)

**M1 — coverage does not honour directory-prefix exclusions.** score.py computes
`excluded = {e['path']}` and removes only exact path matches from the denominator. A manifest
that excludes `docs_src` (a directory, which is what the schema's `excluded` invites) leaves
all 462 files under it in scope. fastapi/0 decomposed all 48 real package files and was scored
at coverage 0.09; prefix-aware coverage is 1.00. It changed no validity verdict in this
baseline, because every affected run also exhausted its budget, but it will suppress a genuine
future improvement: fastapi can never reach valid_nontrivial through better decomposition
alone. It also creates a perverse incentive for the ratchet to reward verbose per-file
exclusion lists over better structure. Suggested fix: treat an excluded entry as a prefix when
it names a directory.

**M2 — score.py's SKIP list misses common non-source trees.** It skips tests/test/docs/examples
but not `docs_src` (fastapi, 462 files), `integration` or `sample` (nest, 910 of 1546 files).
This inflates the coverage denominator and makes nest close to unscoreable.

**M3 — score.py crashes on a malformed manifest.** The fastapi noskill run emitted an
`excluded` entry `{"__DOCS_SRC_PLACEHOLDER__": true}` with no `path` key; score.py raised
KeyError and run_one.sh's redirect left a zero-byte score.json. Scoring possibly-malformed
model output is score.py's core job, so it should tolerate this. Consequence today:
`aggregate.py --label cac873e-noskill` cannot run, because load() parses every score.json it
globs. The primary table is unaffected (the label filter skips it before parsing).

**M4 — run_corpus.sh loses the corpus list to the inner CLI.** It pipes corpus.txt into a
`while read` loop and the inner `claude -p` inherits and drains that stdin, so the sweep stops
after the first repo. Both Phase 1 sweeps were driven by scratchpad scripts calling run_one.sh
with `< /dev/null`; arguments are otherwise identical. Fix: redirect stdin on the run_one.sh
call inside the loop.

## Cost and losses

21 skill + 7 noskill run slots filled. Three slots lost to infrastructure, not to the model:
nest/0 and flask noskill (account usage limit mid-run) and fastapi noskill (response exceeded
the 64000 output-token maximum). An earlier sweep under abandoned label dfb7d01 lost 18 of 28
slots to the same usage limit; see notes/phase0-log.md. Setting ANTHROPIC_API_KEY in the
environment would remove this failure class. Spend across both sweeps is roughly $190.
