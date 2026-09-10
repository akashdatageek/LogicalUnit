# FILES.md — every file, who reads it, whether it may change

"Mutable during the experiment" is enforced by `.claude/hooks/guard_edit.sh`, which blocks
the outer agent's edit tools everywhere except `SKILL.md`, `overlay/examples/*.json`,
`notes/*.md` and `results.tsv`. The guard exists to stop the instrument changing underneath a
measurement, so during a run a harness defect is written up in `notes/patch-*.md` with its
evidence and left for the owner. Between runs the owner can direct otherwise; the patch notes
record which changes were applied that way and in which commit.

| Path | Read by | Purpose | Mutable during the experiment? |
|---|---|---|---|
| **Research design (human-owned)** | | | |
| `program.md` | outer agent | pre-registered outcomes, MDE, decision rule, RQ1–RQ5, constraints | no |
| `LOOP.md` | outer agent | the procedure: Phase 0 sanity → 1 baseline → 2 ratchet (gated) → 3 recall → 4 transfer → 6 write-up | no |
| `PILOT.md` | human | what the 10-repo pilot must establish; pass criteria P1–P8 | no |
| `CORPUS_PLAN.md` | human | sampling frame, strata, gold subset, dev/holdout split | no |
| `REVIEW.md` | human | methodology review: gaps in v0 and what v1/v1.1 changed | no |
| `PROMPTS.md` | human | the exact prompts and the order to run things | no |
| `notes/CODEBOOK.md` | outer agent | failure-mode codes F1–F11 for RQ1 | no |
| **Harness context and guard** | | | |
| `CLAUDE.md` | outer agent (auto-loaded) | rules, commands, what it may edit, no-questions | no |
| `requirements.txt` | human, SessionStart hook | pinned Python deps (tree-sitter, language-pack, networkx) + the non-pip prerequisites | no |
| `README.md` | human | install, the free pre-flight checks, layout, how to run one or many | no |
| `.claude/settings.json` | Claude Code | outer-agent permissions; PreToolUse guard hook | no |
| `.claude/hooks/guard_edit.sh` | Claude Code | blocks writes outside SKILL.md, examples/, notes/, results.tsv | no |
| **Harness tools (agent calls, never edits)** | | | |
| `harness/run_one.sh` | agent, human | one extraction: pin, strip CLAUDE.md, overlay, `claude -p`, collect, score; runs keyed by skill sha | no |
| `harness/run_corpus.sh` | agent, human | all repos × replicates; resumable; refuses holdout | no |
| `harness/resolver.py` | score.py, lint hook | tree-sitter: exported symbols, cross-file refs, public surface, effects | no |
| `harness/score.py` | run_one.sh | invariants 1–4, null baselines, Louvain ceiling, co-change, gold ARI/NMI, cost → vector | no |
| `harness/headroom.py` | agent, human | pre-flight: q_dir, ceiling, headroom, hub share per repo; no model call. Run before choosing a corpus | no |
| `harness/test_score.py` | agent, human, SessionStart | 8 fixtures for the scorer; run before trusting any number. Must be 8/8 | no |
| `harness/rescore.py` | agent, human | re-score existing runs in place after a scorer change; diffs every field; dry run by default | no |
| `harness/aggregate.py` | agent, human | per-repo/stratum table; `--decide` (gates + paired bootstrap); `--n-dev`; `--tsv` | no |
| `harness/power.py` | agent (Phase-2 gate), human | min dev-set size for the pre-registered MDE, with effect heterogeneity | no |
| `harness/build_corpus.py` | human | stratified random sample from GitHub, pinned, frame recorded | no |
| `harness/pilot.sh` | human | 10-repo pilot runner: baseline skill, 6 replicates, writes notes/pilot-report.txt | no |
| `harness/pilot_check.py` | human | automated go/no-go against PILOT.md criteria P1–P8 | no |
| `harness/status.sh` | agent, supervisor, human | derives current phase + next command from repo state; exit 2 = human needed | no |
| `harness/checkpoint.sh` | agent, supervisor | commit + push runs/ notes/ results.tsv | no |
| `harness/pin_corpus.sh` | agent, human | replace PIN_ME with HEAD shas (mechanical) | no |
| `harness/supervise.sh` | human (local/self-hosted) | re-launch fresh sessions until DONE/BLOCKED/WAITING | no |
| `harness/kickoff.sh` | human | one-shot launch (use supervise.sh or a cloud session instead) | no |
| `.claude/hooks/session_setup.sh` | Claude Code (SessionStart) | installs resolver deps if missing; runs outside the agent's pip deny | no |
| `harness/corpus.txt` | run_corpus.sh | `repo sha stratum language`, pinned | human adds rows; agent may pin PIN_ME via pin_corpus.sh |
| `harness/holdout.txt` | aggregate, run_corpus | repos the agent may not run | human only, before any edit |
| `harness/corpus.meta.json` | thesis | citable sampling frame (written by build_corpus.py) | no |
| **Overlay — copied into every target repo checkout** | | | |
| `overlay/.claude/skills/lu-decompose/SKILL.md` | inner agent | LU definition, invariants, procedure, anti-patterns, stop rule | **YES — the only thing under study** |
| `overlay/examples/minimal-http-lib.manifest.json` | inner agent | one worked example the skill references | yes, sparingly |
| `overlay/.claude/agents/unit-scout.md` | inner agent | read-only per-unit scout subagent | no |
| `overlay/.claude/settings.json` | Claude Code | inner permissions + 3 hooks | no |
| `overlay/.claude/hooks/guard_write.sh` | Claude Code | only `$LU_OUT/manifest.json` may be written (`LU_OUT` defaults to `/out`, set per run) | no |
| `overlay/.claude/hooks/lint_manifest.sh` | Claude Code | runs `ent ci --lint` or the stub after every manifest write; violations fed back | no |
| `overlay/.claude/hooks/lint_stub.py` | lint hook | I1/I3 structural, I2/I4 via resolver (regex fallback); honours directory-prefix exclusions | no |
| `overlay/.claude/hooks/require_manifest.sh` | Claude Code | Stop hook: no manifest, no stopping | no |
| `overlay/lu-manifest.schema.json` | inner agent, lint | output contract; `version` is ent's, never the model's | no |
| **Outputs** | | | |
| `runs/<repo>/<sha>/<label>/<rep>/` | aggregate | manifest, result, meta (provenance), lint.log, score.json; `graph.json` cached at `<sha>/` | append-only; `score.json` may be rewritten by `rescore.py` |
| `results.tsv` | human, agent | one row per kept skill version | agent appends |
| `notes/` | human | lab notebook: phase0, rq1, rq2, rq4, SUMMARY, architecture, patch-0*, BLOCKED/NEED_CORPUS | agent writes |
| `gold/<repo>.json` | score.py | human gold decompositions (optional) | human only |
