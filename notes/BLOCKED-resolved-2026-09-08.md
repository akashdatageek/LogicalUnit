# BLOCKED — Phase 0 sanity failed (2026-09-08 21:10 UTC)

LOOP.md Phase 0 stops the run on either of the two conditions below. Both hold.
Nothing under study (SKILL.md) was touched. No extraction run was started, so
`runs/` is empty and `results.tsv` has only its header.

## Blocker 1 — corpus.txt is not pinned (Phase 0, step 1)

All 10 rows of `harness/corpus.txt` still read `PIN_ME`. The agent may not edit shas
(FILES.md: "human adds rows; never edits shas"; the guard hook blocks the file anyway).

Human fix (from PROMPTS.md §0), run from the repo root:

    for r in $(grep -v '^#' harness/corpus.txt | awk '{print $1}'); do
      sha=$(git ls-remote https://github.com/$r HEAD | cut -f1)
      sed -i "s|^$r .*PIN_ME|$r $sha|" harness/corpus.txt
    done
    grep -c PIN_ME harness/corpus.txt   # must print 0

GitHub is reachable from this container (`git ls-remote https://github.com/psf/requests HEAD`
returned a sha), so the loop itself will work once the rows are pinned. Pin all rows in
one sitting so the frame is dated consistently; commit the result.

## Blocker 2 — tree-sitter is not installed (Phase 0, step 3)

    python3 -c "import tree_sitter"                 -> ModuleNotFoundError
    python3 -c "import tree_sitter_language_pack"   -> ModuleNotFoundError
    python3 -c "import networkx"                    -> ModuleNotFoundError

`harness/resolver.py` imports `tree_sitter_language_pack` unconditionally, so score.py
would fall to `graph_source = "regex-fallback"`, which LOOP.md defines as BLOCKED.
networkx is also missing, so the Louvain ceiling cannot be computed. `pip` is on the
agent's deny list, so this is a container-image change:

    pip install tree-sitter tree-sitter-language-pack networkx

Then re-verify: `python3 -c "import tree_sitter, tree_sitter_language_pack, networkx"`.

## Checked and OK (no action needed)

- `claude` CLI 2.1.265 is on PATH and a one-turn `claude -p` completed (auth works;
  default model resolved to claude-sonnet-5). `LU_MODEL` is unset, so runs use the
  CLI default. Set `LU_MODEL` to pin a model id for a multi-day experiment.
- `jq` and python 3.11 present. `/work` and `/out` are writable.
- `ent` is not on PATH; `lint_manifest.sh` falls back to `lint_stub.py` as designed.
  Pilot check P7 (resolver vs `ent ci`) therefore cannot be done in this container.

## Not blocking Phase 0, but needed later

- `LU_MODEL_SECONDARY` is unset. Phase 4 (RQ5 transfer) needs it; CLAUDE.md asks the
  human to fill it in.
- PILOT.md and PROMPTS.md §1–2 say a hand-run extraction and the 10-repo pilot must
  precede the unattended loop. There is no `notes/pilot-report.txt` or
  `notes/human_rank.txt`, so the pilot has not been run either.

## To resume

After fixing both blockers and committing corpus.txt, re-run `./harness/kickoff.sh`
(or the same one-line prompt). The loop restarts at Phase 0 and will hand-run
`psf/requests` first.

## Resolution (2026-09-08, later session)
Both blockers were resolved by the human-supplied lu-bench v1.1 update: pin_corpus.sh makes
pinning an agent-owned mechanical step, and the SessionStart hook installed tree-sitter,
tree-sitter-language-pack and networkx. Archived here; status.sh no longer sees it.
