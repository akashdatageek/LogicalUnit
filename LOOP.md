# LOOP.md — the research run (v1)

Read CLAUDE.md (rules), program.md (pre-registered outcomes and decision rule), and
notes/CODEBOOK.md (failure codes). This file is the procedure. Follow it in order.
No questions — nobody answers. Every phase ends by writing to notes/.

## Resuming (do this first, every session)
You may be a fresh session with no memory of earlier ones. The repo is the memory.
    ./harness/status.sh
It prints the phase you are in and the next command. Start there, not at Phase 0.
After finishing any phase, and after every ratchet iteration, run
    ./harness/checkpoint.sh "<what you did>"
so runs/ and notes/ are committed and pushed. Uncommitted work is lost when the VM ends.
If status.sh exits 2 (BLOCKED or WAITING), stop; a human is needed.

Budget: the ratchet runs at most LU_MAX_ITER iterations (default 12). Per session,
check `date` at phase boundaries and checkpoint before you run low on turns.

Vocabulary: a *replicate* is a repeated run (there is no seed). A *label* is the harness
git sha at run time; runs live in runs/<repo>/<sha>/<label>/<rep>/.

## Phase 0 — Sanity (≤ 30 min)
1. corpus.txt fully pinned? If any PIN_ME → `./harness/pin_corpus.sh && git commit -am "pin corpus"`.
   (Pinning is mechanical, not a sampling decision, so it is yours to do. Adding or
   removing repos is not.) If pinning fails for a repo → notes/BLOCKED.md.
2. `./harness/run_one.sh psf/requests <sha> 0 --max-turns 40`
3. Confirm manifest parses, lint.log has ≥1 round, result.json has total_cost_usd,
   meta.json has skill_label and model, score.json has graph_source = "tree-sitter"
   (if it says regex-fallback, tree-sitter is not installed in the container → BLOCKED). Read the manifest as a maintainer would;
   5 lines in notes/phase0.md.
4. Harness failure (hooks/harness/schema) → notes/BLOCKED.md, stop. Skill failure →
   fix, commit `[procedure] …`, rerun once.

## Phase 1 — Baseline sweep (RQ1, ~2h). Do NOT edit SKILL.md.
1. `git tag baseline`; BASE=$(git rev-parse --short HEAD)
2. `./harness/run_corpus.sh --reps 0,1,2`               (dev only; holdout auto-skipped)
3. `./harness/run_corpus.sh --reps 0 --condition noskill`  (RQ3 control, 1 rep)
4. `python3 harness/aggregate.py --label $BASE`  and  `--tsv >> results.tsv`
5. Read every dev manifest. For each (repo, rep) record rows in notes/rq1.md using
   CODEBOOK codes only: repo | rep | code | evidence | severity.
6. notes/rq1.md summary table: repo | lang | LOC | stratum | valid | gain | cochange |
   jaccard | dominant code. Then 3–6 hypotheses "repos with P fail with code Fx because Q",
   each backed by ≥2 repos, ranked by repos explained.
7. Compute noskill vs skill on the same repos. If the skill is not beating noskill on
   valid_nontrivial, the FIRST Phase 2 hypothesis must be about that.

## Phase 2 — Ratchet (RQ2; remaining time − 1h45)
SAMPLE-SIZE GATE FIRST:
    NEED=$(python3 harness/power.py --from-runs --label $BASE --delta 0.02 --min-n)
    HAVE=$(python3 harness/aggregate.py --n-dev)
If HAVE < NEED: write notes/NEED_CORPUS.md with both numbers and the command the human
should run (`python3 harness/build_corpus.py --n <NEED-HAVE+5> --seed <n> --strata lowvis,famous`),
then skip to Phase 3. Do not ratchet on a dev set that cannot detect the pre-registered MDE.

STABILITY FIRST: if mean jaccard at baseline < 0.6, edits target the Procedure section
until it is ≥ 0.6. Score gains on an unstable skill are noise.

Per iteration:
1. Take the top untested hypothesis. Design ONE edit. Classify it. Write the edit AND a
   falsifiable prediction ("q_gain_dir up on flask, fastapi; valid unchanged") to
   notes/rq2.md BEFORE running, under a heading `## iteration <n>` (status.sh counts these).
2. `git commit -am "[category] …"`;  NEW=$(git rev-parse --short HEAD)
3. Targeted signal: `./harness/run_corpus.sh --reps 0,1,2 --only <predicted repos>`
   Then `python3 harness/aggregate.py --decide $PREV $NEW` restricted by what exists.
   If the targeted repos did not move in the predicted direction, `git revert --no-edit HEAD`,
   log "prediction failed", next hypothesis. Do not run the full corpus.
4. Full dev: `./harness/run_corpus.sh --reps 0,1,2`
5. DECIDE: `python3 harness/aggregate.py --decide $PREV $NEW`. The printed verdict is final.
   - REVERT → `git revert --no-edit HEAD`; log the delta and CI anyway (null results count).
   - KEEP → REPLICATE: `./harness/run_corpus.sh --reps 3,4,5`; `--decide $PREV $NEW` again.
     Flips → revert, log "did not replicate". Holds → PREV=$NEW, `--tsv >> results.tsv`.
6. Natural-partition check: if >70% of the gain comes from ripgrep + MAVSDK, revert.
7. `./harness/checkpoint.sh "iteration <n>: <KEEP|REVERT>"`. Back to 1.

Hard rules: one edit per iteration; no repo/library/path names in SKILL.md; never weaken
invariants, anti-patterns, or the stop rule; never touch holdout; never move or delete a
run directory; never rerun a (repo, label, rep) that already has a score.json.

## Phase 3 — Recall control (RQ4, ~30 min)
`./harness/run_corpus.sh --reps 0 --hide-docs --only ripgrep,MAVSDK,flask,nest`
Compare gain with docs vs without. Code any collapse as F11 in notes/rq4.md.

## Phase 4 — Transfer (RQ5, ~30 min, only if a KEEP survived)
With LU_MODEL set to the second model (CLAUDE.md says which):
`git checkout baseline -- overlay/` → run 4 dev repos, 1 rep → `git checkout HEAD -- overlay/`
→ same 4 repos, 1 rep → aggregate --decide. Record whether the gain transfers.

## Phase 5 — (human only) Holdout
Not yours. Write "holdout not run" in the summary.

## Phase 6 — Write-up (mandatory; status.sh sends you here when the budget is spent). notes/SUMMARY.md, ≤ 700 words:
1. Baseline table (--label baseline) and final table (--label HEAD); `git log --oneline baseline..HEAD`.
2. RQ1: top 3 predictors of failure with codes and evidence.
3. RQ2: per category — attempted / kept / replicated / reverted, with CIs.
4. RQ3: skill vs noskill.  RQ4: docs vs hide-docs.  RQ5: transfer or "not run".
5. Threats: what in the metric or corpus you distrust most, and why.
6. Total cost from summing runs/**/result.json.
Then `./harness/checkpoint.sh "summary"` and stop.
