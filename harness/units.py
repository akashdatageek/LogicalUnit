#!/usr/bin/env python3
"""units.py — analyse runs at the UNIT level, not the run level.

  units.py [--label <sha>] [--rep 0,1,2]        per-repo unit table + corpus unit outcomes
  units.py --decide <label_before> <label_after> [--alpha 0.10] [--boot 5000]
        Cluster-robust paired bootstrap over repos on a unit-level outcome. KEEP/REVERT.

Why this exists
---------------
Every run emits one q_gain_dir and one valid flag, so the baseline sweep gave ~16
observations and power.py needs a generous tau assumption for 80% power. But each run
emits many independently-checkable units: score.py now persists per-unit ground truth
(from the resolver) under score.json["units"]. Counted over the same runs that gave 16
run-level rows, there are ~200 unit-level rows. Most rq2.md hypotheses are claims ABOUT
units ("the lead splits until it runs out of files", "a unit must be entered from
outside"), so testing them at the unit level matches the analysis to the hypothesis and
uses the n that is already there.

Unit-level outcomes (per unit, all in [0,1] or bool; None when the resolver could not run):
  entered_from_outside   is this unit reachable from outside it at all (else: probably not a unit)
  entrypoint_r           recall of the unit's true entrypoints (invariant 2)
  effects_r              recall of the unit's detected effects (invariant 4)
  is_singleton           owns <=1 file (over-split indicator)

Inference
---------
Units within a repo are NOT independent (one over-splitting run correlates all its units),
so a naive bootstrap over units would overstate precision. We resample REPOS with
replacement (the independent cluster), then take that repo's units — a cluster/block
bootstrap. The paired delta is (after unit-mean - before unit-mean) per repo, matching the
run-level --decide design in aggregate.py but on a far larger within-repo sample.
"""
import json, random, sys
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / 'runs'
HOLDOUT = {l.strip() for l in (HERE/'harness'/'holdout.txt').read_text().splitlines()
           if l.strip() and not l.startswith('#')} if (HERE/'harness'/'holdout.txt').exists() else set()

OUTCOMES = ('entered_from_outside', 'entrypoint_r', 'effects_r', 'is_singleton')

def _num(v):
    if v is None: return None
    if isinstance(v, bool): return 1.0 if v else 0.0
    return float(v)

def load_units(label=None, reps=None, include_holdout=False):
    """repo -> list of unit dicts (one row per unit per run). Skips runs with no unit data."""
    per = {}
    n_runs = n_runs_with_units = 0
    for sp in RUNS.glob('*/*/*/*/score.json'):
        run = sp.parent; name, sha, lab, rep = run.parts[-4:]
        if label and lab != label: continue
        if reps and rep not in reps: continue
        if name in HOLDOUT and not include_holdout: continue
        try: s = json.loads(sp.read_text())
        except Exception: continue
        n_runs += 1
        us = s.get('units')
        if not us: continue          # legacy run scored before per-unit persistence
        n_runs_with_units += 1
        per.setdefault(name, []).extend(us)
    return per, n_runs, n_runs_with_units

def repo_means(units_by_repo, outcome):
    """repo -> mean of `outcome` over its units (units with a None value are dropped)."""
    out = {}
    for repo, us in units_by_repo.items():
        vals = [_num(u.get(outcome)) for u in us]
        vals = [v for v in vals if v is not None]
        if vals: out[repo] = mean(vals)
    return out

def summarise(units_by_repo):
    rows = []
    for repo, us in sorted(units_by_repo.items()):
        row = dict(repo=repo, n_units=len(us))
        for oc in OUTCOMES:
            vals = [_num(u.get(oc)) for u in us]; vals = [v for v in vals if v is not None]
            row[oc] = mean(vals) if vals else None
        rows.append(row)
    return rows

def cluster_bootstrap_delta(before, after, outcome, alpha=0.10, boot=5000):
    """Paired delta of repo-mean(outcome), bootstrapped by resampling repos (the cluster)."""
    ma, mb = repo_means(before, outcome), repo_means(after, outcome)
    common = sorted(set(ma) & set(mb))
    if len(common) < 3: return None
    deltas = {r: mb[r] - ma[r] for r in common}
    obs = mean(deltas.values())
    rng = random.Random(0); means = []
    for _ in range(boot):
        sample = [rng.choice(common) for _ in common]
        means.append(mean(deltas[r] for r in sample))
    means.sort(); lo, hi = means[int(alpha/2*boot)], means[int((1-alpha/2)*boot)-1]
    return dict(outcome=outcome, obs=obs, lo=lo, hi=hi, n_repos=len(common),
                n_units_after=sum(len(after[r]) for r in common))

def decide(before_label, after_label, alpha=0.10, boot=5000):
    A, _, _ = load_units(before_label); B, _, _ = load_units(after_label)
    common = sorted(set(A) & set(B))
    if len(common) < 3:
        print(f"REVERT  (only {len(common)} repos with unit data in common; need >=3)"); return
    # Primary unit-level outcome for the ratchet: contract recall at unit level.
    # entrypoint_r is the invariant-2 ground truth per unit and is the one most rq2
    # hypotheses speak to. is_singleton is reported as a guardrail (higher = more over-split).
    print(f"unit-level decide  {before_label} -> {after_label}   (repos in common: {len(common)})\n")
    verdict_line = None
    for oc in OUTCOMES:
        r = cluster_bootstrap_delta(A, B, oc, alpha, boot)
        if r is None: continue
        direction = 'higher-better' if oc != 'is_singleton' else 'lower-better'
        sig = 'CI excludes 0' if (r['lo'] > 0 or r['hi'] < 0) else 'CI spans 0'
        print(f"  {oc:22} delta={r['obs']:+.4f}  {int((1-alpha)*100)}%CI=[{r['lo']:+.4f},{r['hi']:+.4f}]  "
              f"({direction}; {sig})  n_units={r['n_units_after']}")
        if oc == 'entrypoint_r': verdict_line = r
    if verdict_line is None:
        print("\nno entrypoint_r signal available (resolver produced no unit ground truth)"); return
    keep = verdict_line['lo'] > 0
    print(f"\n{'KEEP' if keep else 'REVERT'}  on unit-level entrypoint recall  "
          f"delta={verdict_line['obs']:+.4f} CI=[{verdict_line['lo']:+.4f},{verdict_line['hi']:+.4f}]")
    print("(advisory unit-level view; the run-level primary in aggregate.py --decide remains the ratchet's rule)")

def main():
    a = sys.argv[1:]
    if a and a[0] == '--decide':
        alpha = float(a[a.index('--alpha')+1]) if '--alpha' in a else 0.10
        boot = int(a[a.index('--boot')+1]) if '--boot' in a else 5000
        return decide(a[1], a[2], alpha, boot)
    label = a[a.index('--label')+1] if '--label' in a else None
    reps = set(a[a.index('--rep')+1].split(',')) if '--rep' in a else None
    per, n_runs, n_units_runs = load_units(label, reps, include_holdout='--holdout' in a)
    rows = summarise(per)
    if not rows:
        print(f"no unit-level data ({n_runs} runs seen, {n_units_runs} with per-unit records). "
              f"Re-score older runs with harness/rescore.py --apply to backfill.")
        return
    total_units = sum(r['n_units'] for r in rows)
    print(f"repos={len(rows)}  units={total_units}  (from {n_units_runs}/{n_runs} runs carrying unit data)\n")
    print(f"{'repo':20}{'units':>6}{'outside':>9}{'ep_r':>7}{'ef_r':>7}{'singl':>7}")
    for r in rows:
        f = lambda v: f"{v:>7.3f}" if v is not None else f"{'-':>7}"
        print(f"{r['repo']:20}{r['n_units']:>6}{f(r['entered_from_outside'])[1:]:>9}"
              f"{f(r['entrypoint_r'])}{f(r['effects_r'])}{f(r['is_singleton'])}")
    for oc in OUTCOMES:
        vals = [r[oc] for r in rows if r[oc] is not None]
        if vals: print(f"\ncorpus {oc}: {mean(vals):.3f} (over {len(vals)} repos)")

if __name__ == '__main__': main()
