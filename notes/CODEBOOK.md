# Failure-mode codebook — use these codes, not free text, in rq1.md

F1  unassigned      in-scope files left out of every unit (coverage < 0.95)
F2  dir-copy        units ≈ top-level directories; q_gain_dir ≈ 0
F3  over-merge      < 3 units on a repo > 2k LOC; seams collapsed
F4  over-split      units of 1–2 files with no distinct entrypoints
F5  ep-underlist    depends_on targets a symbol the target unit did not list (I3 fail, target's fault)
F6  internal-reach  depends_on targets a real internal that is not a contract (I3 fail, source's fault)
F7  effect-miss     I/O present in unit files but not declared (I4)
F8  budget          hit --max-turns before a valid manifest
F9  context         run degraded on large repo: partial manifest, scouts truncated, or contradictory ownership
F10 unstable        unit NAMES agree across replicates but FILE ownership does not (Jaccard < 0.6)
F11 recall          units/names match the repo's own docs verbatim (suspect recall, test with --hide-docs)

Each observation: repo | rep | code | one-line evidence (file or unit name) | severity 1–3
