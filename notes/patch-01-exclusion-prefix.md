# Patch 01 — honour directory-prefix exclusions (score.py + lint_stub.py)

> **APPLIED** in `7b1bf52`. Kept as the rationale and evidence record; the change is live in the tree.

**Priority: apply before any further runs.** This is one bug in two files. It causes the
coverage artefact (M1), the scorer crash (M3), *and* it is the mechanical driver of F8, the
dominant failure mode. Fixing it is the highest-value change available.

## The causal chain, with evidence

`lint_stub.py` and `score.py` both treat `excluded` as a set of exact paths. A manifest that
excludes a directory therefore excludes nothing.

fastapi rep 0 excluded four directories, exactly as the schema invites:

    "excluded": [{"path": "tests"}, {"path": "docs"}, {"path": "docs_src"}, {"path": "scripts"}]

The lint hook answered, on the very first round (`runs/fastapi/*/cac873e/0/lint.log`):

    I1 'docs_src/additional_responses/__init__.py' in no unit, not excluded, not unpartitioned
    I1 'docs_src/additional_responses/tutorial001_py310.py' in no unit, not excluded, not unpartitioned
    ... 50 lines (the stub caps the list at 50)

The model is now told its correct exclusion does not count. The only way to satisfy the lint
is to enumerate files one at a time — which is precisely what flask did, listing 56 individual
excluded paths. That text is generated output, output drives runtime at 7,200 tokens/min
(r = 0.996), and runtime drives the turn cap. Eight of 21 baseline runs died there.

Per-run I1 counts on rep 0: fastapi 50, flask 42, requests 17.

Scoring consequence, same run: fastapi decomposed all 48 real package files and was scored
`coverage 0.09`. Prefix-aware coverage is `1.00`.

## The fix

### harness/score.py — around line 147

```python
# before
    excluded = {e['path'] for e in m.get('excluded', [])}
    in_scope = [f for f in files if f not in excluded]

# after
    exc = [e['path'] for e in m.get('excluded', [])
           if isinstance(e, dict) and isinstance(e.get('path'), str)]
    excluded = set(exc)
    exc_dirs = tuple(p.rstrip('/') + '/' for p in exc)
    in_scope = [f for f in files if f not in excluded and not f.startswith(exc_dirs)]
```

The `isinstance` guard is the M3 fix: the fastapi noskill run emitted
`{"__DOCS_SRC_PLACEHOLDER__": true}` with no `path` key, score.py raised `KeyError`, and
run_one.sh's redirect left a zero-byte score.json that then broke `aggregate.py` for that
label. Scoring imperfect model output is the scorer's job; it should never raise on it.

`str.startswith(())` on an empty tuple returns `False`, so a manifest with no exclusions
behaves exactly as before.

### overlay/.claude/hooks/lint_stub.py — the I1 block

```python
# before
    excluded = {e['path'] for e in m.get('excluded', [])}
    unpart   = {e['path'] for e in m.get('unpartitioned', [])}
    missing = sorted(all_src - set(owned) - excluded - unpart)

# after
    def _paths(key):
        return [e['path'] for e in m.get(key, [])
                if isinstance(e, dict) and isinstance(e.get('path'), str)]
    exc, unp = _paths('excluded'), _paths('unpartitioned')
    skip_dirs = tuple(p.rstrip('/') + '/' for p in exc + unp)
    missing = sorted(f for f in all_src - set(owned) - set(exc) - set(unp)
                     if not f.startswith(skip_dirs))
```

Both files must change together. Fixing only the scorer leaves the lint hook still pushing
the model toward per-file enumeration; fixing only the hook leaves coverage wrong.

## Deliberately NOT changing the SKIP list

M2 in notes/rq1.md proposed adding `docs_src`, `integration` and `sample` to `score.py`'s
hardcoded `SKIP` set. **Do not.** Two reasons:

1. It silently changes what counts as source, which changes every historical score and is a
   sampling-frame decision, not a bug fix. It belongs in pre-registration if it happens at all.
2. With prefix exclusion working, the model can exclude those trees itself and the scorer will
   honour it. Letting the manifest declare scope is the more principled design and it is what
   the schema already intends.

The fixture `undeclared tree counts against coverage` in patch 03 pins this decision in both
directions: an undeclared tree must lower coverage, and declaring it by directory must restore
it. If someone later widens `SKIP`, that test fails loudly.

## Verification

`harness/test_score.py` (patch 03) contains the fixtures. Against the current scorer:

    FAIL  directory-prefix exclusion   coverage 0.062 with 30 docs_src files excluded by directory
    FAIL  malformed excluded entry     KeyError: 'path'

Both must pass after this patch, and the five currently-passing cases must stay passing.

## Expected effect on the next baseline

- fastapi becomes scoreable; its coverage stops being an artefact.
- Excluded-list output shrinks sharply on repos with large non-source trees, which should
  reduce F8. This is a prediction, not a certainty: log it as such and measure it.
- Re-score existing runs in place rather than re-running them:

      python3 harness/rescore.py            # see notes/patch-06; resolves each run's checkout

  Historical labels stay comparable because the same scorer version is applied to all of them.
  Note the re-score changes recorded numbers, so record which scorer sha produced results.tsv.
  A hand-rolled loop over `/work/<name>` no longer works: patch 04 made checkouts per-run
  (`/work/<name>-<sha>-<rep>`), so the re-scorer has to map a run directory back to a tree
  that matches its pinned sha. `rescore.py` does that.
