#!/usr/bin/env python3
"""Sample-size planning for the ratchet (paired design: same repos before/after an edit).

  power.py [--sd 0.02] [--tau 0.03] [--delta 0.03] [--alpha 0.10]     table: N repos x replicates -> power
  power.py --min-n [--reps 3] ...                                      smallest N_dev with power >= 0.80 (Phase-2 gate)
  power.py --from-runs [--label sha] [--before A --after B]            estimate sd (and tau if two labels) from runs

Variance model for the per-repo delta of q_gain_dir:
    var(delta_i) = tau^2 + 2 * sd_within^2 / reps
  tau        sd of the TRUE effect across repos (an edit helps some repos, hurts others). This is the
             term that replicates cannot reduce; only more repos can. Default tau = delta (a realistic,
             mildly pessimistic assumption: effects are as variable as they are large).
  sd_within  run-to-run sd within a repo (from the pilot).
Power = P(z > z_alpha - delta / (sd_delta / sqrt(N))), one-sided, normal approximation.
"""
import math, sys
from statistics import NormalDist, mean, pstdev, variance
from pathlib import Path

Z = NormalDist()

def sd_delta(reps, sd_within, tau): return math.sqrt(tau**2 + 2 * sd_within**2 / reps)

def power(N, reps, sd_within, tau, delta, alpha):
    se = sd_delta(reps, sd_within, tau) / math.sqrt(N)
    return 1 - Z.cdf(Z.inv_cdf(1 - alpha) - delta / se)

def min_n(reps, sd_within, tau, delta, alpha, target=0.80):
    for N in range(3, 1000):
        if power(N, reps, sd_within, tau, delta, alpha) >= target: return N
    return None

def from_runs(label, before, after):
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import aggregate as agg
    per = agg.load(label, None, include_holdout=True)
    w = [pstdev([r['s']['q_gain_dir'] for r in runs]) for runs in per.values() if len(runs) >= 2]
    sd = mean(w) if w else None
    tau = None
    if before and after:
        A, B = agg.load(before, None, True), agg.load(after, None, True)
        common = sorted(set(A) & set(B))
        if len(common) >= 4:
            d = [mean(r['s']['q_gain_dir'] for r in B[k]) - mean(r['s']['q_gain_dir'] for r in A[k]) for k in common]
            reps = mean(len(A[k]) for k in common)
            tau2 = variance(d) - 2 * (sd or 0)**2 / reps
            tau = math.sqrt(max(tau2, 0.0))
    return sd, tau, len(w)

def main():
    a = sys.argv[1:]
    g = lambda k, d: type(d)(a[a.index(k)+1]) if k in a else d
    delta, alpha, reps = g('--delta', 0.03), g('--alpha', 0.10), g('--reps', 3)
    sd, tau = g('--sd', 0.02), None
    if '--from-runs' in a:
        sd_e, tau_e, n = from_runs(a[a.index('--label')+1] if '--label' in a else None,
                                   a[a.index('--before')+1] if '--before' in a else None,
                                   a[a.index('--after')+1] if '--after' in a else None)
        if sd_e is None: print('no runs with >=2 replicates'); return
        sd = sd_e; tau = tau_e
        print(f"from runs: sd_within={sd:.4f} ({n} repos)" + (f"  tau={tau:.4f}" if tau is not None else "  tau: need --before/--after"))
    if '--tau' in a: tau = float(a[a.index('--tau')+1])
    if tau is None: tau = delta
    if '--min-n' in a:
        n = min_n(reps, sd, tau, delta, alpha); print(n if n else 'inf'); return
    print(f"power to detect delta={delta} in q_gain_dir | sd_within={sd:.3f}  tau={tau:.3f}  alpha={alpha} one-sided\n")
    Ns = [7, 10, 20, 30, 50, 70, 100]; R = [1, 2, 3, 5]
    print(f"{'N_dev':>6} | " + ' '.join(f"reps={r:<3}" for r in R))
    for N in Ns:
        print(f"{N:>6} | " + ' '.join(f"{power(N, r, sd, tau, delta, alpha):>6.2f}  " for r in R))
    print(f"\nmin N_dev for 80% power at reps={reps}: {min_n(reps, sd, tau, delta, alpha)}")
    print("Replicates shrink run-to-run noise; only repos shrink effect heterogeneity (tau). Past ~3 reps, add repos.")

if __name__ == '__main__': main()
