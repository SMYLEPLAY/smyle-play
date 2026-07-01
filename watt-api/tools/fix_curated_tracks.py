"""
Diagnostique et répare les sons curatés (v1) côté DB.

PROBLÈME RÉSOLU
───────────────
Certains sons curatés s'affichent sur le profil public (lus depuis
`tracks.json`) mais n'ont PAS de ligne éditable en base — soit jamais
semés, soit soft-deleted, soit rattachés au mauvais propriétaire. Du
coup le dashboard ne peut pas les modifier (pas dans /tracks/me, ou
PATCH /tracks/{id} en 404). Symptôme typique : un son d'un univers est
éditable, son voisin du même univers ne l'est pas (ex. Calm Rain OK,
Caraibes KO — tous deux sous JUNGLE OSMOSE).

CE QUE FAIT CE SCRIPT
─────────────────────
Pour chaque son de `tracks.json` (filtrable par univers / par nom) :
  - le retrouve en DB par r2_key (clé unique du fichier R2) ;
  - rapporte son état : présent ? supprimé ? bon propriétaire ?
    a déjà une cover / un prompt ?

Avec --apply, il RÉPARE de façon idempotente :
  - son manquant            → le crée sous le bon user-univers ;
  - son soft-deleted        → is_deleted = False ;
  - mauvais propriétaire    → réassigne artist_id au user-univers.
Il ne touche JAMAIS la cover, le prompt, le titre déjà en place.

PRÉ-REQUIS
──────────
Les user-univers doivent exister et être connectables : lancer d'abord
`make_universe_accounts_loggable.py` si besoin.

USAGE
─────
    # Rapport complet (lecture seule) :
    python tools/fix_curated_tracks.py

    # Cibler un univers / un son :
    python tools/fix_curated_tracks.py --universe jungle-osmose
    python tools/fix_curated_tracks.py --name Caraibes

    # Réparer pour de vrai :
    python tools/fix_curated_tracks.py --name Caraibes --apply
    python tools/fix_curated_tracks.py --universe jungle-osmose --apply

Lit DATABASE_URL via app.config → marche en local (venv) comme en prod
(Railway), tant qu'il est lancé là où DATABASE_URL pointe sur la base.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

# ── Bootstrap sys.path (même logique que les autres scripts tools/) ────────
_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.track import Track  # noqa: E402
from app.models.user import User  # noqa: E402

# Emails des comptes-univers (miroir de seed_from_tracks_json.py).
UNIVERSE_EMAIL = {
    "sunset-lover": "sunset-lover@smyleplay.local",
    "jungle-osmose": "jungle-osmose@smyleplay.local",
    "night-city": "night-city@smyleplay.local",
    "hit-mix": "hit-mix@smyleplay.local",
}

# tracks.json vit à la racine du repo (un cran au-dessus de watt-api/).
TRACKS_JSON = _API_ROOT.parent / "tracks.json"


def _r2_key_from_url(url: str) -> str | None:
    if not url:
        return None
    return unquote(urlparse(url).path.lstrip("/")) or None


def _norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


async def run(universe: str | None, name: str | None, apply: bool) -> None:
    data = json.loads(TRACKS_JSON.read_text(encoding="utf-8"))

    rows: list[dict] = []
    for slug, info in data.items():
        if universe and slug != universe:
            continue
        for t in info.get("tracks", []):
            if name and _norm(name) not in _norm(t.get("name", "")):
                continue
            rows.append({"slug": slug, "track": t})

    if not rows:
        print("Aucun son ne correspond au filtre.")
        return

    report: list[tuple] = []  # (name, slug, etat, action)

    async with SessionLocal() as session:
        # Cache des user-univers
        users: dict[str, User | None] = {}
        for slug in {r["slug"] for r in rows}:
            email = UNIVERSE_EMAIL.get(slug)
            users[slug] = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none() if email else None

        for r in rows:
            slug, t = r["slug"], r["track"]
            nm = t.get("name", "?")
            url = t.get("url") or t.get("url_alt") or ""
            r2_key = _r2_key_from_url(url)
            owner = users.get(slug)

            if owner is None:
                report.append((nm, slug, "USER-UNIVERS ABSENT", "—"))
                continue
            if not r2_key:
                report.append((nm, slug, "URL invalide (pas de r2_key)", "skip"))
                continue

            track = (
                await session.execute(select(Track).where(Track.r2_key == r2_key))
            ).scalar_one_or_none()

            # Diagnostic
            if track is None:
                etat = "ABSENT en DB"
            elif track.is_deleted:
                etat = "soft-deleted"
            elif track.artist_id != owner.id:
                etat = "mauvais propriétaire"
            else:
                cov = "cover✓" if track.cover_url else "cover✗"
                pr = "prompt✓" if track.prompt_id else "prompt✗"
                etat = f"OK éditable ({cov} {pr})"

            # Réparation
            action = "—"
            if track is None:
                action = "à créer"
                if apply:
                    session.add(Track(
                        title=t.get("name", "Untitled").strip() or "Untitled",
                        audio_url=url,
                        artist_id=owner.id,
                        universe=slug,
                        duration_seconds=t.get("duration"),
                        r2_key=r2_key,
                        legacy_id=t.get("id") or None,
                        plays=0,
                        is_deleted=False,
                    ))
                    action = "CRÉÉ"
            elif track.is_deleted:
                action = "à restaurer"
                if apply:
                    track.is_deleted = False
                    if track.artist_id != owner.id:
                        track.artist_id = owner.id
                    action = "RESTAURÉ"
            elif track.artist_id != owner.id:
                action = "à réassigner"
                if apply:
                    track.artist_id = owner.id
                    action = "RÉASSIGNÉ"

            report.append((nm, slug, etat, action))

        if apply:
            await session.commit()

    # ── Affichage ──────────────────────────────────────────────────────────
    print()
    print("=" * 84)
    print(f"  SONS CURATÉS — {'RÉPARATION (--apply)' if apply else 'DIAGNOSTIC (lecture seule)'}")
    print("=" * 84)
    print(f"  {'SON':<22}{'UNIVERS':<16}{'ÉTAT':<30}{'ACTION'}")
    print("-" * 84)
    for nm, slug, etat, action in report:
        print(f"  {nm[:21]:<22}{slug:<16}{etat:<30}{action}")
    print("-" * 84)
    n_fix = sum(1 for *_, a in report if a not in ("—", "skip"))
    if apply:
        print(f"  {n_fix} son(s) réparé(s). Recharge le dashboard puis édite-les.")
    else:
        if n_fix:
            print(f"  {n_fix} son(s) à réparer. Relance avec --apply pour corriger.")
        else:
            print("  Rien à réparer — tous les sons filtrés sont déjà éditables.")
    print("=" * 84)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", help="Slug d'univers (ex. jungle-osmose).")
    parser.add_argument("--name", help="Filtre sur le nom du son (sous-chaîne, accents ignorés).")
    parser.add_argument("--apply", action="store_true", help="Applique les réparations (sinon lecture seule).")
    args = parser.parse_args()
    asyncio.run(run(universe=args.universe, name=args.name, apply=args.apply))


if __name__ == "__main__":
    main()
