# Baseline

The `baseline` tag marks the commit whose overlay is the baseline skill, and the sweep runs
are labelled with that commit's short sha (run_one.sh labels by HEAD). A note cannot name
its own commit, so the tag is defined relative to a fixed ancestor:

    baseline = the direct child of 1af7b3a on this branch
    recover:  git tag baseline $(git rev-list --reverse --ancestry-path 1af7b3a..HEAD | head -1)

Cross-check: the label directory under runs/<repo>/<repo-sha>/ that holds reps 0,1,2 of the
Phase 1 sweep is the baseline label. Never recreate the tag at a later HEAD.

History: the first baseline tag (child of a9640c3 = dfb7d01) was abandoned after the usage
limit killed 18 of its runs; see notes/phase0-log.md. The current definition above supersedes it.
