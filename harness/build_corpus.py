#!/usr/bin/env python3
"""build_corpus.py — stratified random sample of repos from a defined frame, pinned to a sha.

  build_corpus.py --n 40 --seed 7 [--strata famous,lowvis,postcutoff] [--cutoff 2026-01-01] [--out harness/corpus.txt]
                  [--languages python,typescript,go,rust,java,cpp] [--token $GITHUB_TOKEN] [--dry-run]

Frame (recorded in corpus.meta.json so it can be cited):
  GitHub search API, snapshot date = now, filters per stratum below, fork:false archived:false,
  size 500KB–60MB (LOC proxy; real LOC checked after clone), pushed within the last 2 years.

Strata:
  famous       stars:>5000
  lowvis       stars:20..200  created:<(now-1y)          contamination-resistant
  postcutoff   created:>=CUTOFF                          contamination-proof (only if --cutoff given)
  natpart      famous + a workspace/packages/plugins layout hint in the description (weak; verify manually)
Sampling: for each (stratum, language) cell, fetch up to 3 pages (≤90 candidates, sorted by 'updated'
for spread rather than by stars), then draw uniformly at random with the given seed. This is
random WITHIN the frame; it is not a random sample of GitHub.

Rate limits: unauthenticated search = 10 req/min. Pass --token for 30/min. The script sleeps as needed.
Pinning uses `git ls-remote` (no API cost).
"""
import json, random, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = 'https://api.github.com/search/repositories'
LANG_Q = {'python':'Python','typescript':'TypeScript','javascript':'JavaScript','go':'Go','rust':'Rust','java':'Java','cpp':'C++','c':'C'}

def gh(q, page, token):
    url = API + '?' + urllib.parse.urlencode({'q': q, 'sort': 'updated', 'order': 'desc', 'per_page': 30, 'page': page})
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'lu-bench'})
    if token: req.add_header('Authorization', f'Bearer {token}')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                remaining = int(r.headers.get('X-RateLimit-Remaining', '1'))
                data = json.load(r)
                if remaining <= 1:
                    reset = int(r.headers.get('X-RateLimit-Reset', time.time() + 60)); time.sleep(max(1, reset - time.time() + 1))
                return data.get('items', [])
        except urllib.error.HTTPError as e:
            if e.code in (403, 429): time.sleep(65); continue
            raise
    return []

def pin(full_name):
    try:
        out = subprocess.check_output(['git', 'ls-remote', f'https://github.com/{full_name}', 'HEAD'], text=True, timeout=60)
        return out.split()[0]
    except Exception:
        return None

def strata_queries(cutoff):
    now = datetime.now(timezone.utc); y1 = (now - timedelta(days=365)).date().isoformat(); y2 = (now - timedelta(days=730)).date().isoformat()
    base = f'fork:false archived:false size:500..60000 pushed:>{y2}'
    q = {
        'famous':  f'{base} stars:>5000',
        'lowvis':  f'{base} stars:20..200 created:<{y1}',
        'natpart': f'{base} stars:>5000 monorepo OR workspace OR plugins in:description',
    }
    if cutoff: q['postcutoff'] = f'{base} stars:>5 created:>={cutoff}'
    return q

def main():
    a = sys.argv[1:]
    g = lambda k, d: a[a.index(k)+1] if k in a else d
    n_total = int(g('--n', 40)); seed = int(g('--seed', 0)); cutoff = g('--cutoff', None)
    strata = g('--strata', 'famous,lowvis' + (',postcutoff' if cutoff else '')).split(',')
    langs = g('--languages', 'python,typescript,go,rust,java,cpp').split(',')
    token = g('--token', None); out = Path(g('--out', 'harness/corpus.txt')); dry = '--dry-run' in a
    rng = random.Random(seed)
    queries = strata_queries(cutoff)
    cells = [(s, l) for s in strata for l in langs]
    per_cell = max(1, n_total // len(cells))
    chosen, meta = [], dict(snapshot=datetime.now(timezone.utc).isoformat(), seed=seed, n_requested=n_total, cells={})
    for s, l in cells:
        q = f"{queries[s]} language:{LANG_Q[l]}"
        cands = []
        for page in (1, 2, 3):
            items = gh(q, page, token); cands += items
            if len(items) < 30: break
            time.sleep(6.5 if not token else 2.1)
        names = sorted({c['full_name'] for c in cands})
        pick = rng.sample(names, min(per_cell, len(names)))
        meta['cells'][f'{s}/{l}'] = dict(query=q, candidates=len(names), picked=pick)
        for p in pick: chosen.append((s, l, p))
        print(f"{s:10} {l:10} candidates={len(names):3}  picked={pick}", file=sys.stderr)
    if dry:
        print(json.dumps(meta, indent=2)); return
    lines = ['# owner/name  sha  stratum  language   (built by build_corpus.py; see corpus.meta.json)']
    existing = out.read_text().splitlines() if out.exists() else []
    lines += [l for l in existing if l.strip() and not l.startswith('#')]
    for s, l, p in chosen:
        sha = pin(p)
        if not sha: print(f"could not pin {p}; skipped", file=sys.stderr); continue
        lines.append(f"{p:40} {sha}  {s}  {l}")
    out.write_text('\n'.join(lines) + '\n')
    (out.parent / 'corpus.meta.json').write_text(json.dumps(meta, indent=2))
    print(f"wrote {out} ({len(lines)-1} repos) and corpus.meta.json", file=sys.stderr)

if __name__ == '__main__': main()
