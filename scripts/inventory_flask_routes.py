#!/usr/bin/env python3
"""P0-a — Inventaire des routes Flask vs FastAPI vs front.

Analyse statique, idempotent, ne modifie rien.
Sorties :
  OBSIDIAN/05_TECH/Flask_routes_inventory.md   (rapport de décision)
  OBSIDIAN/05_TECH/Flask_routes_inventory.json (données brutes)

Couvre :
  1. Routes Flask (@app.route) + garde 410 centralisé (_LEGACY_BLOCKED_PREFIXES,
     applique en before_request — un parseur naïf de décorateurs le raterait).
  2. Endpoints FastAPI (APIRouter + prefix, tous les fichiers de watt-api/app/routers/).
  3. Appels front : fetch()/apiFetch() + littéraux /api/* dans *.js/*.html
     (racine + ui/ récursif).
  4. Tables legacy de models.py → requête SQL d'audit prod (lecture seule).
"""
import ast, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "OBSIDIAN" / "05_TECH"

# ── 1. Flask ────────────────────────────────────────────────────────────────
def parse_flask():
    src = (ROOT / "flask_app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    routes, blocked_prefixes = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_LEGACY_BLOCKED_PREFIXES":
                    blocked_prefixes = [e.value for e in node.value.elts
                                        if isinstance(e, ast.Constant)]
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "route"
                        and isinstance(dec.func.value, ast.Name)
                        and dec.func.value.id == "app" and dec.args):
                    path = dec.args[0].value
                    methods = ["GET"]
                    for kw in dec.keywords:
                        if kw.arg == "methods":
                            methods = [e.value for e in kw.value.elts]
                    routes.append({"path": path, "methods": methods,
                                   "line": node.lineno, "func": node.name})
    for r in routes:
        p = r["path"].rstrip("/")
        r["blocked_410"] = any(p == b or p.startswith(b + "/") or p.startswith(b)
                               for b in blocked_prefixes)
    return routes, blocked_prefixes

# ── 2. FastAPI ──────────────────────────────────────────────────────────────
HTTP = {"get", "post", "put", "patch", "delete", "head", "options"}

def parse_fastapi():
    endpoints = []
    for f in sorted((ROOT / "watt-api" / "app" / "routers").glob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            print(f"  ! syntax error {f.name}: {e}", file=sys.stderr); continue
        prefixes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                if (isinstance(fn, ast.Name) and fn.id == "APIRouter") or \
                   (isinstance(fn, ast.Attribute) and fn.attr == "APIRouter"):
                    pref = ""
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            pref = kw.value.value
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            prefixes[t.id] = pref
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                            and dec.func.attr in HTTP
                            and isinstance(dec.func.value, ast.Name)
                            and dec.func.value.id in prefixes and dec.args
                            and isinstance(dec.args[0], ast.Constant)):
                        full = prefixes[dec.func.value.id] + dec.args[0].value
                        endpoints.append({"file": f.name, "router": dec.func.value.id,
                                          "method": dec.func.attr.upper(),
                                          "path": full, "line": node.lineno})
    return endpoints

# ── 3. Front ────────────────────────────────────────────────────────────────
CALL_RE = re.compile(r"""(?:fetch|apiFetch)\(\s*[`'"]([^`'"]+)""")
API_RE = re.compile(r"""[`'"](/api/[A-Za-z0-9_\-/.${}]*)""")

def scan_front():
    files = [p for p in ROOT.glob("*.js")] + [p for p in ROOT.glob("*.html")] + \
            [p for p in (ROOT / "ui").rglob("*.js")] + [p for p in (ROOT / "ui").rglob("*.html")]
    calls = {}
    for p in files:
        try:
            s = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(ROOT))
        for m in CALL_RE.finditer(s):
            u = m.group(1).split("?")[0]
            if u.startswith("/"):
                calls.setdefault(re.sub(r"\$\{[^}]*\}", "{x}", u), set()).add(rel)
        for m in API_RE.finditer(s):
            calls.setdefault(re.sub(r"\$\{[^}]*\}", "{x}", m.group(1).split("?")[0]), set()).add(rel)
    return {k: sorted(v) for k, v in sorted(calls.items())}

# ── 4. Tables legacy ────────────────────────────────────────────────────────
TS_HINTS = ("created_at", "created", "timestamp", "updated_at", "sent_at", "date")

def parse_models():
    tree = ast.parse((ROOT / "models.py").read_text(encoding="utf-8"))
    tables = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        tname, cols = None, []
        for st in node.body:
            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name):
                nm = st.targets[0].id
                if nm == "__tablename__" and isinstance(st.value, ast.Constant):
                    tname = st.value.value
                elif isinstance(st.value, ast.Call):
                    fn = st.value.func
                    if isinstance(fn, ast.Attribute) and fn.attr == "Column":
                        cols.append(nm)
        if tname:
            ts = next((c for h in TS_HINTS for c in cols if c == h or h in c), None)
            tables.append({"table": tname, "model": node.name, "ts_col": ts})
    return tables

def audit_sql(tables):
    lines = []
    for t in tables:
        mx = f"max({t['ts_col']})::text" if t["ts_col"] else "NULL"
        lines.append(f"SELECT '{t['table']}' AS tbl, count(*) AS rows, {mx} AS last_ts FROM {t['table']}")
    return "\nUNION ALL\n".join(lines) + ";"

# ── Matching & rapport ──────────────────────────────────────────────────────
def norm(p):
    p = re.sub(r"<int:(\w+)>", r"{\1}", p)
    p = re.sub(r"<(\w+)>", r"{\1}", p)
    return p.rstrip("/") or "/"

def variants(p):
    n = norm(p)
    out = {n}
    if n.startswith("/api/"):
        out |= {n[4:], "/watt" + n[4:], n.replace("/api/watt/", "/watt/")}
    return out

def main():
    flask_routes, blocked = parse_flask()
    fastapi_eps = parse_fastapi()
    front = scan_front()
    tables = parse_models()
    sql = audit_sql(tables)

    fa_by_norm = {}
    for e in fastapi_eps:
        fa_by_norm.setdefault(re.sub(r"\{\w+\}", "{x}", norm(e["path"])), []).append(e)

    front_norm = {re.sub(r"\{\w+\}|\{x\}", "{x}", norm(k)): v for k, v in front.items()}

    for r in flask_routes:
        n = re.sub(r"\{\w+\}", "{x}", norm(r["path"]))
        eq = []
        for v in variants(r["path"]):
            vv = re.sub(r"\{\w+\}", "{x}", v)
            for e in fa_by_norm.get(vv, []):
                eq.append(f"{e['method']} {e['path']} ({e['file']})")
        r["fastapi_equiv"] = sorted(set(eq))
        r["front_callers"] = front_norm.get(n, [])
        if r["blocked_410"]:
            r["decision"] = "supprimer (déjà bloquée 410)"
        elif r["path"].startswith("/api/"):
            r["decision"] = "SUPPRIMER (défaut)" if not r["front_callers"] else "VÉRIFIER — encore appelée par le front !"
        else:
            r["decision"] = "migrer vers pages.py FastAPI (P0-b)"

    api_routes = [r for r in flask_routes if r["path"].startswith("/api/")]
    page_routes = [r for r in flask_routes if not r["path"].startswith("/api/")]

    md = ["# Inventaire routes Flask — P0-a", "",
          f"> Généré par `scripts/inventory_flask_routes.py` — analyse statique.",
          f"> {len(flask_routes)} routes Flask · {len(fastapi_eps)} endpoints FastAPI · "
          f"{len(front)} chemins appelés par le front · {len(tables)} tables legacy.", "",
          "## Garde 410 centralisé (before_request)", "",
          "Préfixes bloqués : " + ", ".join(f"`{b}`" for b in blocked), "",
          "## Routes API Flask (`/api/*`) — candidat suppression P0-c", "",
          "| Route | Méthodes | 410 | Équivalent FastAPI | Front ? | Décision |",
          "|---|---|---|---|---|---|"]
    for r in api_routes:
        md.append(f"| `{r['path']}` (l.{r['line']}) | {','.join(r['methods'])} | "
                  f"{'✅' if r['blocked_410'] else '—'} | "
                  f"{'<br>'.join(r['fastapi_equiv']) or '—'} | "
                  f"{'<br>'.join(r['front_callers']) or 'non'} | {r['decision']} |")
    md += ["", "## Routes pages & statiques — périmètre P0-b (`pages.py`)", "",
           "| Route | Méthodes | Décision |", "|---|---|---|"]
    for r in page_routes:
        md.append(f"| `{r['path']}` (l.{r['line']}) | {','.join(r['methods'])} | {r['decision']} |")
    md += ["", "## Appels front détectés (fetch/apiFetch + littéraux /api/*)", "",
           "| Chemin | Fichiers |", "|---|---|"]
    for k, v in front.items():
        md.append(f"| `{k}` | {', '.join(v[:4])}{'…' if len(v) > 4 else ''} |")
    md += ["", "## Audit SQL des tables legacy (LECTURE SEULE — à lancer en prod avec accord Tom)",
           "", "```sql", sql, "```", "",
           "> Compléter avec les logs Railway 7-14 j sur les chemins Flask avant le P0-c."]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "Flask_routes_inventory.md").write_text("\n".join(md), encoding="utf-8")
    (OUT_DIR / "Flask_routes_inventory.json").write_text(json.dumps({
        "flask_routes": flask_routes, "blocked_prefixes": blocked,
        "fastapi_endpoints": fastapi_eps, "front_calls": front,
        "legacy_tables": tables, "audit_sql": sql}, indent=2, ensure_ascii=False,
        default=list), encoding="utf-8")
    print(f"OK — {len(flask_routes)} routes Flask ({len(api_routes)} API, {len(page_routes)} pages)")
    print(f"Rapport : {OUT_DIR / 'Flask_routes_inventory.md'}")
    alerts = [r for r in api_routes if r["front_callers"]]
    if alerts:
        print("⚠ Routes API Flask encore appelées par le front :")
        for r in alerts:
            print(f"  {r['path']} ← {r['front_callers']}")
    else:
        print("✔ Aucune route API Flask appelée par le front.")

if __name__ == "__main__":
    main()
