# PROMPTS.md — exactly what to type, and when

There are three Claude Code sessions in this design. Each gets a one-line prompt; the
substance lives in files the prompt points at, so every run is reproducible and every
instruction change is a git commit.

## 0. Prerequisites (human, once)

    # container image needs: claude (Claude Code CLI), git, jq, python3 >= 3.10
    pip install -r requirements.txt   # or rely on the SessionStart hook, which reads the same file
    # code-intelligence plugins for python/typescript/go/rust/java/cpp in Claude Code
    cd lu-bench && git init && git add -A && git commit -m "lu-bench v1.1"
    ./harness/pin_corpus.sh && git commit -am "pin corpus"   # or leave it: Phase 0 does this itself now
    export ANTHROPIC_API_KEY=...        # or however the container authenticates
    export LU_MODEL=<model id to pin>   # optional but recommended for a multi-day experiment

## 1. Hand-run one extraction (human, 5 minutes) — do this before anything unattended

    ./harness/run_one.sh psf/requests <sha> 0 --max-turns 40
    cat runs/requests/<sha>/*/0/score.json | jq '{valid_nontrivial,q_gain_dir,entrypoint_r,effects_r,graph_source}'

`graph_source` must say `tree-sitter`. Read the manifest. If it's nonsense, fix the harness,
not the skill.

## 2. PILOT — validate the instrument (human starts it; ~10 repos x 6 replicates)

    ./harness/pilot.sh

This runs the baseline skill only, then prints `notes/pilot-report.txt`. When it finishes:
rank the 10 repos by eye, best decomposition first, into `notes/human_rank.txt`
(one repo name per line, BEFORE looking at scores), then

    python3 harness/pilot_check.py --budget <usd>

Read PILOT.md for the pass criteria. Do the two manual checks (P6 thresholds, P7 resolver
vs ent ci). If it says NO-GO, fix the named component and re-pilot only that check.
If the sample-size line says you need more repos than you have:

    python3 harness/build_corpus.py --n <N> --seed 7 --strata lowvis,famous --cutoff <model cutoff date>
    # then add ~30% of the new repos to harness/holdout.txt, stratified, BEFORE any skill edit

## 3. THE LOOP — starting it and keeping it going

The loop is resumable from repo state: `harness/status.sh` derives the current phase from
runs/, notes/, tags, and git log, and `harness/checkpoint.sh` commits and pushes after
every phase and iteration. That is what lets any of the three mechanisms below pick up
where the last one stopped, with zero memory of it.

The resume prompt (same for all three):

    Read CLAUDE.md, program.md, and LOOP.md. Run ./harness/status.sh and resume LOOP.md
    at the phase it names. Checkpoint after every phase and iteration. Keep going until
    status.sh reports DONE, BLOCKED, or WAITING.

### 3a. Claude Code on the web (cloud session) — simplest
1. At claude.ai/code, create a cloud environment for this repo:
   - Environment variables:
         LU_MODEL=<primary model id>        # pin it; the CLI default drifts and the pilot's variance is model-specific
         LU_MAX_ITER=12
         ANTHROPIC_API_KEY=<key>            # optional but recommended: the INNER `claude -p` runs (the bulk of the
                                            # spend) then bill to the API instead of your plan's usage limit, which
                                            # is what killed the first Phase 0 attempt. Anyone using the environment
                                            # can read it, so use a scoped key on a personal environment.
   - Setup script (cached as a snapshot, so it runs once):
         pip install -r requirements.txt
     (The repo's SessionStart hook installs from the same file if they are missing, so the
     setup script is an optimisation, not a requirement.)
   - Network: Trusted is enough (GitHub, PyPI, api.anthropic.com are in the default list).
2. Start a session on the branch you want the results on, paste the resume prompt.
   The session keeps running when you close the browser.
3. When it stops (context, turn, or time limit), open the session and send the resume
   prompt again. Because everything is checkpointed, nothing is repeated.

### 3b. Routine (scheduled) — hands-off across days
Create a routine at claude.ai/code/routines: repository = this repo, environment = the
one above, trigger = hourly or nightly, prompt = the resume prompt plus one line:
    Work on branch <your-branch>; pull it first. Stop after one phase or one ratchet
    iteration and checkpoint.
Each run is a fresh session with zero context; status.sh gives it its place. The
routine keeps firing until status.sh reports DONE (it then does nothing) or exits 2
(BLOCKED/WAITING — it stops and you fix the note). Pause the routine when you are done.

### 3c. Your own machine or self-hosted runner — deterministic
    ./harness/supervise.sh 20 300      # up to 20 launches, 300 turns each
A shell loop: status → launch a fresh `claude -p` with the resume prompt → checkpoint →
repeat until DONE/BLOCKED/WAITING. Needs `claude` authenticated and the deps installed.
This is the most controllable option and the one to use for the 100-repo campaign.

In every case, the morning read is the same: `notes/SUMMARY.md` (if DONE), `results.tsv`,
`git log --oneline baseline..HEAD`, and `notes/BLOCKED.md` or `notes/NEED_CORPUS.md` if it stopped.

## 4. The inner prompt (you never type this; run_one.sh does)

    claude -p "/lu-decompose" --allowedTools "Read,Grep,Glob,Agent,Write,Bash(ent:*)" \
      --max-turns 60 --output-format json

`/lu-decompose` invokes overlay/.claude/skills/lu-decompose/SKILL.md inside the target repo.
The hooks in overlay/.claude/settings.json guarantee: only /out/manifest.json is written,
the manifest is linted on every write, and the session cannot end without one.

## 5. Human-only, at the end

    LU_HOLDOUT_OK=1 ./harness/run_corpus.sh --reps 0,1,2 --only <holdout names>
    python3 harness/aggregate.py --holdout --label $(git rev-parse --short HEAD)

The holdout is scored once, after the last kept edit. Never by the agent.
