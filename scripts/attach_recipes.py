#!/usr/bin/env python3
"""
attach_recipes.py — Attache une RECETTE (prompt Suno) aux sons publiés SANS
recette, à partir d'un fichier JSON {name: prompt_text}. Étape préalable au
backfill d'œuvres : un son sans recette n'a pas de face « son » à lier.

Pour chaque recette du JSON :
  1. Match le SON par titre normalisé via GET /tracks/me.
  2. SKIP si le son a déjà un prompt_id (idempotent).
  3. Crée la recette : POST /artist/me/prompts.
  4. L'attache : PATCH /tracks/{id} { prompt_id }.

⚠️ DRY-RUN par défaut. --execute pour écrire.

Env : WATT_API_BASE + (WATT_TOKEN | WATT_EMAIL+WATT_PASSWORD).

Usage :
  WATT_API_BASE=... WATT_EMAIL=... python3 scripts/attach_recipes.py \
      --recipes data/recipes_backfill_jungle.json
  ... --execute
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Installe requests : pip install requests")


def norm(s: str) -> str:
    s = s or ""
    if "—" in s:
        s = s.split("—", 1)[1]
    if "·" in s:
        s = s.split("·", 1)[0]
    s = s.lower()
    s = re.sub(r"\.(png|jpg|jpeg|webp|wav|mp3|m4a|flac)$", "", s)
    for junk in ("cover", "civer", "drift", "sw-001", "sw001"):
        s = s.replace(junk, "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def _login(base: str) -> str:
    token = os.environ.get("WATT_TOKEN", "")
    if token:
        return token
    import getpass
    email = os.environ.get("WATT_EMAIL", "").strip()
    pwd = os.environ.get("WATT_PASSWORD", "")
    if "@" not in email:
        email = input("Email du compte WATT : ").strip()
    if not pwd:
        pwd = getpass.getpass("Mot de passe : ")
    lr = requests.post(f"{base}/auth/login",
                       json={"email": email, "password": pwd}, timeout=30)
    if lr.status_code >= 300:
        sys.exit(f"Login échoué : {lr.status_code} {lr.text[:160]}")
    token = lr.json().get("access_token", "")
    if not token:
        sys.exit("Login OK mais pas d'access_token.")
    print("✅ Connecté via /auth/login.\n")
    return token


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipes", required=True, help="Fichier JSON des recettes")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    base = os.environ.get("WATT_API_BASE", "").rstrip("/")
    if not base:
        sys.exit("Définis WATT_API_BASE.")

    cfg = json.loads(Path(args.recipes).expanduser().read_text(encoding="utf-8"))
    recipes = cfg["recipes"]
    platform = cfg.get("platform", "suno")
    vocal = cfg.get("vocal", "instrumental")
    price = int(cfg.get("price", 30))
    print(f"{len(recipes)} recettes · platform={platform} · vocal={vocal} · prix={price} S\n")

    token = _login(base)
    H = {"Authorization": f"Bearer {token}"}

    r = requests.get(f"{base}/tracks/me", headers=H, timeout=30)
    r.raise_for_status()
    tracks = r.json()
    if isinstance(tracks, dict):
        tracks = tracks.get("items") or tracks.get("tracks") or []
    by_norm = {norm(t.get("title") or t.get("name") or ""): t for t in tracks}
    print(f"{len(tracks)} sons trouvés sur ce compte.\n")

    def match(key):
        if key in by_norm:
            return by_norm[key]
        sub = [v for k, v in by_norm.items() if k and (k in key or key in k)]
        if len(sub) == 1:
            return sub[0]
        cl = difflib.get_close_matches(key, list(by_norm.keys()), n=1, cutoff=0.85)
        return by_norm[cl[0]] if cl else None

    plan, skip = [], []
    for name, text in recipes.items():
        t = match(norm(name))
        if not t:
            skip.append((name, "aucun son ne matche"))
        elif t.get("prompt_id"):
            skip.append((name, "a déjà une recette (skip)"))
        elif len(text) > 1000:
            skip.append((name, f"recette trop longue ({len(text)}>1000)"))
        else:
            plan.append((name, text, t))

    print("=== PLAN ===")
    for name, text, t in plan:
        print(f"  {name:22s} → « {t.get('title') or t.get('name')} »  (recette {len(text)} car.)")
    if skip:
        print("\n⚠️  IGNORÉS :")
        for name, why in skip:
            print(f"  {name:22s} — {why}")

    if not args.execute:
        print("\nDRY-RUN — rien écrit. Relance avec --execute.")
        return 0

    print("\n=== EXÉCUTION ===")
    ok = 0
    for name, text, t in plan:
        title = (t.get("title") or t.get("name") or name)[:120]
        if len(title) < 5:  # contrainte API : titre recette ≥ 5 caractères
            title = f"{title} — ADN"
        cr = requests.post(
            f"{base}/artist/me/prompts",
            headers=H,
            json={
                "title": title,
                "prompt_text": text,
                "price_credits": price,
                "prompt_platform": platform,
                "prompt_weirdness": "50",
                "prompt_style_influence": "50",
                "prompt_vocal_gender": vocal,
                "is_published": True,
            },
            timeout=30,
        )
        if cr.status_code >= 300:
            print(f"  ❌ recette « {title} » : {cr.status_code} {cr.text[:160]}")
            continue
        pid = cr.json().get("id") or cr.json().get("prompt_id")
        if not pid:
            print(f"  ❌ « {title} » : recette créée mais pas d'id.")
            continue
        pt = requests.patch(
            f"{base}/tracks/{t['id']}", headers=H,
            json={"prompt_id": pid}, timeout=30,
        )
        if pt.status_code >= 300:
            print(f"  ⚠️  « {title} » : recette OK (id={pid}) mais attache KO {pt.status_code} {pt.text[:120]}")
            continue
        print(f"  ✅ « {title} » — recette créée + attachée")
        ok += 1

    print(f"\nTerminé : {ok}/{len(plan)} recettes attachées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
