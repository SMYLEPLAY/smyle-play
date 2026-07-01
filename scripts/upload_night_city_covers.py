#!/usr/bin/env python3
"""
upload_night_city_covers.py — Attache automatiquement les covers Night City
au bon SON correspondant sur WATT, depuis le dossier local des covers.

Pour chaque cover :
  1. Résout le track par son TITRE (match normalisé) via GET /tracks/me.
  2. Upload l'image en R2 via POST /watt/upload-image (kind=track-cover).
  3. Lie la cover au son via PATCH /tracks/{id} { cover_url }.

⚠️ Aucune donnée de prod n'est modifiée tant que --execute n'est pas passé.
Par défaut : DRY-RUN (affiche le plan, ne fait aucune écriture).

Pré-requis (variables d'environnement) :
  WATT_API_BASE  ex: https://web-production-e30c8c.up.railway.app
  Auth — au choix :
    • WATT_TOKEN   Bearer JWT du compte propriétaire des sons Night City, OU
    • WATT_EMAIL + WATT_PASSWORD  (compte Smyle) → le script se connecte seul
                                  via /auth/login (rien à copier du navigateur).

Usage :
  # 1) Vérifier le plan (aucune écriture) :
  WATT_API_BASE=... WATT_TOKEN=... python3 scripts/upload_night_city_covers.py \
      --covers "/Users/tommio/Desktop/WORK/SMYLE/cover night city"

  # 2) Exécuter pour de vrai :
  WATT_API_BASE=... WATT_TOKEN=... python3 scripts/upload_night_city_covers.py \
      --covers "/Users/tommio/Desktop/WORK/SMYLE/cover night city" --execute
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Installe requests : pip install requests")


def norm(s: str) -> str:
    """Normalise un nom pour matcher cover<->titre (minuscule, sans extension,
    sans 'cover', sans accents/espaces/ponctuation)."""
    s = s.lower()
    s = re.sub(r"\.(png|jpg|jpeg|webp)$", "", s)
    s = s.replace("cover", "")
    repl = {"é": "e", "è": "e", "ê": "e", "à": "a", "ç": "c", "î": "i", "ô": "o", "û": "u"}
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--covers", required=True, help="Dossier des covers Night City")
    ap.add_argument("--execute", action="store_true", help="Écrit réellement (sinon dry-run)")
    ap.add_argument("--overwrite", action="store_true", help="Remplace une cover déjà présente")
    args = ap.parse_args()

    base = os.environ.get("WATT_API_BASE", "").rstrip("/")
    token = os.environ.get("WATT_TOKEN", "")
    if not base:
        sys.exit("Définis WATT_API_BASE (ex: https://web-production-e30c8c.up.railway.app).")

    # Pas de token sous la main ? On se connecte avec email + mot de passe
    # du compte Smyle (POST /auth/login → access_token). Aucun token à copier
    # depuis le navigateur. (Renseigne WATT_EMAIL et WATT_PASSWORD.)
    if not token:
        import getpass
        email = os.environ.get("WATT_EMAIL", "").strip()
        pwd = os.environ.get("WATT_PASSWORD", "")
        # Si absent OU si c'est encore le texte d'exemple → on demande à l'écran.
        if (not email) or ("exemple" in email) or ("@" not in email):
            email = input("Email du compte WATT (propriétaire des sons) : ").strip()
        if (not pwd) or (pwd == "tonvraimotdepasse"):
            pwd = getpass.getpass("Mot de passe : ")
        if not (email and pwd):
            sys.exit("Email + mot de passe requis.")
        lr = requests.post(f"{base}/auth/login",
                           json={"email": email, "password": pwd}, timeout=30)
        if lr.status_code >= 300:
            sys.exit(f"Login échoué : {lr.status_code} {lr.text[:160]}")
        token = lr.json().get("access_token", "")
        if not token:
            sys.exit("Login OK mais pas d'access_token dans la réponse.")
        print("✅ Connecté via /auth/login.\n")
    H = {"Authorization": f"Bearer {token}"}

    folder = Path(args.covers).expanduser()
    if not folder.is_dir():
        sys.exit(f"Dossier introuvable : {folder}")
    covers = [p for p in folder.iterdir()
              if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    if not covers:
        sys.exit("Aucune image dans le dossier.")

    # 1) Récupère les tracks de l'utilisateur (propriétaire des sons Night City)
    r = requests.get(f"{base}/tracks/me", headers=H, timeout=30)
    r.raise_for_status()
    tracks = r.json()
    by_norm = {}
    for t in tracks:
        title = t.get("title") or t.get("name") or ""
        by_norm[norm(title)] = t
    print(f"{len(tracks)} sons trouvés sur le compte · {len(covers)} covers dans le dossier\n")

    plan, unmatched = [], []
    for cov in sorted(covers):
        key = norm(cov.name)
        t = by_norm.get(key)
        if not t:
            # match partiel de secours
            cand = [v for k, v in by_norm.items() if k and (k in key or key in k)]
            t = cand[0] if len(cand) == 1 else None
        if t:
            plan.append((cov, t))
        else:
            unmatched.append(cov)

    print("=== PLAN ===")
    for cov, t in plan:
        has = "（cover déjà présente）" if (t.get("cover_url") or t.get("coverUrl")) else ""
        print(f"  {cov.name:38s} → {t.get('title') or t.get('name')}  {has}")
    if unmatched:
        print("\n⚠️  NON MATCHÉS (à régler) :")
        for cov in unmatched:
            print(f"  {cov.name}")

    if not args.execute:
        print("\nDRY-RUN — rien n'a été écrit. Relance avec --execute pour appliquer.")
        return 0

    # 2) + 3) Upload R2 puis PATCH cover_url
    print("\n=== EXÉCUTION ===")
    ok = 0
    for cov, t in plan:
        tid = t.get("id")
        if (t.get("cover_url") or t.get("coverUrl")) and not args.overwrite:
            print(f"  ⏭  {t.get('title')} a déjà une cover (utilise --overwrite)")
            continue
        with open(cov, "rb") as fh:
            up = requests.post(
                f"{base}/watt/upload-image",
                headers=H,
                files={"file": (cov.name, fh, "image/png")},
                data={"kind": "track-cover"},
                timeout=120,
            )
        if up.status_code >= 300:
            print(f"  ❌ upload {cov.name}: {up.status_code} {up.text[:120]}")
            continue
        cover_url = up.json().get("cover_url")
        pat = requests.patch(
            f"{base}/tracks/{tid}", headers=H, json={"cover_url": cover_url}, timeout=30
        )
        if pat.status_code >= 300:
            print(f"  ❌ patch {t.get('title')}: {pat.status_code} {pat.text[:120]}")
            continue
        print(f"  ✅ {t.get('title')} ← {cov.name}")
        ok += 1
    print(f"\nTerminé : {ok}/{len(plan)} covers attachées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
