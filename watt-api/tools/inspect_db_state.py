"""
Inspection LECTURE SEULE de l'état réel de la base.

But : comprendre qui possède les sons curatés et lesquels existent
vraiment en base, sans rien modifier. Lit DATABASE_URL via app.config
(donc la base pointée par watt-api/.env).

USAGE
─────
    python tools/inspect_db_state.py                  # vue d'ensemble
    python tools/inspect_db_state.py --universe jungle-osmose
    python tools/inspect_db_state.py --find Caraibes  # cherche un titre
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import select, func  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.track import Track  # noqa: E402
from app.models.user import User  # noqa: E402


async def run(universe: str | None, find: str | None) -> None:
    async with SessionLocal() as session:
        # ── Users ────────────────────────────────────────────────────────
        users = (await session.execute(select(User))).scalars().all()
        by_id = {u.id: u for u in users}
        print()
        print("=" * 78)
        print(f"  USERS ({len(users)})")
        print("=" * 78)
        print(f"  {'EMAIL':<38}{'ARTIST':<18}{'PUBLIC':<8}{'OFFICIAL'}")
        print("-" * 78)
        for u in sorted(users, key=lambda x: (x.email or "")):
            print(f"  {(u.email or '')[:37]:<38}{(u.artist_name or '')[:17]:<18}"
                  f"{str(bool(u.profile_public)):<8}{bool(u.is_official)}")

        # ── Tracks par universe ──────────────────────────────────────────
        rows = (await session.execute(
            select(Track.universe, func.count())
            .group_by(Track.universe)
        )).all()
        print()
        print("=" * 78)
        print("  TRACKS PAR UNIVERSE (toutes, y compris supprimées)")
        print("=" * 78)
        for univ, n in sorted(rows, key=lambda r: (r[0] or "")):
            print(f"  {str(univ):<24} {n}")

        # ── Détail d'un universe ─────────────────────────────────────────
        if universe:
            tracks = (await session.execute(
                select(Track).where(Track.universe == universe)
                .order_by(Track.title)
            )).scalars().all()
            print()
            print("=" * 96)
            print(f"  DÉTAIL UNIVERSE = {universe}  ({len(tracks)} tracks)")
            print("=" * 96)
            print(f"  {'TITRE':<22}{'OWNER EMAIL':<34}{'DEL':<5}{'COVER':<7}{'PROMPT':<8}{'LEGACY_ID'}")
            print("-" * 96)
            for t in tracks:
                owner = by_id.get(t.artist_id)
                oe = (owner.email if owner else f"?{t.artist_id}")[:33]
                print(f"  {(t.title or '')[:21]:<22}{oe:<34}"
                      f"{('Y' if t.is_deleted else '-'):<5}"
                      f"{('Y' if t.cover_url else '-'):<7}"
                      f"{('Y' if t.prompt_id else '-'):<8}"
                      f"{t.legacy_id or ''}")

        # ── Recherche par titre ──────────────────────────────────────────
        if find:
            tracks = (await session.execute(
                select(Track).where(Track.title.ilike(f"%{find}%"))
            )).scalars().all()
            print()
            print("=" * 96)
            print(f"  RECHERCHE TITRE ~ '{find}'  ({len(tracks)} résultats)")
            print("=" * 96)
            print(f"  {'TITRE':<22}{'UNIVERS':<16}{'OWNER EMAIL':<34}{'DEL':<5}{'COVER':<7}{'PROMPT'}")
            print("-" * 96)
            for t in tracks:
                owner = by_id.get(t.artist_id)
                oe = (owner.email if owner else f"?{t.artist_id}")[:33]
                print(f"  {(t.title or '')[:21]:<22}{str(t.universe or '')[:15]:<16}{oe:<34}"
                      f"{('Y' if t.is_deleted else '-'):<5}"
                      f"{('Y' if t.cover_url else '-'):<7}"
                      f"{('Y' if t.prompt_id else '-')}")
        print()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", help="Détaille un univers (ex. jungle-osmose).")
    p.add_argument("--find", help="Cherche les tracks dont le titre contient ce texte.")
    args = p.parse_args()
    asyncio.run(run(universe=args.universe, find=args.find))


if __name__ == "__main__":
    main()
