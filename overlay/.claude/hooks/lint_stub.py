#!/usr/bin/env python3
"""Stand-in for `ent ci --lint` until the CLI is wired. Invariants 1 and 3 structurally;
2 and 4 via the tree-sitter resolver when present (run_one.sh copies it next to this file),
regex fallback otherwise. Exit 0 = no blocking errors."""
import json, re, sys
from pathlib import Path

SRC_EXT = {'.py','.js','.ts','.tsx','.go','.rs','.java','.c','.cc','.cpp','.h','.hpp'}
SKIP_DIRS = {'.git','node_modules','vendor','target','build','dist','__pycache__','.claude','examples'}
EFFECT_PATTERNS = {
  'network':    r'\b(requests|httpx|urllib|socket|fetch\(|axios|net/http|reqwest|HttpClient)\b',
  'filesystem': r'\b(open\(|os\.path|pathlib|fs\.|std::fs|ioutil|java\.io\.File)\b',
  'subprocess': r'\b(subprocess|child_process|os/exec|std::process|ProcessBuilder)\b',
  'env':        r'\b(os\.environ|process\.env|os\.Getenv|std::env|System\.getenv)\b',
  'clock':      r'\b(time\.time|Date\.now|time\.Now|Instant::now|currentTimeMillis)\b',
  'random':     r'\b(random\.|Math\.random|rand\.|rand::)\b',
}

def main(manifest_path, repo):
    m = json.load(open(manifest_path)); repo = Path(repo); errors = []
    units = {u['name']: u for u in m.get('units', [])}

    # I1 partition
    owned = {}
    for u in m.get('units', []):
        for f in u.get('files', []):
            if f in owned: errors.append(f"I1 '{f}' owned by both '{owned[f]}' and '{u['name']}'")
            owned[f] = u['name']
    excluded = {e['path'] for e in m.get('excluded', [])}
    unpart   = {e['path'] for e in m.get('unpartitioned', [])}
    all_src  = {str(p.relative_to(repo)) for p in repo.rglob('*')
                if p.is_file() and p.suffix in SRC_EXT and not (set(p.parts) & SKIP_DIRS)}
    missing = sorted(all_src - set(owned) - excluded - unpart)
    errors += [f"I1 '{f}' in no unit, not excluded, not unpartitioned" for f in missing[:50]]
    if len(missing) > 50: errors.append(f"I1 ...and {len(missing)-50} more unassigned files")

    # I2 entrypoint locations live inside the unit
    for u in m.get('units', []):
        for ep in u.get('entrypoints', []):
            f = ep.get('location','').split(':')[0]
            if f not in u.get('files', []):
                errors.append(f"I2 '{u['name']}'.{ep.get('name')} location '{f}' not in unit files")

    # I3 edges target listed entrypoints
    for u in m.get('units', []):
        for d in u.get('depends_on', []):
            tgt = units.get(d.get('unit'))
            if not tgt: errors.append(f"I3 '{u['name']}' depends on unknown unit '{d.get('unit')}'"); continue
            if d.get('entrypoint') not in {e['name'] for e in tgt.get('entrypoints', [])}:
                errors.append(f"I3 '{u['name']}' -> '{d.get('unit')}.{d.get('entrypoint')}' is not a listed entrypoint")

    # I4 heuristic: detected I/O covered by declared effects
    for u in m.get('units', []):
        declared = {e['kind'] for e in u.get('effects', [])}
        for f in u.get('files', []):
            try: text = (repo/f).read_text(errors='ignore')
            except Exception: continue
            for kind, pat in EFFECT_PATTERNS.items():
                if kind not in declared and re.search(pat, text):
                    errors.append(f"I4 '{u['name']}' file '{f}' shows '{kind}' effect not declared"); break

    print(*errors, sep='\n') if errors else None
    print(f"{len(errors)} blocking error(s)")
    sys.exit(0 if not errors else 1)

if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
