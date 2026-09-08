#!/usr/bin/env python3
"""resolver.py — AST-based static facts for scoring invariants 2 (entrypoints) and 4 (effects).

  resolver.py extract <repo_dir> > graph.json
  resolver.py score   <graph.json> <manifest.json>      -> entrypoint/effects P/R per unit + summary

What it computes (tree-sitter, six languages; no regex over source text):
  defs      per file: symbols defined at top level (or class members) with kind, line, exported flag
  imports   per file: import targets, resolved to repo files where possible
  refs      per file: identifiers used that resolve to a def in ANOTHER file
  effects   per file: effect kinds, from (a) imports of known I/O modules and (b) calls to known I/O functions
  edges     file -> file (import or resolved reference) — feeds modularity in score.py

Ground truth for invariant 2, per unit U:
  true_entrypoints(U) = defs in U's files that are referenced from a file outside U
  precision = |listed ∩ true| / |listed|,  recall = |listed ∩ true| / |true|
Ground truth for invariant 4, per unit U:
  detected(U) = union of effect kinds over U's files;  P/R of declared vs detected

This is precise on definitions and imports, and heuristic on cross-file identifier
resolution (name-based, disambiguated by import linkage). Treat the numbers as a
static-analysis approximation, not runtime truth; ent's runtime span evidence
supersedes it when available.
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path

from tree_sitter_language_pack import get_parser

LANG_BY_EXT = {'.py':'python', '.js':'javascript', '.mjs':'javascript', '.cjs':'javascript', '.jsx':'javascript',
               '.ts':'typescript', '.tsx':'typescript', '.go':'go', '.rs':'rust', '.java':'java',
               '.c':'c', '.h':'c', '.cc':'cpp', '.cpp':'cpp', '.hpp':'cpp', '.hh':'cpp'}
SKIP_DIRS = {'.git','node_modules','vendor','target','build','dist','__pycache__','.claude','examples',
             'tests','test','docs','doc','third_party','testdata','fixtures'}

# ---- per-language node tables --------------------------------------------------------------
DEF_NODES = {
  'python':     {'function_definition':'function', 'class_definition':'class'},
  'javascript': {'function_declaration':'function', 'class_declaration':'class', 'method_definition':'method',
                 'lexical_declaration':'const', 'variable_declaration':'const'},
  'typescript': {'function_declaration':'function', 'class_declaration':'class', 'method_definition':'method',
                 'lexical_declaration':'const', 'interface_declaration':'type', 'type_alias_declaration':'type',
                 'enum_declaration':'type', 'abstract_class_declaration':'class'},
  'go':         {'function_declaration':'function', 'method_declaration':'method', 'type_spec':'type'},
  'rust':       {'function_item':'function', 'struct_item':'type', 'enum_item':'type', 'trait_item':'type',
                 'type_item':'type', 'const_item':'constant', 'static_item':'constant', 'mod_item':'module'},
  'java':       {'method_declaration':'method', 'class_declaration':'class', 'interface_declaration':'type',
                 'enum_declaration':'type', 'record_declaration':'type', 'constructor_declaration':'method'},
  'c':          {'function_definition':'function', 'type_definition':'type', 'struct_specifier':'type'},
  'cpp':        {'function_definition':'function', 'class_specifier':'class', 'struct_specifier':'type',
                 'type_definition':'type', 'namespace_definition':'module'},
}
IMPORT_NODES = {
  'python': {'import_statement','import_from_statement'}, 'javascript': {'import_statement'}, 'typescript': {'import_statement'},
  'go': {'import_spec'}, 'rust': {'use_declaration'}, 'java': {'import_declaration'}, 'c': {'preproc_include'}, 'cpp': {'preproc_include'},
}
CALL_NODES = {'python':'call','javascript':'call_expression','typescript':'call_expression','go':'call_expression',
              'rust':'call_expression','java':'method_invocation','c':'call_expression','cpp':'call_expression'}

# ---- effects tables: imported module -> kind ; called name -> kind ------------------------------
EFFECT_IMPORTS = {
  'python': {'requests':'network','httpx':'network','urllib.request':'network','urllib3':'network','socket':'network','aiohttp':'network','ssl':'network',
             'pathlib':'filesystem','shutil':'filesystem','glob':'filesystem','tempfile':'filesystem',
             'subprocess':'subprocess','multiprocessing':'subprocess','sqlite3':'database','psycopg2':'database','sqlalchemy':'database',
             'pymongo':'database','redis':'database','random':'random','secrets':'random','serial':'hardware','pymavlink':'hardware','dronekit':'hardware'},
  'javascript': {'http':'network','https':'network','net':'network','axios':'network','node-fetch':'network','ws':'network','fs':'filesystem',
                 'fs/promises':'filesystem','path':None,'child_process':'subprocess','worker_threads':'subprocess','pg':'database','mysql':'database',
                 'mysql2':'database','mongoose':'database','mongodb':'database','sqlite3':'database','crypto':'random','serialport':'hardware'},
  'go': {'net/http':'network','net':'network','crypto/tls':'network','os/exec':'subprocess','database/sql':'database','math/rand':'random',
         'crypto/rand':'random','io/ioutil':'filesystem','path/filepath':None,'os':'filesystem','time':'clock'},
  'rust': {'reqwest':'network','hyper':'network','tokio::net':'network','std::net':'network','std::fs':'filesystem','tokio::fs':'filesystem',
           'std::process':'subprocess','std::env':'env','std::time':'clock','rand':'random','sqlx':'database','diesel':'database','rusqlite':'database','serialport':'hardware'},
  'java': {'java.net':'network','okhttp3':'network','org.apache.http':'network','java.io':'filesystem','java.nio.file':'filesystem',
           'java.sql':'database','javax.sql':'database','java.util.Random':'random','java.security.SecureRandom':'random','java.time':'clock'},
  'c':   {'sys/socket.h':'network','netinet':'network','curl':'network','stdio.h':None,'fcntl.h':'filesystem','unistd.h':None,'termios.h':'hardware'},
  'cpp': {'sys/socket.h':'network','netinet':'network','curl':'network','fstream':'filesystem','filesystem':'filesystem','thread':None,
          'chrono':'clock','random':'random','termios.h':'hardware','boost/asio':'network','mavsdk':'hardware'},
}
EFFECT_IMPORTS['typescript'] = EFFECT_IMPORTS['javascript']
# imports that match a table prefix but are NOT effects (pure helpers, types, exceptions, parsers)
NO_EFFECT = {
  'python': ('urllib.parse','urllib.error','urllib3.exceptions','urllib3.fields','urllib3.filepost','urllib3.util','urllib3.response',
             'requests.exceptions','requests.structures','requests.compat','io.StringIO','io.BytesIO','socket.error','socket.timeout'),
  'javascript': ('http-errors','path','url'), 'typescript': ('http-errors','path','url'),
  'go': ('net/url','net/http/httptest','net/textproto','net/mail','os/signal','os/user','time'),
  'rust': ('std::net::IpAddr','std::net::SocketAddr','hyper::header','reqwest::header','std::time::Duration'),
  'java': ('java.net.URI','java.net.URL','java.net.URLEncoder','java.net.URLDecoder','java.io.IOException','java.io.Serializable',
           'java.io.InputStream','java.io.OutputStream','java.io.Reader','java.io.Writer','java.io.StringReader','java.io.StringWriter',
           'java.io.ByteArrayInputStream','java.io.ByteArrayOutputStream','java.io.UncheckedIOException','java.time.Duration'),
  'c': (), 'cpp': ('chrono',),
}
EFFECT_CALLS = {
  'python': {'open':'filesystem','os.environ':'env','os.getenv':'env','os.system':'subprocess','os.popen':'subprocess','time.time':'clock',
             'time.sleep':'clock','datetime.now':'clock','datetime.utcnow':'clock','os.remove':'filesystem','os.listdir':'filesystem','os.makedirs':'filesystem'},
  'javascript': {'fetch':'network','process.env':'env','Date.now':'clock','Math.random':'random','require':None,'setTimeout':'clock','setInterval':'clock'},
  'go': {'os.Getenv':'env','os.Environ':'env','time.Now':'clock','time.Sleep':'clock','os.Open':'filesystem','os.Create':'filesystem','os.ReadFile':'filesystem',
         'os.WriteFile':'filesystem','os.Remove':'filesystem','os.Stat':'filesystem','ioutil.ReadFile':'filesystem','exec.Command':'subprocess','rand.Intn':'random'},
  'rust': {'std::env::var':'env','env::var':'env','Instant::now':'clock','SystemTime::now':'clock','Command::new':'subprocess','File::open':'filesystem',
           'File::create':'filesystem','fs::read':'filesystem','fs::write':'filesystem','fs::read_to_string':'filesystem','TcpStream::connect':'network'},
  'java': {'System.getenv':'env','System.currentTimeMillis':'clock','Instant.now':'clock','System.nanoTime':'clock','Runtime.exec':'subprocess',
           'ProcessBuilder':'subprocess','Files.read':'filesystem','Files.write':'filesystem','new File':'filesystem','Math.random':'random'},
  'c':   {'fopen':'filesystem','open':'filesystem','read':None,'write':None,'system':'subprocess','popen':'subprocess','fork':'subprocess','exec':'subprocess',
          'getenv':'env','time':'clock','clock_gettime':'clock','rand':'random','socket':'network','connect':'network','ioctl':'hardware'},
}
EFFECT_CALLS['typescript'] = EFFECT_CALLS['javascript']; EFFECT_CALLS['cpp'] = dict(EFFECT_CALLS['c'], **{'std::ifstream':'filesystem','std::ofstream':'filesystem','std::getenv':'env'})

# ---- helpers --------------------------------------------------------------------------------
def node_text(n, src): return src[n.start_byte:n.end_byte].decode('utf-8', 'ignore')

def child_by_field(n, f):
    try: return n.child_by_field_name(f)
    except Exception: return None

def def_name(n, lang, src):
    nm = child_by_field(n, 'name')
    if nm is not None: return node_text(nm, src)
    if lang in ('javascript','typescript') and n.type in ('lexical_declaration','variable_declaration'):
        for c in n.children:
            if c.type == 'variable_declarator':
                nm = child_by_field(c, 'name'); return node_text(nm, src) if nm is not None else None
    if lang in ('c','cpp') and n.type == 'function_definition':
        d = child_by_field(n, 'declarator')
        while d is not None and d.type not in ('identifier','field_identifier','qualified_identifier','destructor_name'):
            d = child_by_field(d, 'declarator') or (d.children[0] if d.children else None)
        return node_text(d, src) if d is not None else None
    if lang in ('c','cpp') and n.type == 'type_definition':
        d = child_by_field(n, 'declarator'); return node_text(d, src) if d is not None else None
    return None

def is_exported(n, lang, name, src):
    if not name: return False
    if lang == 'python': return not name.startswith('_')
    if lang in ('javascript','typescript'):
        p = n.parent
        return p is not None and p.type == 'export_statement'
    if lang == 'go': return name[0].isupper()
    if lang == 'rust':
        return any(c.type == 'visibility_modifier' for c in n.children)
    if lang == 'java':
        for c in n.children:
            if c.type == 'modifiers': return 'public' in node_text(c, src) or 'protected' in node_text(c, src)
        return False
    if lang in ('c','cpp'):
        head = node_text(n, src)[:200]
        return not head.lstrip().startswith('static')
    return True

def import_names(n, lang, src):
    """Local names bound by this import (what a call in this file would start with)."""
    names = []
    if lang == 'python':
        for c in n.children:
            if c.type == 'dotted_name': names.append(node_text(c, src).split('.')[-1])
            if c.type == 'aliased_import':
                al = child_by_field(c, 'alias'); nm = child_by_field(c, 'name')
                names.append(node_text(al if al is not None else nm, src).split('.')[-1])
            if c.type == 'wildcard_import': names.append('*')
        if n.type == 'import_from_statement':
            m = child_by_field(n, 'module_name'); mt = node_text(m, src) if m is not None else ''
            names = [x for x in names if x != mt.split('.')[-1]] or names
    elif lang in ('javascript','typescript'):
        for c in walk(n):
            if c.type in ('identifier','namespace_import') and c.parent.type in ('import_clause','import_specifier','namespace_import','import_clause'):
                names.append(node_text(c, src).replace('* as','').strip())
    elif lang == 'go':
        p = child_by_field(n, 'path'); nm = child_by_field(n, 'name')
        if nm is not None: names.append(node_text(nm, src))
        elif p is not None: names.append(node_text(p, src).strip('"').split('/')[-1])
    elif lang == 'rust':
        t = node_text(n, src)
        inner = t[t.rfind('{')+1:t.rfind('}')] if '{' in t else t.rstrip(';').split('::')[-1]
        names += [x.strip().split(' as ')[-1].strip() for x in inner.split(',') if x.strip()]
    elif lang == 'java':
        names.append(node_text(n, src).rstrip(';').split('.')[-1].strip())
    return [x for x in names if x]

def import_targets(n, lang, src):
    t = node_text(n, src)
    if lang == 'python':
        if n.type == 'import_from_statement':
            m = child_by_field(n, 'module_name'); return [node_text(m, src)] if m is not None else []
        return [node_text(c, src) for c in n.children if c.type in ('dotted_name','aliased_import')]
    if lang in ('javascript','typescript'):
        s = child_by_field(n, 'source'); return [node_text(s, src).strip('\'"`')] if s is not None else []
    if lang == 'go':
        p = child_by_field(n, 'path'); return [node_text(p, src).strip('"')] if p is not None else []
    if lang == 'rust':
        return [t.replace('use ','').rstrip(';').strip()]
    if lang == 'java':
        return [t.replace('import ','').replace('static ','').rstrip(';').strip()]
    if lang in ('c','cpp'):
        p = child_by_field(n, 'path'); return [node_text(p, src).strip('<>"')] if p is not None else []
    return []

def callee_name(n, lang, src):
    f = child_by_field(n, 'function') if lang != 'java' else None
    if lang == 'java':
        obj = child_by_field(n, 'object'); nm = child_by_field(n, 'name')
        return (node_text(obj, src) + '.' if obj is not None else '') + (node_text(nm, src) if nm is not None else '')
    return node_text(f, src) if f is not None else ''

def walk(n):
    stack = [n]
    while stack:
        x = stack.pop(); yield x
        stack.extend(reversed(x.children))

# ---- extraction -----------------------------------------------------------------------------
def extract(repo):
    repo = Path(repo)
    files = sorted(p for p in repo.rglob('*') if p.is_file() and p.suffix in LANG_BY_EXT and not (set(p.parts[len(repo.parts):]) & SKIP_DIRS))
    out = {}
    parsers = {}
    for p in files:
        lang = LANG_BY_EXT[p.suffix]; rel = str(p.relative_to(repo))
        if lang not in parsers: parsers[lang] = get_parser(lang)
        try: src = p.read_bytes()
        except Exception: continue
        if len(src) > 2_000_000: continue
        tree = parsers[lang].parse(src); root = tree.root_node
        defs, imports, calls, idents, effects, reexports = [], [], [], set(), set(), []
        weak = []   # (kind, names) from imports; confirmed later by a call through one of names
        for n in walk(root):
            if n.type in DEF_NODES[lang]:
                # top-level or class-member only (depth <= 3 keeps nested helpers out)
                depth = 0; a = n.parent
                while a is not None and a.type != root.type: depth += 1; a = a.parent
                if depth > 3: continue
                nm = def_name(n, lang, src)
                kind = DEF_NODES[lang][n.type]
                a = n.parent; in_class = False
                while a is not None:
                    if a.type in ('class_definition','class_declaration','class_body','impl_item','trait_item','class_specifier','struct_specifier','abstract_class_declaration','interface_declaration','enum_declaration','record_declaration'):
                        in_class = True; break
                    a = a.parent
                if in_class and kind in ('function','const'): kind = 'method'
                if nm: defs.append(dict(name=nm, kind=kind, line=n.start_point[0]+1, exported=is_exported(n, lang, nm, src)))
            elif n.type in IMPORT_NODES[lang]:
                if lang == 'python' and n.type == 'import_from_statement' and Path(rel).name == '__init__.py':
                    mod = child_by_field(n, 'module_name'); modt = node_text(mod, src).lstrip('.') if mod is not None else None
                    for c in n.children:
                        if c.type == 'dotted_name' and c is not mod: reexports.append((node_text(c, src), modt or None))
                        if c.type == 'aliased_import':
                            nm = child_by_field(c, 'name'); reexports.append((node_text(nm, src), modt or None))
                if lang == 'rust' and 'pub' in node_text(n, src)[:8]:
                    body = node_text(n, src).replace('pub use','').replace('pub(crate) use','').rstrip(';')
                    inner = body[body.rfind('{')+1:body.rfind('}')] if '{' in body else body.split('::')[-1]
                    for sym in inner.split(','):
                        sym = sym.strip().split(' as ')[-1].strip()
                        if sym and sym != 'self': reexports.append((sym, None))
                names = import_names(n, lang, src)
                for t in import_targets(n, lang, src):
                    imports.append(t)
                    if any(t == x or t.startswith(x + '.') or t.startswith(x + '::') or t.startswith(x + '/') for x in NO_EFFECT[lang]): continue
                    for mod, kind in EFFECT_IMPORTS[lang].items():
                        if kind and (t == mod or t.startswith(mod + '.') or t.startswith(mod + '/') or t.startswith(mod + '::') or t.endswith('/' + mod)):
                            weak.append((kind, names or [mod.split('/')[-1].split('.')[-1]]))
            elif n.type == 'export_statement' and lang in ('javascript','typescript') and Path(rel).stem == 'index':
                srcn = child_by_field(n, 'source'); tgt = node_text(srcn, src).strip('\'"`') if srcn is not None else None
                txt = node_text(n, src)
                if '*' in txt.split('from')[0]: reexports.append(('*', tgt))
                for c in walk(n):
                    if c.type == 'export_specifier':
                        nm = child_by_field(c, 'name'); reexports.append((node_text(nm, src), tgt))
            elif n.type == CALL_NODES[lang]:
                cn = callee_name(n, lang, src)
                if cn:
                    calls.append(cn)
                    for pat, kind in EFFECT_CALLS[lang].items():
                        if kind and (cn == pat or cn.endswith('.' + pat) or cn.endswith('::' + pat) or cn.startswith(pat + '(') ):
                            effects.add(kind)
            elif n.type in ('identifier','type_identifier','field_identifier','property_identifier','scoped_identifier'):
                par = n.parent
                if par is not None and par.type in ('attribute','member_expression','field_expression','selector_expression','field_access','scoped_identifier') \
                   and par.children and par.children[0] is not n:
                    continue   # `x.get` -> do not resolve `get` as a free symbol
                idents.add(node_text(n, src))
        # confirm import-derived effects: some call in this file goes through a name the import bound
        callset = set(calls)
        for kind, names in weak:
            if '*' in names or any(c == nm or c.startswith(nm + '.') or c.startswith(nm + '::') or c.startswith(nm + '(') for nm in names for c in callset):
                effects.add(kind)
            elif lang in ('c','cpp'):
                effects.add(kind)          # C has no import names; header include is the best evidence we get
        # cheap detectors for effects that are not calls/imports
        txt = src.decode('utf-8','ignore')
        if lang == 'python' and 'os.environ' in txt: effects.add('env')
        if lang in ('javascript','typescript') and 'process.env' in txt: effects.add('env')
        out[rel] = dict(lang=lang, defs=defs, imports=imports, calls=calls, idents=sorted(idents), effects=sorted(effects), reexports=reexports)
    return resolve(out)

def public_surface(files):
    """(file, symbol) pairs that form the repo's external API. Static refs cannot see external callers,
    so these count as true entrypoints even with zero intra-repo references."""
    surf = set()
    def_index = defaultdict(set)
    for f, d in files.items():
        for df in d['defs']:
            if df['exported']: def_index[df['name']].add(f)
    header_names = set()
    for f, d in files.items():
        lang = d['lang']; base = Path(f).name; parts = set(Path(f).parts)
        if lang == 'python' and base == '__init__.py':
            for df in d['defs']:
                if df['exported']: surf.add((f, df['name']))
            for sym, tgt in d.get('reexports', []):
                for cand in def_index.get(sym, ()):
                    if tgt is None or Path(cand).stem == tgt or str(Path(cand).with_suffix('')).endswith(tgt.replace('.', '/')):
                        surf.add((cand, sym))
        elif lang in ('javascript','typescript') and Path(f).stem == 'index':
            for df in d['defs']:
                if df['exported']: surf.add((f, df['name']))
            for sym, tgt in d.get('reexports', []):
                tgt_stem = Path(tgt).stem if tgt else None
                for name, cands in def_index.items():
                    if sym not in ('*', name): continue
                    for cand in cands:
                        if tgt_stem is None or Path(cand).stem == tgt_stem: surf.add((cand, name))
        elif lang == 'rust' and base in ('lib.rs', 'main.rs'):
            for sym, _ in d.get('reexports', []):
                for cand in def_index.get(sym, ()): surf.add((cand, sym))
            for df in d['defs']:
                if df['exported']: surf.add((f, df['name']))
        elif lang == 'go' and 'internal' not in parts:
            for df in d['defs']:
                if df['exported']: surf.add((f, df['name']))
        elif lang == 'java' and not ({'internal','impl'} & parts):
            for df in d['defs']:
                if df['exported'] and df['kind'] in ('class','type'): surf.add((f, df['name']))
        elif lang in ('c','cpp') and Path(f).suffix in ('.h','.hpp','.hh'):
            header_names |= set(d['idents'])
    for f, d in files.items():
        if d['lang'] in ('c','cpp') and Path(f).suffix not in ('.h','.hpp','.hh'):
            for df in d['defs']:
                if df['exported'] and df['name'] in header_names: surf.add((f, df['name']))
    return sorted(surf)

def resolve(files):
    """Build file->file edges and cross-file refs by name, disambiguated by imports."""
    def_index = defaultdict(set)
    for f, d in files.items():
        for df in d['defs']:
            if df['kind'] != 'method': def_index[df['name']].add(f)   # methods are reached via their class, not by bare name
    stem_index = defaultdict(set)
    for f in files:
        stem_index[Path(f).stem].add(f)
        stem_index[str(Path(f).with_suffix(''))].add(f)
    edges = defaultdict(set); refs = defaultdict(set)   # refs[file] = {(target_file, symbol)}
    for f, d in files.items():
        linked = set()
        for imp in d['imports']:
            key = imp.replace('.', '/').replace('::', '/').strip('./')
            for cand in (key, key.split('/')[-1], Path(key).stem):
                for tgt in stem_index.get(cand, ()):
                    if tgt != f: linked.add(tgt)
        for tgt in linked: edges[f].add(tgt)
        own = {df['name'] for df in d['defs']}
        for ident in d['idents']:
            if ident in own or ident not in def_index: continue
            cands = def_index[ident] - {f}
            if not cands: continue
            hit = cands & linked if linked else set()
            if not hit and len(cands) == 1: hit = cands          # unique in repo: accept
            for tgt in hit:
                refs[f].add((tgt, ident)); edges[f].add(tgt)
    return dict(files=files, edges={k: sorted(v) for k, v in edges.items()},
                refs={k: sorted(v) for k, v in refs.items()}, public_surface=public_surface(files))

# ---- scoring against a manifest -------------------------------------------------------------
def score(graph, manifest):
    files = graph['files']; refs = graph['refs']
    surface = defaultdict(set)
    for f, sym in graph.get('public_surface', []): surface[f].add(sym)
    units = manifest.get('units', [])
    owner = {f: u['name'] for u in units for f in u.get('files', [])}
    per_unit = {}
    for u in units:
        uf = set(u.get('files', []))
        # invariant 2 ground truth: defs in U referenced from outside U
        true_eps = set()
        for src_file, rlist in refs.items():
            if owner.get(src_file) == u['name']: continue
            for tgt, sym in rlist:
                if tgt in uf: true_eps.add(sym)
        for f in uf: true_eps |= surface.get(f, set())          # external API counts even with no internal callers
        listed = {e['name'].split('.')[-1] for e in u.get('entrypoints', [])}
        tp = len(listed & true_eps)
        ep_p = tp / len(listed) if listed else None
        ep_r = tp / len(true_eps) if true_eps else None
        # invariant 4: declared vs detected
        detected = set()
        for f in uf:
            if f in files: detected |= set(files[f]['effects'])
        declared = {e['kind'] for e in u.get('effects', [])}
        tp4 = len(declared & detected)
        ef_p = tp4 / len(declared) if declared else None
        ef_r = tp4 / len(detected) if detected else None
        per_unit[u['name']] = dict(entrypoint_p=ep_p, entrypoint_r=ep_r, true_entrypoints=sorted(true_eps),
                                   missed=sorted(true_eps - listed), spurious=sorted(listed - true_eps),
                                   effects_p=ef_p, effects_r=ef_r, detected_effects=sorted(detected), undeclared=sorted(detected - declared))
    def avg(key):
        v = [x[key] for x in per_unit.values() if x[key] is not None]
        return round(sum(v)/len(v), 4) if v else None
    summary = dict(entrypoint_p=avg('entrypoint_p'), entrypoint_r=avg('entrypoint_r'), effects_p=avg('effects_p'), effects_r=avg('effects_r'),
                   units_with_undeclared_effects=sum(1 for x in per_unit.values() if x['undeclared']),
                   units_with_missed_entrypoints=sum(1 for x in per_unit.values() if x['missed']))
    return dict(summary=summary, units=per_unit)

if __name__ == '__main__':
    if sys.argv[1] == 'extract':
        print(json.dumps(extract(sys.argv[2])))
    elif sys.argv[1] == 'score':
        g = json.load(open(sys.argv[2])); m = json.load(open(sys.argv[3]))
        print(json.dumps(score(g, m), indent=2))
