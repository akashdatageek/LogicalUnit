#!/usr/bin/env python3
"""Score one run. Usage: score.py <run_dir> <repo_dir>

Reports a VECTOR, not a composite. The decision rule lives in aggregate.py --decide.

Primary outcomes (pre-registered, see program.md):
  valid_nontrivial   bool   coverage>=0.95 and edge_resolution>=0.90 and not trivial and not budget_exhausted
                            budget_exhausted comes from the result's subtype/terminal_reason (error_max_turns,
                            error_max_budget_usd), NOT from num_turns, which also counts subagent turns.
  singleton_unit_frac       fraction of units owning <=1 file (over-split indicator; reported, audited in pilot P6)
  q_gain_dir         float  Q_llm - max(Q_one, Q_dir) on the import graph  (Louvain is a ceiling, NOT a baseline)
Secondary:
  q_cochange_gain    Q on the git co-change graph vs same baselines (orthogonal proxy)
  gold_ari, gold_nmi agreement with gold/<repo>.json if present (the real ground truth)
  entrypoint_p/r, effects_p/r   from harness/resolver.py (tree-sitter); contract_r = mean recall, gated in --decide
                                 precision is interpretable only if the resolver's ground truth is trusted (pilot P7)
  cost_usd, turns, input_tokens, output_tokens, lint_rounds, unpartitioned, n_units
"""
import json, math, re, subprocess, sys
from collections import defaultdict, Counter
from itertools import combinations
from pathlib import Path
from statistics import mean
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import resolver as RES
except Exception:
    RES = None

SRC_EXT = {'.py','.js','.ts','.tsx','.go','.rs','.java','.c','.cc','.cpp','.h','.hpp'}
SKIP = {'.git','node_modules','vendor','target','build','dist','__pycache__','.claude','examples','tests','test','docs'}

def src_files(repo):
    return sorted(str(p.relative_to(repo)) for p in repo.rglob('*')
                  if p.is_file() and p.suffix in SRC_EXT and not (set(p.parts) & SKIP))

# ---------- graphs ----------
def import_graph(repo, files):
    stems = defaultdict(list)
    for r in files: stems[Path(r).stem].append(r)
    g = defaultdict(set)
    for r in files:
        try: text = (repo/r).read_text(errors='ignore')
        except Exception: continue
        for line in text.splitlines():
            if not re.match(r'\s*(import|from|use|require|#include)\b', line) and 'require(' not in line: continue
            for tok in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', line):
                for tgt in stems.get(tok, []):
                    if tgt != r: g[r].add(tgt)
    return g

def cochange_graph(repo, files, max_commits=2000, max_files_per_commit=20):
    """Edge weight = number of commits in which both files changed. Large commits ignored (noise)."""
    fset = set(files); w = Counter()
    try:
        out = subprocess.check_output(['git','-C',str(repo),'log','--name-only','--pretty=format:%H',f'-n{max_commits}'],
                                      text=True, errors='ignore')
    except Exception:
        return None
    for block in out.split('\n\n'):
        lines = [l for l in block.strip().split('\n')[1:] if l in fset]
        if 2 <= len(lines) <= max_files_per_commit:
            for a, b in combinations(sorted(set(lines)), 2): w[(a,b)] += 1
    return w if w else None

def modularity(partition, g):
    """Newman Q, undirected unweighted; g: node -> set(neighbors) or dict (a,b)->weight."""
    und = defaultdict(lambda: defaultdict(float))
    if isinstance(g, Counter) or (g and isinstance(next(iter(g)), tuple)):
        for (a,b), wt in g.items(): und[a][b] += wt; und[b][a] += wt
    else:
        for a, bs in g.items():
            for b in bs: und[a][b] = 1.0; und[b][a] = 1.0
    m2 = sum(sum(v.values()) for v in und.values())
    if m2 == 0: return 0.0
    deg = {n: sum(v.values()) for n, v in und.items()}
    q = 0.0
    by_comm = defaultdict(list)
    for n in und: by_comm[partition.get(n)].append(n)
    for comm, nodes in by_comm.items():
        if comm is None: continue
        for a in nodes:
            for b in nodes:
                q += und[a].get(b, 0.0) - deg[a]*deg[b]/m2
    return q / m2

def label_propagation(g):
    """Community detection for the CEILING. Louvain via networkx when installed, label propagation otherwise."""
    try:
        import networkx as nx
        G = nx.Graph()
        # Sort before inserting. g's values are sets of str, and set iteration order varies
        # between processes under hash randomisation, which changed Louvain's tie-breaking and
        # made q_ceiling non-reproducible for identical input (observed 0.0969 vs 0.0934 on
        # the same run). Sorting makes the ceiling a function of the graph alone.
        for a in sorted(g):
            for b in sorted(g[a]): G.add_edge(a, b)
        if G.number_of_edges() == 0: return {}
        comms = nx.community.louvain_communities(G, seed=0)
        return {n: i for i, c in enumerate(comms) for n in c}
    except ImportError:
        pass
    und = defaultdict(set)
    for a, bs in g.items():
        for b in bs: und[a].add(b); und[b].add(a)
    lab = {n: n for n in und}
    for _ in range(30):
        changed = False
        for n in sorted(und):
            if not und[n]: continue
            c = Counter(lab[nb] for nb in und[n]); best = c.most_common(1)[0][0]
            if lab[n] != best: lab[n] = best; changed = True
        if not changed: break
    return lab

# ---------- gold agreement ----------
def contingency(p1, p2):
    files = sorted(set(p1) & set(p2))
    tab = Counter((p1[f], p2[f]) for f in files)
    return files, tab

def ari(p1, p2):
    files, tab = contingency(p1, p2); n = len(files)
    if n < 2: return None
    comb = lambda x: x*(x-1)/2
    a = Counter(); b = Counter()
    for (i,j), c in tab.items(): a[i] += c; b[j] += c
    sum_ij = sum(comb(c) for c in tab.values()); sum_a = sum(comb(c) for c in a.values()); sum_b = sum(comb(c) for c in b.values())
    exp = sum_a*sum_b/comb(n); mx = (sum_a+sum_b)/2
    return (sum_ij-exp)/(mx-exp) if mx != exp else 1.0

def nmi(p1, p2):
    files, tab = contingency(p1, p2); n = len(files)
    if n == 0: return None
    a = Counter(); b = Counter()
    for (i,j), c in tab.items(): a[i] += c; b[j] += c
    H = lambda cnt: -sum(c/n*math.log(c/n) for c in cnt.values() if c)
    I = sum(c/n*math.log((c/n)/((a[i]/n)*(b[j]/n))) for (i,j), c in tab.items() if c)
    d = (H(a)+H(b))/2
    return I/d if d else 1.0

# ---------- main ----------
def main(run_dir, repo_dir):
    run, repo = Path(run_dir), Path(repo_dir)
    m = json.loads((run/'manifest.json').read_text() or '{}')
    res = json.loads((run/'result.json').read_text() or '{}')
    meta = json.loads((run/'meta.json').read_text()) if (run/'meta.json').exists() else {}
    files = src_files(repo)
    units = m.get('units', [])
    owned = {f: u['name'] for u in units for f in u.get('files', [])}
    exc = [e['path'] for e in m.get('excluded', [])
           if isinstance(e, dict) and isinstance(e.get('path'), str)]
    excluded = set(exc)
    exc_dirs = tuple(q.rstrip('/') + '/' for q in exc)
    in_scope = [f for f in files if f not in excluded and not f.startswith(exc_dirs)]
    coverage = sum(1 for f in in_scope if f in owned) / max(1, len(in_scope))

    eps = {u['name']: {e['name'] for e in u.get('entrypoints', [])} for u in units}
    edges = [d for u in units for d in u.get('depends_on', [])]
    edge_res = (sum(1 for d in edges if d.get('entrypoint') in eps.get(d.get('unit'), set())) / len(edges)) if edges else 1.0

    n_units = len(units)
    trivial = n_units <= 1 or (len(owned) > 3 and n_units >= 0.8*len(owned))
    turns = res.get('num_turns')   # counts subagent turns too; never compare it to --max-turns
    subtype = str(res.get('subtype') or ''); term = str(res.get('terminal_reason') or '')
    budget_exhausted = subtype in ('error_max_turns', 'error_max_budget_usd') or 'max_turns' in term or 'budget' in term
    run_error = subtype.startswith('error_') or bool(res.get('is_error'))
    singleton_frac = (sum(1 for u in units if len(u.get('files', [])) <= 1) / len(units)) if units else None

    # static graph: tree-sitter resolver, cached per (repo, sha); regex fallback only if tree-sitter is missing
    graph = None
    cache = run.resolve().parents[1] / 'graph.json' if len(run.resolve().parts) >= 4 else None
    if RES is not None:
        if cache is not None and cache.exists(): graph = json.loads(cache.read_text())
        else:
            try:
                graph = RES.extract(repo)
                if cache is not None: cache.write_text(json.dumps(graph))
            except Exception as e:
                print(f"resolver failed: {e}", file=sys.stderr); graph = None
    if graph:
        g = defaultdict(set)
        for a, bs in graph['edges'].items(): g[a] |= set(bs)
        sc = RES.score(graph, m) if units else {'summary': {}, 'units': {}}
        contracts = sc['summary']; per_unit_contract = sc.get('units', {})
        graph_source = 'tree-sitter'
    else:
        g = import_graph(repo, files); contracts = {}; per_unit_contract = {}; graph_source = 'regex-fallback'
    q_llm = modularity(owned, g)
    q_one = modularity({f:'all' for f in files}, g)
    q_dir = modularity({f:str(Path(f).parent) for f in files}, g)
    q_ceiling = modularity(label_propagation(g), g)
    q_gain_dir = q_llm - max(q_one, q_dir)

    # co-change modularity (orthogonal proxy)
    cg = cochange_graph(repo, files)
    if cg:
        qc_llm = modularity(owned, cg); qc_dir = modularity({f:str(Path(f).parent) for f in files}, cg)
        qc_one = modularity({f:'all' for f in files}, cg)
        q_cochange_gain = qc_llm - max(qc_one, qc_dir)
    else:
        qc_llm = q_cochange_gain = None

    # gold agreement (the real ground truth, when we have it)
    HERE = Path(__file__).resolve().parent.parent
    repo_name = (meta.get('repo') or '').split('/')[-1] or (run.resolve().parts[-4] if len(run.resolve().parts) >= 4 else '')
    gold_path = HERE / 'gold' / f"{repo_name}.json"
    gold_ari = gold_nmi = None
    if repo_name and gold_path.exists():
        gold = {f: u['name'] for u in json.loads(gold_path.read_text()).get('units', []) for f in u.get('files', [])}
        gold_ari, gold_nmi = ari(owned, gold), nmi(owned, gold)

    usage = res.get('usage') or {}
    cost = res.get('total_cost_usd') or 0.0
    lint_rounds = (run/'lint.log').read_text().count('=== lint round') if (run/'lint.log').exists() else 0

    # per-unit records: the resolver already computes ground truth per unit; keep it instead of
    # collapsing to one summary per run. This is the sample harness/units.py analyses at unit level.
    unit_records = []
    for u in units:
        nm = u.get('name'); uf = u.get('files', []); c = per_unit_contract.get(nm, {})
        te = c.get('true_entrypoints')
        unit_records.append(dict(
            name=nm, kind=u.get('kind'), n_files=len(uf), is_singleton=len(uf) <= 1,
            entered_from_outside=(None if te is None else bool(te)),
            entrypoint_p=c.get('entrypoint_p'), entrypoint_r=c.get('entrypoint_r'),
            effects_p=c.get('effects_p'), effects_r=c.get('effects_r'),
            n_missed_entrypoints=(len(c['missed']) if 'missed' in c else None),
            n_undeclared_effects=(len(c['undeclared']) if 'undeclared' in c else None)))

    valid_nontrivial = coverage >= 0.95 and edge_res >= 0.90 and not trivial and not budget_exhausted
    out = dict(
        # primary
        valid_nontrivial=valid_nontrivial, q_gain_dir=round(q_gain_dir,4),
        # validity components
        coverage=round(coverage,3), edge_resolution=round(edge_res,3), trivial=trivial, budget_exhausted=budget_exhausted,
        run_error=run_error, result_subtype=subtype or None, singleton_unit_frac=None if singleton_frac is None else round(singleton_frac,3),
        n_units=n_units, unpartitioned=len(m.get('unpartitioned', [])), lint_rounds=lint_rounds,
        units=unit_records,
        # structure
        q_llm=round(q_llm,4), q_one=round(q_one,4), q_dir=round(q_dir,4), q_ceiling=round(q_ceiling,4),
        q_cochange_llm=None if qc_llm is None else round(qc_llm,4),
        q_cochange_gain=None if q_cochange_gain is None else round(q_cochange_gain,4),
        gold_ari=None if gold_ari is None else round(gold_ari,4), gold_nmi=None if gold_nmi is None else round(gold_nmi,4),
        # contracts (invariants 2 and 4), from the static resolver
        entrypoint_p=contracts.get('entrypoint_p'), entrypoint_r=contracts.get('entrypoint_r'),
        effects_p=contracts.get('effects_p'), effects_r=contracts.get('effects_r'),
        contract_r=(None if contracts.get('entrypoint_r') is None and contracts.get('effects_r') is None
                    else round(mean([v for v in (contracts.get('entrypoint_r'), contracts.get('effects_r')) if v is not None]), 4)),
        units_with_missed_entrypoints=contracts.get('units_with_missed_entrypoints'),
        units_with_undeclared_effects=contracts.get('units_with_undeclared_effects'),
        graph_source=graph_source,
        # cost
        cost_usd=cost, turns=turns, duration_ms=res.get('duration_ms'),
        input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'),
    )
    print(json.dumps(out, indent=2))

if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
