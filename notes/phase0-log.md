# Phase 0 attempt log

## Attempt 1 — label 6d58dca, psf/requests rep 0 (2026-09-08 21:27 UTC)
Dead run. The inner `claude -p` returned after 356 ms with is_error=true and the text
"You've hit your session limit · resets 10pm (UTC)" (account usage limit, not a harness
fault). No manifest, 0 lint rounds, score.json valid_nontrivial=false. Left in place under
runs/requests/<sha>/6d58dca/0 per the never-delete rule; excluded from analysis because
turns=1 and result.is_error=true. stderr also reported "this workspace has not been trusted",
which drops the overlay's permissions.allow entries (the CLI --allowedTools flag still applies).
Retry goes under the next label.

## Phase 1 sweep incident (2026-09-08 23:42 UTC) — harness bug in run_corpus.sh
`run_corpus.sh` reads corpus.txt through `grep | while read`; the inner `claude -p` in
run_one.sh inherits that pipe as stdin and drains it, so the loop ended after the first repo
(requests) in both the skill and the noskill pass. Consequences: (a) requests skill rep 0
(label dfb7d01) probably received the remaining nine corpus lines appended to its prompt;
treat that replicate with suspicion when coding rq1; (b) the other six dev repos were driven
by scratchpad/sweep_rest.sh, which calls run_one.sh per repo/rep with the same arguments and
`< /dev/null`. Output is identical to what run_corpus.sh would have produced. Fix for the
human: `"$HERE/harness/run_one.sh" ... < /dev/null` inside the loop (or read from fd 3).

## Phase 1 sweep incident 2 (2026-09-09 01:14 UTC) — usage limit killed the baseline
At 01:14 UTC the inner `claude -p` began returning "You've hit your session limit · resets
3:10am (UTC)" (terminal_reason=api_error). fastapi rep 0 died mid-run after $4.89 and 90
turns; the following 12 skill runs (fastapi 1-2, ripgrep 0-2, nest 0-2, MAVSDK 0-2) and 6
noskill runs (all but requests) returned in <1 s with cost 0, empty manifests, run_error=true.
Each still wrote a score.json, so status.sh counted the baseline as complete. Under the
never-rerun rule those (repo, dfb7d01, rep) slots are dead, so label dfb7d01 is abandoned as
the baseline. Its 8 good runs (requests 0-1, cobra 0-2, flask 0-2) and the requests noskill
run are kept as a pre-baseline sample only; they are not pooled with the baseline.
Baseline restarts under the next label with a limit-aware driver (probe before each run;
wait for the reset when the probe reports the limit). Root cause and permanent fix (human):
inner runs bill to the plan; set ANTHROPIC_API_KEY in the environment (PROMPTS.md v1.2).
Spend so far: 12 real runs, ~$58.
