#!/usr/bin/env python3
"""headroom.py — pre-flight a candidate repo BEFORE it costs a model call.

  headroom.py <repo_dir> [<repo_dir> ...]        table, one row per repo
  headroom.py --corpus                            every pinned row of harness/corpus.txt (needs clones in /work)
  headroom.py --json <repo_dir>                   machine-readable

Why this exists
---------------
q_gain_dir = Q_llm - max(Q_one, Q_dir).  Q_one is 0 by construction.  So on a repo whose
source is one flat package, Q_dir is ~0 too and gain collapses to raw modularity, which is
negative for any partition that cuts a dense import graph.  Such a repo CANNOT show a
positive gain no matter how good the decomposition is.

Every number below is static analysis over the same tree-sitter graph score.py uses.  No
model call, no cost.  Run it on candidates before admitting them to the corpus.

Columns
  files      in-scope source files (same rule as score.py)
  q_dir      modularity of the per-directory partition = the null the model must beat
  ceiling    Louvain modularity = the practical maximum on this graph
  headroom   ceiling - max(0, q_dir); how much room a decomposition can actually win
  hub%       share of import edges touching the top 5% most-connected files.  A high value
             means cross-cutting code that exclusive file ownership will strand in one unit.
  verdict    MEASURABLE / THIN / FLAT  (see --help thresholds)

Thresholds (tune once, then pre-register):
  FLAT        q_dir < 0.02   -> the directory baseline is degenerate; gain ~= raw Q; expect negatives
  THIN        headroom < 0.10 -> real but small room; keep as a control, not as evidence
  MEASURABLE  otherwise
"""
import json, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score as S                      # reuse src_files / modularity / label_propagation
try:
    import resolver as RES
except Exception:
    RES = None

FLAT_QDIR = 0.02
THIN_HEADROOM = 0.10

def graph_for(repo: Path):
    """tree-sitter graph when available, regex import graph otherwise."""
    files = S.src_files(repo)
    if RES is not None:
        try:
            g = defaultdict(set)
            for a, bs in RES.extract(repo)['edges'].items():
                g[a] |= set(bs)
            return files, g, 'tree-sitter'
        except Exception as e:
            print(f"  resolver failed on {repo}: {e}", file=sys.stderr)
    return files, S.import_graph(repo, files), 'regex-fallback'

def hub_share(g):
    """fraction of edge endpoints landing on the top 5% most-connected files."""
    deg = defaultdict(int)
    for a, bs in g.items():
        for b in bs:
            deg[a] += 1; deg[b] += 1
    if not deg: return 0.0
    ranked = sorted(deg.values(), reverse=True)
    k = max(1, len(ranked) // 20)
    return sum(ranked[:k]) / sum(ranked)

def assess(repo_dir):
    repo = Path(repo_dir)
    files, g, src = graph_for(repo)
    q_dir = S.modularity({f: str(Path(f).parent) for f in files}, g)
    ceiling = S.modularity(S.label_propagation(g), g)
    head = ceiling - max(0.0, q_dir)
    if q_dir < FLAT_QDIR:      verdict = 'FLAT'
    elif head < THIN_HEADROOM: verdict = 'THIN'
    else:                      verdict = 'MEASURABLE'
    return dict(repo=repo.name, files=len(files), q_dir=round(q_dir, 4),
                ceiling=round(ceiling, 4), headroom=round(head, 4),
                hub_share=round(hub_share(g), 3), graph_source=src, verdict=verdict)

def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__); return 0
    as_json = '--json' in argv
    argv = [a for a in argv if a != '--json']
    if argv and argv[0] == '--corpus':
        c = HERE.parent / 'harness' / 'corpus.txt'
        targets = []
        for line in c.read_text().splitlines():
            if not line.strip() or line.startswith('#'): continue
            p = line.split()
            if len(p) < 2 or p[1] == 'PIN_ME': continue
            targets.append(Path('/work') / p[0].split('/')[-1])
        targets = [t for t in targets if t.is_dir()]
    else:
        targets = [Path(a) for a in argv]
    rows = [assess(t) for t in targets]
    if as_json:
        print(json.dumps(rows, indent=1)); return 0
    print(f"{'repo':14}{'files':>7}{'q_dir':>9}{'ceiling':>9}{'headroom':>10}{'hub%':>7}  verdict")
    for r in rows:
        print(f"{r['repo']:14}{r['files']:>7}{r['q_dir']:>9.4f}{r['ceiling']:>9.4f}"
              f"{r['headroom']:>10.4f}{r['hub_share']*100:>6.0f}%  {r['verdict']}")
    n_ok = sum(1 for r in rows if r['verdict'] == 'MEASURABLE')
    print(f"\n{n_ok}/{len(rows)} repos can show a positive q_gain_dir. "
          f"FLAT repos are controls, not evidence.")
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
