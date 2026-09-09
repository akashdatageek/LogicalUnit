# Patch 03 — harness/test_score.py: fixture tests for the scorer

> **APPLIED** in `7b1bf52`. Kept as the rationale and evidence record; the change is live in the tree.

**Priority: apply with patch 01; it is how you verify patch 01.**

The scorer is the one component every result depends on and the only one with no tests. Four
defects in it were found by running real experiments against them, one of which halted the
loop for a full session. Seven fixtures find three of the four in four seconds.

Each case builds a tiny synthetic repo and manifest in a temp dir, runs `score.py` as a
subprocess, and asserts on the JSON. Failures name the defect and what it costs.

## Verified output against the CURRENT scorer

```
scoring fixtures against /home/user/LogicalUnit/harness/score.py

  PASS  exact-path exclusion
  FAIL  directory-prefix exclusion
  FAIL  malformed excluded entry
  PASS  budget from subtype
  PASS  real max-turns is caught
  PASS  one unit per file is trivial
  FAIL  non-source trees stay out of the denominator

4/7 passed
```

The three failures are the live defects patch 01 fixes. The four passes matter too:
`budget from subtype` and `real max-turns is caught` are regression guards for the v1.2 fix,
pinning both directions — a completed run with 140 subagent-inflated turns must not be flagged
exhausted, and a genuine `error_max_turns` must be.

After patch 01 all seven must pass. Run it from the SessionStart hook, or at minimum before
tagging any new baseline.

## How to use it

    python3 harness/test_score.py     # exit 0 = clean, exit 1 = at least one defect is live

Adding a case costs three lines: decorate a function with `@case(name, why)`, build a repo
with `build()`, assert on `run_score()`. Add one for every future scorer bug so it can only
be found once.

## The file

Create as `harness/test_score.py`. Verified working; the output above is a real run.

```python
#!/usr/bin/env python3
"""test_score.py — fixture tests for the scorer.  Run: python3 harness/test_score.py

The scorer is the one component every result depends on and the only one with no tests.
Each case builds a tiny synthetic repo + manifest, runs score.py as a subprocess, and
asserts on the JSON.  A case that fails names the defect and what it costs.

Exit 0 = all pass.  Exit 1 = at least one defect is live.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCORE = HERE / 'score.py'
CASES, FAILED = [], []

def case(name, why):
    def deco(fn):
        CASES.append((name, why, fn)); return fn
    return deco

def build(tmp, files, manifest, result=None, meta=None):
    """Create repo + run dir. files: {relpath: text}. Returns (run_dir, repo_dir)."""
    repo = Path(tmp) / 'repo'; run = Path(tmp) / 'run'
    run.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = repo / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    (run / 'manifest.json').write_text(json.dumps(manifest))
    (run / 'result.json').write_text(json.dumps(result or
        {"subtype": "success", "terminal_reason": "completed", "num_turns": 12,
         "total_cost_usd": 1.0, "is_error": False, "usage": {}}))
    (run / 'meta.json').write_text(json.dumps(meta or {"repo": "x/y", "max_turns": 60}))
    return run, repo

def run_score(run, repo):
    p = subprocess.run([sys.executable, str(SCORE), str(run), str(repo)],
                       capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise AssertionError(f"score.py exited {p.returncode}: {p.stderr.strip()[-400:]}")
    if not p.stdout.strip():
        raise AssertionError("score.py produced no output (empty score.json)")
    return json.loads(p.stdout)

def unit(name, files, eps=()):
    return {"name": name, "kind": "domain", "description": "d" * 45, "files": list(files),
            "entrypoints": [{"name": e, "kind": "function", "location": f"{files[0]}:1"} for e in eps],
            "depends_on": [], "effects": []}

# --------------------------------------------------------------------------- cases

@case("exact-path exclusion", "control: the path score.py already handles")
def t_exact(tmp):
    run, repo = build(tmp,
        {"pkg/a.py": "import b\n", "pkg/b.py": "x=1\n", "tests/test_a.py": "import a\n"},
        {"repo": "x/y", "units": [unit("core", ["pkg/a.py", "pkg/b.py"], ["a"])],
         "excluded": [{"path": "tests/test_a.py", "reason": "test"}], "unpartitioned": []})
    s = run_score(run, repo)
    assert s["coverage"] == 1.0, f"coverage {s['coverage']} != 1.0"

@case("directory-prefix exclusion", "M1: excluding a directory must exclude the files under it")
def t_prefix(tmp):
    files = {"pkg/a.py": "x=1\n", "pkg/b.py": "x=1\n"}
    for i in range(30):
        files[f"docs_src/ex{i}.py"] = "x=1\n"      # doc examples, not library source
    run, repo = build(tmp, files,
        {"repo": "x/y", "units": [unit("core", ["pkg/a.py", "pkg/b.py"], ["a"])],
         "excluded": [{"path": "docs_src", "reason": "documentation examples"}],
         "unpartitioned": []})
    s = run_score(run, repo)
    assert s["coverage"] >= 0.95, (
        f"coverage {s['coverage']} — the 30 docs_src files were counted as in-scope even "
        f"though the manifest excluded that directory. A correct decomposition scores invalid.")

@case("malformed excluded entry", "M3: score the run, do not crash on bad model output")
def t_malformed(tmp):
    run, repo = build(tmp, {"pkg/a.py": "x=1\n"},
        {"repo": "x/y", "units": [unit("core", ["pkg/a.py"], ["a"])],
         "excluded": [{"__PLACEHOLDER__": True}], "unpartitioned": []})
    s = run_score(run, repo)     # must not raise
    assert "valid_nontrivial" in s

@case("budget from subtype", "regression guard: v1.2 fix, num_turns counts subagent turns")
def t_budget(tmp):
    run, repo = build(tmp, {"pkg/a.py": "import b\n", "pkg/b.py": "x=1\n"},
        {"repo": "x/y", "units": [unit("a", ["pkg/a.py"], ["a"]), unit("b", ["pkg/b.py"], ["b"])],
         "excluded": [], "unpartitioned": []},
        result={"subtype": "success", "terminal_reason": "completed", "num_turns": 140,
                "total_cost_usd": 1.0, "is_error": False, "usage": {}},
        meta={"repo": "x/y", "max_turns": 60})
    s = run_score(run, repo)
    assert s["budget_exhausted"] is False, (
        "num_turns 140 > max_turns 60 but the run completed; budget_exhausted must come "
        "from subtype/terminal_reason, not the turn counter")

@case("real max-turns is caught", "the other direction: a genuine cap hit must be flagged")
def t_budget_real(tmp):
    run, repo = build(tmp, {"pkg/a.py": "x=1\n"},
        {"repo": "x/y", "units": [unit("core", ["pkg/a.py"], ["a"])], "excluded": [], "unpartitioned": []},
        result={"subtype": "error_max_turns", "terminal_reason": "max_turns", "num_turns": 61,
                "total_cost_usd": 1.0, "is_error": True, "usage": {}})
    s = run_score(run, repo)
    assert s["budget_exhausted"] is True, "error_max_turns must set budget_exhausted"

@case("one unit per file is trivial", "the anti-pattern the skill exists to prevent")
def t_trivial(tmp):
    files = {f"pkg/f{i}.py": "x=1\n" for i in range(8)}
    run, repo = build(tmp, files,
        {"repo": "x/y", "units": [unit(f"u{i}", [f"pkg/f{i}.py"], [f"e{i}"]) for i in range(8)],
         "excluded": [], "unpartitioned": []})
    s = run_score(run, repo)
    assert s["trivial"] is True, "8 units over 8 files must be flagged trivial"
    assert s["singleton_unit_frac"] == 1.0, f"singleton_unit_frac {s['singleton_unit_frac']} != 1.0"

@case("non-source trees stay out of the denominator", "M2: skip list misses sample/ integration/")
def t_skiplist(tmp):
    files = {"pkg/a.py": "x=1\n"}
    for i in range(40):
        files[f"sample/s{i}.py"] = "x=1\n"          # example apps, not library source
    run, repo = build(tmp, files,
        {"repo": "x/y", "units": [unit("core", ["pkg/a.py"], ["a"])],
         "excluded": [], "unpartitioned": []})
    s = run_score(run, repo)
    assert s["coverage"] >= 0.95, (
        f"coverage {s['coverage']} — 40 sample/ files inflate the denominator; "
        f"either the skip list must cover them or the manifest must be able to exclude the tree")

# --------------------------------------------------------------------------- runner

def main():
    print(f"scoring fixtures against {SCORE}\n")
    for name, why, fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                fn(tmp); print(f"  PASS  {name}")
            except AssertionError as e:
                FAILED.append((name, why, str(e))); print(f"  FAIL  {name}")
            except Exception as e:
                FAILED.append((name, why, f"{type(e).__name__}: {e}")); print(f"  ERROR {name}")
    print()
    for name, why, msg in FAILED:
        print(f"[{name}] {why}\n    {msg}\n")
    print(f"{len(CASES)-len(FAILED)}/{len(CASES)} passed")
    return 1 if FAILED else 0

if __name__ == '__main__':
    sys.exit(main())
```
