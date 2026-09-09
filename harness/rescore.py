#!/usr/bin/env python3
"""rescore.py — re-score existing runs in place after a scorer change.

  rescore.py                     dry run: show what would change
  rescore.py --apply             rewrite score.json for every run
  rescore.py --apply --label X   only runs under label X

Why this exists
---------------
When a scorer bug is fixed the RUNS are still good: manifest.json, result.json and meta.json
are on disk and cost real money. Re-running them costs full price and breaks the rule that a
(repo, label, rep) slot is never rerun. Re-scoring is free and preserves provenance.

Finding the checkout is the fiddly part. run_one.sh now checks out per run
(/work/<name>-<sha7>-<rep>), older runs used a shared /work/<name>, and either may be gone.
This resolves in that order and clones at the pinned sha as a last resort.

Never deletes or moves a run directory. Only score.json is rewritten.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def corpus_sha():
    m = {}
    c = HERE / 'corpus.txt'
    if c.exists():
        for line in c.read_text().splitlines():
            if not line.strip() or line.startswith('#'): continue
            p = line.split()
            if len(p) >= 2 and p[1] != 'PIN_ME':
                m[p[0].split('/')[-1]] = (p[0], p[1])
    return m

def find_checkout(name, sha, rep, corpus):
    """Return a path whose HEAD is sha, cloning if we must. None if unavailable."""
    for cand in (Path(f"/work/{name}-{sha[:7]}-{rep}"), Path(f"/work/{name}")):
        if (cand / '.git').is_dir():
            try:
                head = subprocess.check_output(['git', '-C', str(cand), 'rev-parse', 'HEAD'],
                                               text=True).strip()
                if head == sha:
                    return cand
            except subprocess.CalledProcessError:
                pass
    full = corpus.get(name, (None, None))[0]
    if not full:
        return None
    dest = Path(f"/work/{name}-{sha[:7]}-rescore")
    try:
        if not (dest / '.git').is_dir():
            subprocess.check_call(['git', 'clone', '--quiet',
                                   f"https://github.com/{full}", str(dest)])
        subprocess.check_call(['git', '-C', str(dest), 'checkout', '--quiet', '--force', sha])
        return dest
    except subprocess.CalledProcessError:
        return None

def main(argv):
    apply = '--apply' in argv
    label = argv[argv.index('--label') + 1] if '--label' in argv else None
    corpus = corpus_sha()
    runs = sorted((ROOT / 'runs').glob('*/*/*/*/manifest.json'))
    if label:
        runs = [r for r in runs if r.parent.parts[-2] == label]
    changed = unchanged = skipped = 0
    print(f"{'run':44}  changes")
    for man in runs:
        run = man.parent
        name, sha, lab, rep = run.parts[-4:]
        old = {}
        sp = run / 'score.json'
        if sp.exists() and sp.stat().st_size:
            try: old = json.loads(sp.read_text())
            except Exception: old = {}
        repo_dir = find_checkout(name, sha, rep, corpus)
        short = f"{name}/{lab}/{rep}"
        if repo_dir is None:
            print(f"{short:44}  SKIP no checkout for {sha[:7]}")
            skipped += 1; continue
        p = subprocess.run([sys.executable, str(HERE / 'score.py'), str(run), str(repo_dir)],
                           capture_output=True, text=True)
        if p.returncode != 0 or not p.stdout.strip():
            print(f"{short:44}  SKIP scorer failed: {p.stderr.strip()[-90:]}")
            skipped += 1; continue
        new = json.loads(p.stdout)
        # compare every field, not just the headline one: an exclusion fix moves coverage and
        # valid_nontrivial while leaving q_gain_dir untouched.
        diffs = [k for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
        if apply:
            sp.write_text(p.stdout)
        if diffs:
            changed += 1
            shown = ', '.join(f"{k} {old.get(k)}->{new.get(k)}" for k in diffs[:4])
            more = f" (+{len(diffs)-4} more)" if len(diffs) > 4 else ""
            print(f"{short:44}  {shown}{more}")
        else:
            unchanged += 1
    print(f"\n{changed} changed, {unchanged} unchanged, {skipped} skipped"
          f"{'' if apply else '   (dry run — pass --apply to write)'}")
    if apply and changed:
        print("Record which scorer sha produced these numbers before appending to results.tsv.")
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
