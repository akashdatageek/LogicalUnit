# Baseline

The `baseline` tag marks the commit whose overlay is the baseline skill. If the tag is
missing (it could not be pushed: proxy returned 403 on tag refs), recreate it at the
commit recorded here, never at a later HEAD:

    git tag baseline <sha below>

baseline sha: 404a0f1
