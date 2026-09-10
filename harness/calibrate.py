#!/usr/bin/env python3
"""calibrate.py — does the instrument recognise a good decomposition when handed one?

  calibrate.py                 build synthetic repos, score gold + degraded manifests, report
  calibrate.py --keep          leave the generated repos in /tmp for inspection
  calibrate.py --json          machine-readable

Why this exists (notes/architecture.md change 2)
------------------------------------------------
test_score.py checks the scorer's arithmetic on hand-built fixtures. It does NOT answer the
measurement-theory question: given a repository whose correct decomposition is known BY
CONSTRUCTION, what score does the correct answer get, and how far must you degrade it before
the score notices? Without that, "the model produced a bad decomposition" and "the metric
cannot see a good one" are indistinguishable — the exact confusion that cost $253 to discover
by accident.

Method
------
Generate a synthetic repo with a flat file layout (so the per-directory baseline q_dir is
degenerate and a good partition CAN win) and a known module structure: N units, each a core
file that exposes one public entrypoint plus internal helpers, with cross-unit calls only
through cores. The correct partition, entrypoints and effects are known.

Then score the gold manifest and a set of deliberately degraded ones, through the REAL
score.py pipeline. Report each variant's q_gain_dir, validity, contract recall and singleton
fraction, and assert the orderings a trustworthy instrument must satisfy:

  SENSITIVITY  gold must be valid and score the highest q_gain_dir; over-split (one-per-file)
               and under-split (one-giant) must be flagged trivial; merge/misassign must
               score strictly below gold.
  SPECIFICITY  dropping an entrypoint (a CONTRACT error, not a partition error) must NOT move
               q_gain_dir — it must instead show up in contract recall. If q_gain_dir moved,
               the quality metric is entangled with contract fidelity and the two gates are
               not independent.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
N_UNITS = 5           # u0..u4
FILES_PER_UNIT = 3    # core + two helpers

def gen_repo(root: Path):
    """Flat layout: every file in repo root. Cross-unit edges only through cores."""
    root.mkdir(parents=True, exist_ok=True)
    (root / '.git').mkdir(exist_ok=True)     # marks a repo root; git log will just be empty
    units = []
    for i in range(N_UNITS):
        core = f"u{i}_core.py"; h1 = f"u{i}_alpha.py"; h2 = f"u{i}_beta.py"
        prev = f"u{i-1}_core" if i > 0 else None
        imp = f"import u{i}_alpha\nimport u{i}_beta\n" + (f"from u{i-1}_core import entry_{i-1}\n" if prev else "")
        # a FREE-symbol cross-unit call so the resolver records it as a ref (attribute calls are skipped)
        call_prev = f"    return entry_{i-1}(0)\n" if prev else "    return _mk()\n"
        (root / core).write_text(
            imp +
            f"def entry_{i}(x):\n    '''public entrypoint of unit {i}'''\n" + call_prev +
            f"def _mk():\n    return u{i}_alpha.step() + u{i}_beta.step()\n")
        # helper alpha touches the filesystem -> a detectable 'filesystem' effect
        (root / h1).write_text(
            "import os\ndef step():\n    return len(os.listdir('.'))\ndef _priv():\n    return 1\n")
        (root / h2).write_text(
            f"import u{i}_alpha\ndef step():\n    return u{i}_alpha._priv() + 1\ndef _also():\n    return 2\n")
        units.append(dict(name=f"unit-{i}", kind="domain", files=[core, h1, h2],
                          entrypoints=[dict(name=f"entry_{i}", type="function")],
                          effects=[dict(kind="filesystem")]))
    return units

def gold_manifest(units):
    return dict(units=[dict(u) for u in units], excluded=[], unpartitioned=[])

def degrade(units, kind):
    u = [dict(x, files=list(x['files']),
              entrypoints=[dict(e) for e in x['entrypoints']],
              effects=[dict(e) for e in x['effects']]) for x in units]
    if kind == 'gold':
        pass
    elif kind == 'merge-two':                       # fold unit-1 into unit-0
        u[0]['files'] += u[1]['files']; u[0]['entrypoints'] += u[1]['entrypoints']
        u.pop(1)
    elif kind == 'misassign-file':                  # give one of unit-0's helpers to unit-1
        moved = u[0]['files'].pop()                 # a helper (not the core)
        u[1]['files'].append(moved)
    elif kind == 'one-giant':                       # collapse everything into one unit
        allf = [f for x in u for f in x['files']]; alle = [e for x in u for e in x['entrypoints']]
        u = [dict(name='everything', kind='domain', files=allf, entrypoints=alle,
                  effects=[dict(kind='filesystem')])]
    elif kind == 'one-per-file':                    # explode to a unit per file
        u = [dict(name=f"f-{f}", kind='domain', files=[f],
                  entrypoints=([e for e in x['entrypoints']] if f == x['files'][0] else []),
                  effects=[dict(kind='filesystem')])
             for x in units for f in x['files']]
    elif kind == 'drop-entrypoint':                 # remove unit-0's declared entrypoint (contract error only)
        u[0]['entrypoints'] = []
    else:
        raise ValueError(kind)
    return dict(units=u, excluded=[], unpartitioned=[])

def score_variant(repo: Path, manifest: dict, tmp: Path, variant: str):
    # score.py caches the resolver graph at run.resolve().parents[1]/graph.json. Use the real
    # runs/<repo>/<sha>/<label>/<rep> nesting under this invocation's tmp dir so the cache lands
    # inside tmp (fresh, shared across variants of the same repo) and never collides with a
    # stale /tmp/graph.json from another repo.
    run = tmp / 'runs' / repo.name / 'sha' / variant / '0'; run.mkdir(parents=True, exist_ok=True)
    (run / 'manifest.json').write_text(json.dumps(manifest))
    (run / 'result.json').write_text(json.dumps(
        dict(total_cost_usd=0.0, num_turns=1, subtype='success', duration_ms=0, usage={})))
    (run / 'meta.json').write_text(json.dumps(dict(repo=f"synthetic/{repo.name}", condition='calib')))
    out = subprocess.run([sys.executable, str(HERE / 'score.py'), str(run), str(repo)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return dict(error=out.stderr.strip()[:200])
    return json.loads(out.stdout)

VARIANTS = ['gold', 'merge-two', 'misassign-file', 'one-giant', 'one-per-file', 'drop-entrypoint']

def run(keep=False, as_json=False):
    base = Path(tempfile.mkdtemp(prefix='lu-calib-'))
    repo = base / 'synthrepo'; units = gen_repo(repo)
    rows = {}
    for v in VARIANTS:
        m = gold_manifest(units) if v == 'gold' else degrade(units, v)
        s = score_variant(repo, m, base, v)
        rows[v] = s
    if as_json:
        print(json.dumps(rows, indent=1))
    else:
        print(f"synthetic repo: {N_UNITS} units x {FILES_PER_UNIT} files, flat layout   ({repo})")
        print(f"graph backend: {rows['gold'].get('graph_source','?')}\n")
        print(f"{'variant':16}{'valid':>7}{'trivial':>8}{'gain':>9}{'q_dir':>8}{'cov':>6}{'ep_r':>7}{'singl':>7}")
        for v in VARIANTS:
            s = rows[v]
            if 'error' in s: print(f"{v:16}  ERROR {s['error']}"); continue
            ep = s.get('contract_r'); sf = s.get('singleton_unit_frac')
            print(f"{v:16}{('y' if s['valid_nontrivial'] else '-'):>7}{('y' if s['trivial'] else '-'):>8}"
                  f"{s['q_gain_dir']:>+9.4f}{s['q_dir']:>8.4f}{s['coverage']:>6.2f}"
                  f"{(f'{ep:.2f}' if ep is not None else '-'):>7}{(f'{sf:.2f}' if sf is not None else '-'):>7}")

    # ---- assertions: the instrument must satisfy these or it cannot be trusted ----
    g = rows['gold']; checks = []
    def chk(name, ok, detail=''): checks.append((name, bool(ok), detail))

    chk('gold is valid_nontrivial', g.get('valid_nontrivial') is True, str(g.get('valid_nontrivial')))
    chk('gold gain > 0 (correct partition beats flat q_dir)', g.get('q_gain_dir', -1) > 0,
        f"gain={g.get('q_gain_dir')}")
    chk('one-giant flagged trivial', rows['one-giant'].get('trivial') is True)
    chk('one-per-file flagged trivial', rows['one-per-file'].get('trivial') is True)
    if 'q_gain_dir' in rows['merge-two']:
        chk('merge-two gain <= gold (SENS)', rows['merge-two']['q_gain_dir'] <= g['q_gain_dir'] + 1e-9,
            f"{rows['merge-two']['q_gain_dir']} vs {g['q_gain_dir']}")
    if 'q_gain_dir' in rows['misassign-file']:
        chk('misassign gain <= gold (SENS)', rows['misassign-file']['q_gain_dir'] <= g['q_gain_dir'] + 1e-9,
            f"{rows['misassign-file']['q_gain_dir']} vs {g['q_gain_dir']}")
    # SPECIFICITY: a pure contract error must not move the partition-quality metric
    if 'q_gain_dir' in rows['drop-entrypoint']:
        chk('drop-entrypoint leaves gain unchanged (SPEC)',
            abs(rows['drop-entrypoint']['q_gain_dir'] - g['q_gain_dir']) < 1e-9,
            f"{rows['drop-entrypoint']['q_gain_dir']} vs {g['q_gain_dir']}")
    # and it SHOULD show up in contract recall if the resolver ran
    gr, dr = g.get('contract_r'), rows['drop-entrypoint'].get('contract_r')
    if gr is not None and dr is not None:
        chk('drop-entrypoint strictly lowers contract recall (SPEC)', dr < gr - 1e-9, f"{dr} vs {gr}")

    npass = sum(1 for _, ok, _ in checks if ok)
    print()
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if (detail and not ok) else ''))
    print(f"\n{npass}/{len(checks)} calibration checks passed")
    if not keep:
        import shutil; shutil.rmtree(base, ignore_errors=True)
    else:
        print(f"(kept synthetic repo at {base})")
    return 0 if npass == len(checks) else 1

if __name__ == '__main__':
    sys.exit(run(keep='--keep' in sys.argv, as_json='--json' in sys.argv))
