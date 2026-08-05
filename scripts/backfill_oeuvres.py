#!/usr/bin/env python3
"""
backfill_oeuvres.py — Transforme les COVERS existantes en IMAGES VENDABLES
(avec leur vraie recette issue des PROMPT_LIBRARY) puis les LIE au bon SON →
tes œuvres deviennent réelles (bouton « 💠 Œuvre −10 % » côté acheteur).

Pour chaque cover d'un dossier :
  1. Match la cover ↔ un SON (par titre normalisé) via GET /tracks/me.
  2. Match la cover ↔ sa RECETTE (par titre) dans la PROMPT_LIBRARY *_PUBLIC.md.
  3. Crée l'image vendable : POST /artist/me/images (multipart, prompt_text = la
     recette, is_published=true, price = --price).
  4. Lie l'image au son : POST /artist/me/prompts/{track.prompt_id}/link.

⚠️ DRY-RUN par défaut : affiche le plan, n'écrit RIEN. Ajoute --execute pour appliquer.

Pré-requis (env) :
  WATT_API_BASE   ex: https://web-production-e30c8c.up.railway.app
  Auth : WATT_TOKEN (Bearer) OU WATT_EMAIL + WATT_PASSWORD (login auto).

Provenance image (obligatoire côté API) :
  --platform       midjourney | dalle | stable_diffusion | flux | autre  (défaut: autre)
  --model-version  ex: "v6.1", "GPT-4o", "1.0"                            (défaut: "1.0")
  --price          prix fixe de chaque image en Smyles                    (défaut: 30)

Exemples (un univers = un dossier + sa library) :
  WATT_API_BASE=... WATT_TOKEN=... python3 scripts/backfill_oeuvres.py \
    --covers "/chemin/vers/covers/night-city" \
    --library "OBSIDIAN/02_WATT/ADN_VISUEL/PROMPT_LIBRARY_Night-City_PUBLIC.md" \
    --platform midjourney --model-version v6.1 --price 30
  # puis, quand le plan est bon :
  ... --execute
"""
from __future__ import annotations

import argparse
import difflib
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
    """Normalise pour matcher cover ↔ titre ↔ library : minuscule, sans accents,
    sans extension, sans 'cover'/'civer', sans ponctuation ni espaces, et on
    coupe tout ce qui suit un ' · ' (la ville) ou un '—' (préfixe numéro)."""
    s = s or ""
    # coupe préfixe "NN — " et suffixe " · City"
    if "—" in s:
        s = s.split("—", 1)[1]
    if "·" in s:
        s = s.split("·", 1)[0]
    s = s.lower()
    s = re.sub(r"\.(png|jpg|jpeg|webp|wav|mp3|m4a|flac)$", "", s)
    # Bruits de nommage à ignorer pour le match cover ↔ son ↔ track :
    #   'cover'/'civer' (fichiers image), 'drift' (suffixe des masters),
    #   'sw-001'/'sw001' (préfixe des masters), 's' de pluriel parasite géré
    #   par le repli flou difflib.
    for junk in ("cover", "civer", "drift", "sw-001", "sw001"):
        s = s.replace(junk, "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def parse_library(md_path: Path) -> dict[str, str]:
    """Parse une PROMPT_LIBRARY *_PUBLIC.md → { norm(nom): recette }.
    Chaque entrée = un header '## NN — NOM · Ville' suivi d'une ligne '> recette'."""
    if not md_path.is_file():
        sys.exit(f"Library introuvable : {md_path}")
    recipes: dict[str, str] = {}
    cur_name = None
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            cur_name = norm(line[3:])
        elif line.startswith(">") and cur_name:
            txt = line.lstrip("> ").strip()
            if txt and not txt.startswith("**"):  # ignore les notes en gras
                recipes[cur_name] = txt
                cur_name = None
    return recipes


def _login(base: str) -> str:
    token = os.environ.get("WATT_TOKEN", "")
    if token:
        return token
    import getpass
    email = os.environ.get("WATT_EMAIL", "").strip()
    pwd = os.environ.get("WATT_PASSWORD", "")
    if (not email) or ("@" not in email):
        email = input("Email du compte WATT (propriétaire des sons) : ").strip()
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
    ap.add_argument("--covers", required=True, help="Dossier des covers")
    ap.add_argument("--library", required=True, help="Fichier PROMPT_LIBRARY *_PUBLIC.md")
    ap.add_argument("--platform", default="autre",
                    choices=["midjourney", "dalle", "stable_diffusion", "flux", "autre"])
    ap.add_argument("--model-version", default="1.0")
    ap.add_argument("--price", type=int, default=30)
    ap.add_argument("--execute", action="store_true", help="Écrit réellement (sinon dry-run)")
    args = ap.parse_args()

    base = os.environ.get("WATT_API_BASE", "").rstrip("/")
    if not base:
        sys.exit("Définis WATT_API_BASE.")
    token = _login(base)
    H = {"Authorization": f"Bearer {token}"}

    folder = Path(args.covers).expanduser()
    if not folder.is_dir():
        sys.exit(f"Dossier covers introuvable : {folder}")
    covers = [p for p in folder.iterdir()
              if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    if not covers:
        sys.exit("Aucune image dans le dossier.")

    recipes = parse_library(Path(args.library).expanduser())
    print(f"{len(recipes)} recettes dans la library · {len(covers)} covers\n")

    # Sons de l'utilisateur + leur recette (prompt_id) à lier.
    r = requests.get(f"{base}/tracks/me", headers=H, timeout=30)
    r.raise_for_status()
    tracks = r.json()
    if isinstance(tracks, dict):
        tracks = tracks.get("items") or tracks.get("tracks") or []
    by_norm = {norm(t.get("title") or t.get("name") or ""): t for t in tracks}
    print(f"{len(tracks)} sons trouvés sur ce compte.")
    if tracks:
        sample = [t.get("title") or t.get("name") for t in tracks[:12]]
        print("   Exemples de titres :", ", ".join(str(s) for s in sample))

    # Anti-doublon : prompts déjà liés à une image (linked_prompt_id) → on
    # skippera les sons dont la recette a déjà une face visuelle (re-run safe).
    linked_prompt_ids = set()
    try:
        pr = requests.get(f"{base}/artist/me/prompts", headers=H, timeout=30)
        items = pr.json()
        if isinstance(items, dict):
            items = items.get("items") or []
        for p in items:
            if p.get("linked_prompt_id") or p.get("linkedPromptId"):
                linked_prompt_ids.add(str(p.get("id") or p.get("prompt_id")))
    except Exception:
        pass

    def _match(key: str, d: dict):
        """Exact → sous-chaîne → flou (difflib, seuil 0.85, sans faux positif)."""
        if key in d:
            return d[key]
        sub = [v for k, v in d.items() if k and (k in key or key in k)]
        if len(sub) == 1:
            return sub[0]
        close = difflib.get_close_matches(key, list(d.keys()), n=1, cutoff=0.85)
        return d[close[0]] if close else None

    plan, skipped = [], []
    for cov in sorted(covers):
        key = norm(cov.name)
        track = _match(key, by_norm)
        recipe = _match(key, recipes)
        if not track:
            skipped.append((cov.name, "aucun son ne matche ce titre"))
        elif not track.get("prompt_id"):
            skipped.append((cov.name, "le son n'a pas de recette (prompt_id) à lier"))
        elif str(track.get("prompt_id")) in linked_prompt_ids:
            skipped.append((cov.name, "œuvre déjà liée (skip anti-doublon)"))
        elif not recipe:
            skipped.append((cov.name, "aucune recette dans la library"))
        else:
            plan.append((cov, track, recipe))

    print("=== PLAN ===")
    for cov, t, rec in plan:
        print(f"  {cov.name:34s} → « {t.get('title') or t.get('name')} »  (recette {len(rec)} car.)")
    if skipped:
        print("\n⚠️  IGNORÉS :")
        for name, why in skipped:
            print(f"  {name:34s} — {why}")

    print(f"\nProvenance: platform={args.platform} · version={args.model_version} · prix={args.price} S")
    if not args.execute:
        print("\nDRY-RUN — rien écrit. Relance avec --execute pour appliquer.")
        return 0

    print("\n=== EXÉCUTION ===")
    ok = 0
    for cov, t, rec in plan:
        title = (t.get("title") or t.get("name") or cov.stem)[:120]
        if len(title) < 5:  # contrainte API : titre image ≥ 5 caractères
            title = f"{title} — visuel"
        # 1) Créer l'image vendable (multipart) avec sa vraie recette.
        with open(cov, "rb") as fh:
            cr = requests.post(
                f"{base}/artist/me/images",
                headers=H,
                data={
                    "title": title,
                    "image_platform": args.platform,
                    "image_model_version": args.model_version,
                    "prompt_text": rec,
                    "ratio": "1:1",
                    "price_credits": str(args.price),
                    "is_published": "true",
                },
                files={"file": (cov.name, fh, "image/png")},
                timeout=180,
            )
        if cr.status_code >= 300:
            print(f"  ❌ image « {title} » : {cr.status_code} {cr.text[:140]}")
            continue
        img = cr.json()
        img_id = img.get("id") or img.get("imageId") or img.get("prompt_id")
        if not img_id:
            print(f"  ❌ « {title} » : image créée mais pas d'id → {str(img)[:120]}")
            continue
        # 2) Lier l'image à la recette du son → œuvre.
        lk = requests.post(
            f"{base}/artist/me/prompts/{t['prompt_id']}/link",
            headers=H,
            json={"other_prompt_id": img_id, "bundle_exclusive": False},
            timeout=30,
        )
        if lk.status_code == 409:
            print(f"  ⏭  « {title} » : déjà liée (image créée id={img_id}).")
            ok += 1
            continue
        if lk.status_code >= 300:
            print(f"  ⚠️  « {title} » : image OK (id={img_id}) mais lien KO {lk.status_code} {lk.text[:120]}")
            continue
        print(f"  ✅ « {title} » — image vendable + œuvre liée")
        ok += 1

    print(f"\nTerminé : {ok}/{len(plan)} œuvres backfillées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
