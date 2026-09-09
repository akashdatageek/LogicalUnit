# Research review of lu-bench v0 — gaps and fixes

Reviewed as an empirical-SE experiment, not as engineering. Each gap lists
severity, why it matters for the thesis, and what changed in v1.

## A. Construct validity — is the metric measuring "good Logical Units"?

**A1. The headline metric was rigged against the LLM.** `modularity_gain = Q_llm − max(Q_one, Q_dir, Q_louvain)`.
Louvain is a Q-optimizer on the very graph Q is computed on. Including it as a baseline
guarantees the LLM is compared to the near-optimum of the proxy, so gain is ~always negative
regardless of decomposition quality. *Severity: critical.*
→ v1: Louvain is reported as a **reference ceiling**, not a baseline. Gain is vs. the
strongest *zero-intelligence* baseline (one-unit, directory).

**A2. Import-graph modularity is one proxy, and a weak one for LUs.** Import locality ≠ logical
cohesion; a well-layered app has low Q by design. *Severity: high.*
→ v1 adds two orthogonal signals: (i) **co-change modularity** from git history
(evolutionary coupling; files that change together belong together — Zimmermann et al.);
(ii) **agreement with a gold decomposition** (ARI + NMI) where one exists. Gold is the real
ground truth; the graphs are proxies. The SE community's standard for comparing
decompositions is MoJoFM (Tzerpos & Holt) and the architecture-recovery benchmarks
(ACDC, Bunch, ARCADE; Garcia et al.'s ground-truth architectures). Use those datasets and
that metric for the thesis chapter; ARI/NMI here are the cheap in-loop stand-ins.

**A3. Contracts weren't scored.** The thing that makes an LU more than a cluster — enumerated
entrypoints, effects — had no precision/recall. *Severity: high.*
→ v1.1 RESOLVED: `harness/resolver.py` (tree-sitter, six languages) extracts exported symbols,
cross-file references, the repo's public surface (re-exports from `__init__`/`index`/`lib.rs`,
Go/Java visibility, C headers), and effects (import + confirming call). Ground truth for I2 per
unit = symbols entered from outside the unit ∪ public surface; I4 = detected effect kinds.
Validated on psf/requests: it correctly flagged 5 of 8 public API functions missing from a
hand manifest and did not flag `urllib.parse` as network. `contract_r` is a gate in --decide.
Known limits: name-based cross-file resolution; effect tables are curated; pilot P7 checks it
against ent ci before precision is trusted.

**A4. Arbitrary weighted composite as the objective.** 0.35/0.25/0.30 were guesses, and a
composite hides trade-offs (coverage up, structure down looks like "flat"). *Severity: high.*
→ v1: **pre-registered primary outcome** + secondary outcomes, no composite in the decision.
Primary: `valid_nontrivial` rate (gate) and `q_gain_dir` on the import graph (quality),
compared lexicographically. Everything else is a dashboard.

## B. Internal validity — can we trust a "keep"?

**B1. Keep-if-mean-goes-up on 10 repos × 3 reps is a noise ratchet.** Sequential testing on
the same data with no threshold = garden of forking paths; the agent will "find" gains.
*Severity: critical.*
→ v1: the **harness decides**, not the agent. `aggregate.py --decide <before> <after>` runs a
paired bootstrap on per-repo deltas and prints KEEP only if the 90% CI excludes zero and
the validity gate did not drop. LOOP.md forbids the agent from overriding it. This is
"LLM proposes, deterministic code disposes" applied to the experimenter.

**B1b. Sample size was asserted, not computed.** "30–50 repos" was a guess. → v1.1 RESOLVED:
`harness/power.py` models the paired design with effect heterogeneity (tau) — the term
replicates cannot reduce — and reports min N_dev for the pre-registered MDE. LOOP.md gates
Phase 2 on `aggregate.py --n-dev >= power.py --min-n`. `build_corpus.py` makes reaching N
one command, with the sampling frame recorded for citation. At MDE 0.02 the gate is ~14
repos; at 0.01 it is ~50. The 10-repo set is a pilot by construction, not by apology.

**B2. No holdout at 10.** → v1: 7 dev / 3 holdout from day one (holdout: gson, express,
dronekit — chosen so each language family has one). The agent never runs the holdout;
`run_corpus.sh` refuses `--only` names on the holdout list unless `LU_HOLDOUT_OK=1`.

**B3. Replication before keep.** A kept edit must survive a fresh set of replicates.
→ v1: after KEEP, rerun the dev set with 3 *new* replicates (indices 3–5); if the decision
flips, revert and log "did not replicate".

**B4. "Seeds" aren't seeds.** Claude Code exposes no RNG seed; runs are just repetitions.
→ v1: renamed to **replicates** everywhere. Stability is reported honestly as run-to-run.

**B5. Model and tool drift mid-experiment.** → v1: `run_one.sh` pins `--model` and records
`claude --version`, model id, skill git sha, and overlay hash in `meta.json`. If any of
these change between two rows in `results.tsv`, the rows are not comparable.

**B6. The optimizer and the optimized are the same model family.** Skill edits may encode
"what this model likes" rather than "what makes a good instruction". → v1: Phase 5
**transfer check**: final skill vs. baseline skill on a second model. If the gain
disappears, report it as model-specific.

## C. External validity — what can the result generalise to?

**C1. Training-data contamination.** All 10 repos are famous. The model may *recall* their
architecture rather than derive it, which is exactly the thing the thesis must not confuse.
*Severity: critical for the thesis, moderate for the harness shakedown.*
→ v1: (i) `--hide-docs` condition strips README/docs/ARCHITECTURE/comments so structure
must come from code; (ii) corpus plan for 100 adds a **low-visibility stratum** (<200 stars,
created after model cutoff) and a **post-cutoff stratum**; (iii) the natural-partition
guard is kept. Report gains per stratum, never pooled.

**C2. Sampling frame was ad hoc.** → v1: `CORPUS_PLAN.md` defines strata × language × size,
an inclusion rule, and *random* sampling within strata from a defined frame (e.g. SEART GHS
or GitHub search with fixed filters). Cherry-picked repos are a threat reviewers will name.

**C3. Capacity vs. instruction confound.** Large repos may fail from context limits, not
skill quality. → v1: `meta.json` records input/output tokens and `num_turns`; runs that hit
`--max-turns` are flagged `budget_exhausted` and excluded from quality metrics (reported
separately as a failure mode).

## D. Measurement hygiene

**D1. Free-text failure notes aren't comparable.** → v1: a fixed **failure-mode codebook**
(F1–F9) in `notes/CODEBOOK.md`; every observation in rq1.md carries a code.

**D2. No "no-skill" baseline.** Without it you can't attribute anything to SKILL.md.
→ v1: `--condition noskill` runs the bare prompt + schema only. Report skill vs. noskill.

**D3. Descriptions for laypeople are a human study, not a metric.** Left out of the loop
deliberately; planned as a separate rater study (≥3 raters, agreement reported).

**D4. Log everything.** `meta.json` now stores session_id and transcript path so any
manifest can be traced to the reasoning that produced it.

## E. What to write in the thesis' threats-to-validity section (already true of v1)
- Proxy metrics (import/co-change Q) are not ground truth; gold subset is small.
- Contamination cannot be fully excluded for famous repos; see per-stratum results.
- One model family did most of the optimisation; transfer tested on one other model only.
- Replicates are not seeded; run-to-run variance is the model's, not controllable.
- Effects P/R depends on the static detector's own recall.

## F. Found by the first live Phase 0 run (2026-09)

**F1. `budget_exhausted` was computed from `num_turns >= max_turns`, but `num_turns` in the
headless result counts subagent turns.** Every run that used scouts was marked exhausted and
failed the validity gate. *Severity: critical — it would have zeroed the primary outcome.*
→ Fixed: derived from the result's `subtype` / `terminal_reason` (`error_max_turns`,
`error_max_budget_usd`). `run_error` and `result_subtype` are recorded so the failure mode is
visible. Credit: the outer agent diagnosed this from the result fields and wrote the patch
into notes/BLOCKED.md rather than editing a fixed file — the guard worked as intended.

**F2. A repo's own package name matched the effect tables** (`requests` inside psf/requests).
→ Fixed at the resolver: an import that resolves to an in-repo file is never an effect. The
regex fallback in the lint stub no longer matches bare library names.

**F3. The over-split failure mode is real and the trivial rule missed it** (11/13 singleton
units, negative gain, `trivial=False`). → `singleton_unit_frac` reported; PILOT.md P6 asks for
the threshold decision before `baseline` is tagged. Not changed unilaterally: it is a
pre-registration decision.

**F4. Plan usage limits kill long runs.** The inner `claude -p` calls inherited the session's
subscription auth and hit the usage cap mid-run. → PROMPTS.md: set `ANTHROPIC_API_KEY` in the
environment so inner runs bill to the API; `--shard i/n` added to spread the sweep across VMs.
