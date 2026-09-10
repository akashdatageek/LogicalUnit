#!/usr/bin/env python3
"""Aggregate runs/ and DECIDE keep/revert deterministically.

  aggregate.py [--rep 0-2]            table for current runs
  aggregate.py --tsv >> results.tsv   one row per skill version
  aggregate.py --decide <label_before> <label_after> [--alpha 0.10] [--boot 5000]
        Paired bootstrap on per-repo deltas of the primary quality metric, with a
        validity gate. Prints KEEP or REVERT and the CI. The agent may not override it.

Run labels: runs are stored under runs/<repo>/<sha>/<label>/<rep>/ where label is the
skill git sha at run time (written by run_one.sh). Replicate = repetition, not a seed.
"""
import json, random, sys
from itertools import combinations
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / 'runs'
HOLDOUT = {l.strip() for l in (HERE/'harness'/'holdout.txt').read_text().splitlines() if l.strip() and not l.startswith('#')} if (HERE/'harness'/'holdout.txt').exists() else set()

def partition(manifest):
    return {f: u['name'] for u in manifest.get('units', []) for f in u.get('files', [])}

def pair_jaccard(p1, p2):
    files = sorted(set(p1) | set(p2)); s1 = s2 = both = 0
    for a, b in combinations(files, 2):
        x = p1.get(a) is not None and p1.get(a) == p1.get(b); y = p2.get(a) is not None and p2.get(a) == p2.get(b)
        s1 += x; s2 += y; both += x and y
    u = s1 + s2 - both
    return both/u if u else 1.0

def load(label=None, reps=None, include_holdout=False):
    per = {}
    for sp in RUNS.glob('*/*/*/*/score.json'):
        run = sp.parent; name, sha, lab, rep = run.parts[-4:]
        if label and lab != label: continue
        if reps and rep not in reps: continue
        if name in HOLDOUT and not include_holdout: continue
        s = json.loads(sp.read_text()); m = json.loads((run/'manifest.json').read_text() or '{}')
        meta = json.loads((run/'meta.json').read_text()) if (run/'meta.json').exists() else {}
        per.setdefault(name, []).append(dict(rep=rep, s=s, part=partition(m), meta=meta))
    return per

def summarise(per):
    rows = []
    for name, runs in sorted(per.items()):
        S = [r['s'] for r in runs]
        jac = mean(pair_jaccard(a['part'], b['part']) for a, b in combinations(runs, 2)) if len(runs) > 1 else None
        rows.append(dict(repo=name, n=len(runs),
            valid=mean(1 if x['valid_nontrivial'] else 0 for x in S),
            gain=mean(x['q_gain_dir'] for x in S),
            cochange=mean(x['q_cochange_gain'] for x in S if x['q_cochange_gain'] is not None) if any(x['q_cochange_gain'] is not None for x in S) else None,
            gold=mean(x['gold_ari'] for x in S if x['gold_ari'] is not None) if any(x['gold_ari'] is not None for x in S) else None,
            coverage=mean(x['coverage'] for x in S), edge=mean(x['edge_resolution'] for x in S),
            contract=mean(x['contract_r'] for x in S if x.get('contract_r') is not None) if any(x.get('contract_r') is not None for x in S) else None,
            ep_r=mean(x['entrypoint_r'] for x in S if x.get('entrypoint_r') is not None) if any(x.get('entrypoint_r') is not None for x in S) else None,
            ef_r=mean(x['effects_r'] for x in S if x.get('effects_r') is not None) if any(x.get('effects_r') is not None for x in S) else None,
            units=mean(x['n_units'] for x in S), cost=mean(x['cost_usd'] or 0 for x in S),
            exhausted=sum(x['budget_exhausted'] for x in S), jaccard=jac,
            md=any(r['meta'].get('has_claude_md') for r in runs), cond=runs[0]['meta'].get('condition','skill'),
            stratum=runs[0]['meta'].get('stratum','unknown')))
    return rows

def corpus(rows):
    return dict(n_repos=len(rows), n_runs=sum(r['n'] for r in rows),
        valid_rate=mean(r['valid'] for r in rows), mean_gain=mean(r['gain'] for r in rows),
        mean_jaccard=mean(r['jaccard'] for r in rows if r['jaccard'] is not None) if any(r['jaccard'] is not None for r in rows) else None,
        mean_cost=mean(r['cost'] for r in rows))

def _decide_core(before, after, alpha=0.10, boot=5000):
    """Return {verdict, line, n_repos}. No printing. Shared by --decide and --decide-transfer."""
    A, B = load(before), load(after)
    common = sorted(set(A) & set(B))
    if len(common) < 3:
        return dict(verdict='REVERT', n_repos=len(common),
                    line=f"REVERT  (only {len(common)} repos in common; need >=3)")
    ra = {r['repo']: r for r in summarise({k: A[k] for k in common})}
    rb = {r['repo']: r for r in summarise({k: B[k] for k in common})}
    va, vb = mean(ra[k]['valid'] for k in common), mean(rb[k]['valid'] for k in common)
    if vb < va - 1e-9 and (va - vb) * len(common) > 1.0/3:
        return dict(verdict='REVERT', n_repos=len(common), line=f"REVERT  validity gate: {va:.2f} -> {vb:.2f}")
    ja = [ra[k]['jaccard'] for k in common if ra[k]['jaccard'] is not None]
    jb = [rb[k]['jaccard'] for k in common if rb[k]['jaccard'] is not None]
    if ja and jb and mean(jb) < mean(ja) - 0.15:
        return dict(verdict='REVERT', n_repos=len(common), line=f"REVERT  stability gate: jaccard {mean(ja):.2f} -> {mean(jb):.2f}")
    ca = [ra[k]['contract'] for k in common if ra[k]['contract'] is not None]
    cb = [rb[k]['contract'] for k in common if rb[k]['contract'] is not None]
    if ca and cb and mean(cb) < mean(ca) - 0.05:
        return dict(verdict='REVERT', n_repos=len(common), line=f"REVERT  contract gate: recall {mean(ca):.2f} -> {mean(cb):.2f}")
    deltas = [rb[k]['gain'] - ra[k]['gain'] for k in common]
    rng = random.Random(0); means = []
    for _ in range(boot):
        means.append(mean(rng.choice(deltas) for _ in deltas))
    means.sort(); lo, hi = means[int(alpha/2*boot)], means[int((1-alpha/2)*boot)-1]
    obs = mean(deltas)
    verdict = 'KEEP' if lo > 0 else 'REVERT'
    return dict(verdict=verdict, n_repos=len(common),
                line=f"{verdict}  delta_gain={obs:+.4f}  {int((1-alpha)*100)}%CI=[{lo:+.4f},{hi:+.4f}]  validity {va:.2f}->{vb:.2f}  n_repos={len(common)}")

def decide(before, after, alpha=0.10, boot=5000):
    print(_decide_core(before, after, alpha, boot)['line'])

def decide_transfer(before, after, models, alpha=0.10, boot=5000):
    """KEEP only if the edit holds on EVERY model (notes/architecture.md change 4).

    Model is a run-label suffix (run_one.sh): <sha>-opus5, <sha>-sonnet5, or a bare <sha> for
    legacy runs. `models` is that list of suffixes; the token 'base' means the bare label.
    An edit that is KEEP on one model and REVERT on another is REVERT overall: that is the
    difference between 'this wording helps model X' and 'this is a better instruction'.
    """
    results = []
    for m in models:
        lb = before if m in ('base', '') else f"{before}-{m}"
        la = after  if m in ('base', '') else f"{after}-{m}"
        r = _decide_core(lb, la, alpha, boot)
        results.append((m, lb, la, r))
        print(f"  [{m:8}] {lb} -> {la}\n            {r['line']}")
    keeps = [r['verdict'] == 'KEEP' for _, _, _, r in results]
    overall = 'KEEP' if keeps and all(keeps) else 'REVERT'
    n_keep = sum(keeps)
    print(f"\nTRANSFER {overall}  ({n_keep}/{len(results)} models KEEP)  "
          f"-- KEEP requires all {len(results)} models")

def n_dev():
    """Number of pinned, non-holdout repos in corpus.txt (for the Phase-2 gate)."""
    c = HERE/'harness'/'corpus.txt'
    if not c.exists(): return 0
    n = 0
    for l in c.read_text().splitlines():
        if not l.strip() or l.startswith('#'): continue
        parts = l.split()
        if len(parts) < 2 or parts[1] == 'PIN_ME': continue
        if parts[0].split('/')[-1] in HOLDOUT: continue
        n += 1
    return n

def main():
    a = sys.argv[1:]
    if a and a[0] == '--n-dev': print(n_dev()); return
    if a and a[0] == '--decide':
        alpha = float(a[a.index('--alpha')+1]) if '--alpha' in a else 0.10
        boot = int(a[a.index('--boot')+1]) if '--boot' in a else 5000
        return decide(a[1], a[2], alpha, boot)
    if a and a[0] == '--decide-transfer':
        alpha = float(a[a.index('--alpha')+1]) if '--alpha' in a else 0.10
        boot = int(a[a.index('--boot')+1]) if '--boot' in a else 5000
        models = (a[a.index('--models')+1].split(',') if '--models' in a
                  else ['base', 'opus5'])
        return decide_transfer(a[1], a[2], models, alpha, boot)
    label = a[a.index('--label')+1] if '--label' in a else None
    reps = set(a[a.index('--rep')+1].split(',')) if '--rep' in a else None
    per = load(label, reps, include_holdout='--holdout' in a)
    rows = summarise(per)
    if not rows: print('no runs'); return
    c = corpus(rows)
    if '--tsv' in a:
        print(f"{label or 'HEAD'}\t{c['n_repos']}\t{c['n_runs']}\t{c['valid_rate']:.3f}\t{c['mean_gain']:.4f}\t{c['mean_jaccard'] or 0:.3f}\t{c['mean_cost']:.3f}"); return
    if '--json' in a: print(json.dumps(dict(corpus=c, repos=rows), indent=2)); return
    print(f"repos={c['n_repos']} runs={c['n_runs']}  VALID {c['valid_rate']:.2f}  GAIN(dir) {c['mean_gain']:+.4f}  jaccard {c['mean_jaccard'] or 0:.2f}  cost ${c['mean_cost']:.2f}\n")
    strata = sorted({r['stratum'] for r in rows})
    if len(strata) > 1:
        print("per stratum:  " + "   ".join(f"{st}: valid {mean(r['valid'] for r in rows if r['stratum']==st):.2f} gain {mean(r['gain'] for r in rows if r['stratum']==st):+.3f} (n={sum(1 for r in rows if r['stratum']==st)})" for st in strata) + "\n")
    print(f"{'repo':20}{'n':>3}{'valid':>7}{'gain':>8}{'cochg':>8}{'gold':>7}{'cov':>6}{'edge':>6}{'ep_r':>6}{'ef_r':>6}{'units':>6}{'jac':>6}{'exh':>4}{'$':>6}  md cond")
    for r in rows:
        f = lambda v, w: f"{v:>{w}.3f}" if v is not None else f"{'-':>{w}}"
        print(f"{r['repo']:20}{r['n']:>3}{r['valid']:>7.2f}{r['gain']:>+8.3f}{f(r['cochange'],8)}{f(r['gold'],7)}{r['coverage']:>6.2f}{r['edge']:>6.2f}{f(r['ep_r'],6)}{f(r['ef_r'],6)}"
              f"{r['units']:>6.1f}{f(r['jaccard'],6)}{r['exhausted']:>4}{r['cost']:>6.2f}  {'y' if r['md'] else '-'}  {r['cond']}")

if __name__ == '__main__': main()
