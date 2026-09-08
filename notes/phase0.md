# Phase 0 — sanity (psf/requests@dae7ef6, rep 0, label f82b175, 2026-09-08 22:14–22:27 UTC)

Attempt 1 (label 6d58dca) died on an account usage limit; see notes/phase0-log.md. Attempt 2:

- Harness plumbing OK: manifest parses (13 units, 19/19 src files owned, coverage 1.00);
  lint.log has 2 rounds (30 I4 errors -> 0); result.json total_cost_usd=3.73, 57 turns,
  13 unit-scout subagents, 808 s; meta.json has skill_label=f82b175 and model=default
  (LU_MODEL unset; CLI resolved to claude-sonnet-5); score.json graph_source=tree-sitter.
  Workspace-trust warning on stderr only drops overlay permissions.allow; --allowedTools
  from run_one.sh still applies, hooks and the skill load. No fix needed.
- Manifest as a maintainer would read it: sensible names and layperson descriptions
  (session, transport-adapter, cookie-jar, compat-layer...), edges all resolve
  (edge_resolution 1.00, entrypoint recall 0.94), one honest violation recorded
  (auth.py reaching into Response internals). But it is essentially one-unit-per-file:
  11 of 13 units own a single file; q_llm=-0.078 vs one-unit/dir baseline 0.0 (all source
  is one flat directory, so the dir baseline degenerates to the one-unit baseline);
  Louvain ceiling 0.093. Code F4 over-split, severity 2. Effects over-declared
  (effects_p 0.19): the lint stub's I4 regex `\brequests\b` matches the package's own name
  in every file, so the model declared `network` on status_codes, hooks, structures etc.
  to pass lint. Same for every skill version, so not a confound for the ratchet, but it
  costs a lint round per run and makes effects_p uninterpretable on this repo.
- HARNESS DEFECT (blocking): score.json says budget_exhausted=true, valid_nontrivial=false,
  although result.json has subtype=success, terminal_reason=completed, stop_reason=end_turn.
  score.py derives budget_exhausted from num_turns >= max_turns; num_turns (57) counts
  subagent turns and legitimately exceeds --max-turns (40). See notes/BLOCKED.md.

## Post-fix (v1.2 harness, 2026-09-08 23:00 UTC)
Human shipped score.py fix (budget_exhausted from result subtype). Regenerated the resolver
cache runs/requests/<sha>/graph.json with the v1.2 resolver and re-scored the f82b175 run in
place (re-score, not rerun): valid_nontrivial=true, budget_exhausted=false, run_error=false,
singleton_unit_frac=0.769, q_gain_dir=-0.078 unchanged, contract_r=0.968. Phase 0 passes.
Open pre-registration question (PILOT.md P6): the trivial rule accepts 77% singleton units;
the pilot has not been run by a human, so the rule stays as is and singleton_unit_frac is
reported. LU_MODEL was unset; Phase 1 onward passes LU_MODEL=claude-sonnet-5 explicitly
(the id the CLI default resolved to in Phase 0) so meta.json records it.
