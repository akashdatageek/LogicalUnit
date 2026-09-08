#!/usr/bin/env python3
"""Pilot go/no-go report. Run after 10 repos x 6 replicates on the baseline skill.
  pilot_check.py [--label <sha>] [--human notes/human_rank.txt] [--budget 500]

human_rank.txt: one repo name per line, best decomposition first (ranked by eye, before
looking at scores). Optional; enables P3.
"""
import json, math, random, sys
from itertools import combinations
from pathlib import Path
from statistics import mean, pvariance, pstdev

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / 'harness'))
import aggregate as agg  # reuse loaders and decide()

METRICS = ['q_gain_dir', 'coverage', 'edge_resolution', 'n_units', 'q_cochange_gain']

def icc1(groups):
    """ICC(1) one-way random effects. groups: list of lists of values (one list per repo)."""
    groups = [g for g in groups if len(g) >= 2]
    k = len(groups)
    if k < 2: return None, None
    n = mean(len(g) for g in groups)
    grand = mean(v for g in groups for v in g)
    msb = sum(len(g) * (mean(g) - grand) ** 2 for g in groups) / (k - 1)
    msw = sum((v - mean(g)) ** 2 for g in groups for v in g) / sum(len(g) - 1 for g in groups)
    icc = (msb - msw) / (msb + (n - 1) * msw) if (msb + (n - 1) * msw) else None
    return icc, (msb / msw if msw else float('inf'))

def spearman(a, b):
    def rank(x):
        s = sorted(range(len(x)), key=lambda i: x[i]); r = [0] * len(x)
        for i, idx in enumerate(s): r[idx] = i
        return r
    ra, rb = rank(a), rank(b); n = len(a)
    if n < 3: return None
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    return 1 - 6 * d2 / (n * (n * n - 1))

def aa_test(per, alpha, boot=3000):
    """Every 3-vs-3 split of six replicates; returns KEEP rate."""
    repos = sorted(per)
    reps = sorted({r['rep'] for runs in per.values() for r in runs})
    if len(reps) < 6: return None, 0
    keeps = 0; splits = list(combinations(reps, 3)); splits = [s for s in splits if reps[0] in s]  # 10 unique splits
    rng = random.Random(0)
    for A in splits:
        B = tuple(r for r in reps if r not in A)
        ga = {k: mean(r['s']['q_gain_dir'] for r in per[k] if r['rep'] in A) for k in repos}
        gb = {k: mean(r['s']['q_gain_dir'] for r in per[k] if r['rep'] in B) for k in repos}
        deltas = [gb[k] - ga[k] for k in repos]
        means = sorted(mean(rng.choice(deltas) for _ in deltas) for _ in range(boot))
        lo = means[int(alpha / 2 * boot)]
        keeps += lo > 0
    return keeps / len(splits), len(splits)

def replicates_needed(within_sd, n_repos=70, delta=0.03, power=0.8, alpha=0.10):
    """Paired design: SE of mean delta = sd_delta / sqrt(n_repos); sd_delta ≈ within_sd*sqrt(2/reps)."""
    z = 1.645 + 0.84  # one-sided alpha .05-ish + 80% power
    for reps in range(1, 21):
        se = within_sd * math.sqrt(2 / reps) / math.sqrt(n_repos)
        if delta / se >= z: return max(2, reps)
    return 21

def main():
    a = sys.argv[1:]
    label = a[a.index('--label') + 1] if '--label' in a else None
    budget = float(a[a.index('--budget') + 1]) if '--budget' in a else None
    human = Path(a[a.index('--human') + 1]) if '--human' in a else HERE / 'notes' / 'human_rank.txt'
    per = agg.load(label, None, include_holdout=True)
    if not per: print('no runs'); return
    all_runs = [r for runs in per.values() for r in runs]
    N = len(all_runs)
    verdicts = {}

    print(f"PILOT REPORT  label={label or 'all'}  repos={len(per)}  runs={N}\n")

    # P1 reliability
    harness_fail = sum(1 for r in all_runs if r['meta'].get('exit', 0) != 0 and not r['part'])
    has_manifest = sum(1 for r in all_runs if r['part'])
    exhausted = sum(1 for r in all_runs if r['s'].get('budget_exhausted'))
    lint_ok = sum(1 for r in all_runs if not r['part'] or r['s'].get('lint_rounds', 0) >= 1)
    p1 = harness_fail / N < 0.05 and has_manifest / N > 0.9 and exhausted / N < 0.2 and lint_ok == N
    verdicts['P1 reliability'] = p1
    print(f"P1  harness_fail {harness_fail/N:.0%}  manifest {has_manifest/N:.0%}  exhausted {exhausted/N:.0%}  lint_fired {lint_ok}/{N}  -> {'PASS' if p1 else 'FAIL'}")

    # P2 discrimination
    print("P2  metric            ICC(1)   var_ratio")
    p2 = None
    for m in METRICS:
        groups = [[r['s'][m] for r in runs if r['s'].get(m) is not None] for runs in per.values()]
        groups = [g for g in groups if g]
        if not groups: print(f"    {m:18} n/a"); continue
        icc, vr = icc1(groups)
        flag = ''
        if m == 'q_gain_dir':
            p2 = icc is not None and icc >= 0.6
            flag = '  <- PRIMARY: ' + ('PASS' if p2 else ('MARGINAL' if icc and icc >= 0.4 else 'FAIL'))
        print(f"    {m:18} {icc if icc is None else round(icc,3)!s:>7}  {vr if vr is None else round(vr,2)!s:>9}{flag}")
    verdicts['P2 discrimination'] = p2

    # P3 human agreement
    rows = {r['repo']: r for r in agg.summarise(per)}
    if human.exists():
        order = [l.strip() for l in human.read_text().splitlines() if l.strip() and not l.startswith('#')]
        order = [o for o in order if o in rows]
        hr = list(range(len(order)))
        rho_g = spearman(hr, [rows[o]['gain'] for o in order])
        cc = [rows[o]['cochange'] for o in order]
        rho_c = spearman(hr, cc) if all(c is not None for c in cc) else None
        rho_gc = spearman([rows[o]['gain'] for o in order], cc) if rho_c is not None else None
        p3 = rho_g is not None and -rho_g >= 0.5   # human rank 0 = best, gain high = best -> negative rho expected
        verdicts['P3 human agreement'] = p3
        print(f"P3  rho(human, q_gain_dir) {(-rho_g if rho_g is not None else float('nan')):+.2f}  rho(human, cochange) {(-rho_c if rho_c is not None else float('nan')):+.2f}  rho(gain, cochange) {(rho_gc if rho_gc is not None else float('nan')):+.2f}  -> {'PASS' if p3 else 'FAIL'}")
    else:
        verdicts['P3 human agreement'] = None
        print(f"P3  no {human.relative_to(HERE)} — rank the 10 repos by eye first (best first, one per line)")

    # P4 A/A
    for alpha, limit in [(0.10, 0.10), (0.05, 0.0)]:
        rate, n = aa_test(per, alpha)
        if rate is None: print("P4  need 6 replicates per repo for the A/A test"); verdicts['P4 A/A'] = None; break
        ok = rate <= limit + 1e-9
        verdicts['P4 A/A'] = verdicts.get('P4 A/A', True) and ok
        print(f"P4  A/A KEEP rate at alpha={alpha}: {rate:.0%} of {n} splits (limit {limit:.0%})  -> {'PASS' if ok else 'FAIL'}")

    # P5 stability & replicates needed
    within = [pstdev([r['s']['q_gain_dir'] for r in runs]) for runs in per.values() if len(runs) >= 2]
    jac = [x['jaccard'] for x in rows.values() if x['jaccard'] is not None]
    if within:
        sd = mean(within); need = replicates_needed(sd)
        p5 = need <= 5
        verdicts['P5 replicates'] = p5
        print(f"P5  within-repo sd(q_gain_dir) {sd:.4f}  mean jaccard {mean(jac) if jac else float('nan'):.2f}  replicates needed @N=70, delta=0.03 -> {need}  {'PASS' if p5 else 'FAIL'}")
    else:
        need = None; verdicts['P5 replicates'] = None

    # P8 cost projection
    cost = mean(r['s'].get('cost_usd') or 0 for r in all_runs)
    reps = need or 3
    proj = cost * 100 * reps * 5   # x5: baseline + ~4 ratchet reruns of the dev set
    print(f"P8  mean cost/run ${cost:.2f}  projected 100-repo campaign (x{reps} reps, x5 reruns) ≈ ${proj:,.0f}" + (f"  budget ${budget:,.0f} -> {'OK' if proj <= budget else 'OVER'}" if budget else ''))

    print("\nGO/NO-GO")
    for k, v in verdicts.items():
        print(f"  {k:22} {'PASS' if v else ('FAIL' if v is False else 'not run')}")
    go = all(v for v in verdicts.values() if v is not None) and verdicts.get('P3 human agreement') is not None
    print(f"\n  {'GO to 100' if go else 'NO-GO — fix the failed checks, re-pilot those only'}")
    print("  Manual checks still required: P6 (threshold audit), P7 (lint stub vs ent ci). See PILOT.md.")

if __name__ == '__main__': main()
