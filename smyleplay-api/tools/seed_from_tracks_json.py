"""
Étape 1 du plan de migration Flask → FastAPI.

Ce script importe le catalogue `tracks.json` du site Flask (82 tracks
répartis en 4 univers) dans la base PostgreSQL du backend FastAPI.

Rien n'est modifié côté Flask. Ce script est idempotent : si tu le
relances, il met à jour les tracks existantes (match par `r2_key`) au
lieu de créer des doublons.

Usage (depuis la racine `smyleplay-api/`) :

    # 1. Démarrer Postgres + appliquer les migrations
    docker-compose up -d db
    docker-compose run --rm api alembic upgrade head

    # 2. Lancer le seed
    docker-compose run --rm api python tools/seed_from_tracks_json.py \
        --tracks-json /app/../tracks.json

    # Ou en dry-run pour voir ce qui serait fait sans rien écrire :
    docker-compose run --rm api python tools/seed_from_tracks_json.py \
        --tracks-json /app/../tracks.json --dry-run

Ce que fait le script :

    1. Crée 4 "utilisateurs-univers" (un par univers) s'ils n'existent pas :
         - sunset-lover@smyleplay.local  (artist_name = "SUNSET LOVER")
         - jungle-osmose@smyleplay.local (artist_name = "JUNGLE OSMOSE")
         - night-city@smyleplay.local    (artist_name = "NIGHT CITY")
         - hit-mix@smyleplay.local       (artist_name = "HIT MIX")
       Ces users ont un password_hash bidon qu'il est impossible de
       matcher (pas de login possible). Ils servent juste d'artist_id
       pour les tracks curatées du catalogue v1.

    2. Pour chaque track de tracks.json :
         - si `r2_key` existe déjà en base → on met à jour les champs
         - sinon → on crée une nouvelle ligne

    3. Affiche un résumé (créés / mis à jour / ignorés).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

# ── Bootstrap sys.path ────────────────────────────────────────────────────
# Ce script vit dans `smyleplay-api/tools/` mais a besoin d'importer le
# package `app.*` situé dans `smyleplay-api/app/`. Quand on lance
# `python tools/seed_from_tracks_json.py`, Python ajoute uniquement
# `tools/` à sys.path. On remonte d'un cran pour que `import app` marche.
_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

import bcrypt  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.track import Track  # noqa: E402
from app.models.user import User  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────

UNIVERSES = {
    "sunset-lover": {
        "email": "sunset-lover@smyleplay.local",
        "artist_name": "SUNSET LOVER",
        "brand_color": "#FF9500",
    },
    "jungle-osmose": {
        "email": "jungle-osmose@smyleplay.local",
        "artist_name": "JUNGLE OSMOSE",
        "brand_color": "#00E676",
    },
    "night-city": {
        "email": "night-city@smyleplay.local",
        "artist_name": "NIGHT CITY",
        "brand_color": "#2266FF",
    },
    "hit-mix": {
        "email": "hit-mix@smyleplay.local",
        "artist_name": "HIT MIX",
        "brand_color": "#AA00FF",
    },
}

# Hash d'un mot de passe impossible à deviner : ces comptes-univers ne sont
# PAS destinés à être utilisés pour se connecter. Ils existent uniquement
# pour être propriétaires (artist_id) des tracks curatées v1.
IMPOSSIBLE_PASSWORD_HASH = bcrypt.hashpw(
    b"__seed_only_no_login__",
    bcrypt.gensalt(),
).decode("utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def r2_key_from_url(url: str) -> str:
    """
    Extrait la clé R2 depuis l'URL publique.

      https://pub-XXX.r2.dev/SUNSET%20LOVER/sw-001%20...%20Drift.wav
      → "SUNSET LOVER/sw-001 — AMBER DRIVE Drift.wav"
    """
    parsed = urlparse(url)
    return unquote(parsed.path.lstrip("/"))


async def get_or_create_universe_user(
    session: AsyncSession,
    universe_slug: str,
    dry_run: bool = False,
) -> User | None:
    """Retourne le User-univers, le crée si manquant."""
    cfg = UNIVERSES[universe_slug]
    stmt = select(User).where(User.email == cfg["email"])
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        return user

    if dry_run:
        print(f"   [dry-run] would create user {cfg['email']}")
        return None

    user = User(
        email=cfg["email"],
        password_hash=IMPOSSIBLE_PASSWORD_HASH,
        artist_name=cfg["artist_name"],
        brand_color=cfg["brand_color"],
        language="fr",
        credits_balance=0,
        credits_earned_total=0,
    )
    session.add(user)
    await session.flush()
    print(f"   ✓ created universe user: {cfg['email']} (id={user.id})")
    return user


async def upsert_track(
    session: AsyncSession,
    track_data: dict,
    universe_slug: str,
    artist_user: User,
    dry_run: bool = False,
) -> str:
    """
    Insère ou met à jour une track. Match par r2_key (unique par fichier R2).

    Retourne "created" | "updated" | "skipped".
    """
    url = track_data.get("url", "")
    title = track_data.get("name", "").strip() or "Untitled"
    duration = track_data.get("duration")
    legacy_id = track_data.get("id") or None
    r2_key = r2_key_from_url(url) if url else None

    if not r2_key:
        return "skipped"

    # Chercher une track existante par r2_key
    stmt = select(Track).where(Track.r2_key == r2_key)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        if dry_run:
            return "updated"
        existing.title = title
        existing.audio_url = url
        existing.universe = universe_slug
        existing.duration_seconds = duration
        existing.artist_id = artist_user.id
        existing.legacy_id = legacy_id
        return "updated"

    if dry_run:
        return "created"

    track = Track(
        title=title,
        audio_url=url,
        artist_id=artist_user.id,
        universe=universe_slug,
        duration_seconds=duration,
        r2_key=r2_key,
        plays=0,
        legacy_id=legacy_id,
    )
    session.add(track)
    return "created"


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

async def run(tracks_json_path: Path, dry_run: bool) -> int:
    if not tracks_json_path.exists():
        print(f"❌ tracks.json introuvable : {tracks_json_path}", file=sys.stderr)
        return 2

    with tracks_json_path.open(encoding="utf-8") as f:
        catalog = json.load(f)

    total_created = 0
    total_updated = 0
    total_skipped = 0

    async with SessionLocal() as session:
        for universe_slug, data in catalog.items():
            if universe_slug not in UNIVERSES:
                print(f"⚠️  univers inconnu ignoré : {universe_slug}")
                continue

            tracks = data.get("tracks", [])
            print(f"\n▸ {universe_slug} : {len(tracks)} tracks à traiter")

            artist_user = await get_or_create_universe_user(
                session, universe_slug, dry_run
            )
            if artist_user is None and not dry_run:
                print(f"   ❌ impossible d'obtenir l'artist user pour {universe_slug}")
                continue

            for t in tracks:
                outcome = await upsert_track(
                    session,
                    t,
                    universe_slug,
                    artist_user,  # type: ignore[arg-type]
                    dry_run,
                )
                if outcome == "created":
                    total_created += 1
                elif outcome == "updated":
                    total_updated += 1
                else:
                    total_skipped += 1

        if dry_run:
            print("\n[dry-run] rollback (aucun changement persisté)")
            await session.rollback()
        else:
            await session.commit()

    print("\n" + "=" * 50)
    print(f"Créés   : {total_created}")
    print(f"MAJ     : {total_updated}")
    print(f"Ignorés : {total_skipped}")
    print(f"Total   : {total_created + total_updated + total_skipped}")
    print("=" * 50)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tracks-json",
        type=Path,
        required=True,
        help="Chemin vers le fichier tracks.json côté Flask.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche ce qui serait fait sans rien écrire.",
    )
    args = parser.parse_args()

    rc = asyncio.run(run(args.tracks_json, args.dry_run))
    sys.exit(rc)


if __name__ == "__main__":
    main()
