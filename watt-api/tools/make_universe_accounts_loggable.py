"""
Rend connectables les 4 comptes-univers curatés (v1).

CONTEXTE
────────
Les sons curatés (ex. "Calm Rain") appartiennent à des comptes-univers
synthétiques créés par `seed_from_tracks_json.py` :

    - sunset-lover@smyleplay.local   → SUNSET LOVER
    - jungle-osmose@smyleplay.local  → JUNGLE OSMOSE
    - night-city@smyleplay.local     → NIGHT CITY
    - hit-mix@smyleplay.local        → HIT MIX

Le seed leur posait un `password_hash` BIDON (impossible à matcher), donc
personne ne pouvait s'y connecter → impossible d'éditer leurs sons
(cover, recette/prompt) depuis le dashboard, car `PATCH /tracks/{id}`
exige `Track.artist_id == current_user.id`.

CE QUE FAIT CE SCRIPT
─────────────────────
Pour chacun des 4 comptes existants :
  1. Pose un VRAI mot de passe bcrypt (connexion possible).
  2. Force `profile_public = True` (profil + covers visibles publiquement).

Idempotent : relancer ne fait que (re)poser le mot de passe.
Ne crée PAS les comptes manquants — lancer `seed_from_tracks_json.py`
d'abord si un compte n'existe pas encore.

MOT DE PASSE
────────────
- Par défaut : un seul mot de passe partagé par les 4 comptes, soit lu
  depuis la variable d'env WATT_UNIVERSE_PASSWORD, soit généré
  aléatoirement (affiché en clair en fin d'exécution).
- Pour fixer le tien :  WATT_UNIVERSE_PASSWORD="MonMotDePasse" python tools/make_universe_accounts_loggable.py

USAGE
─────
    # Dry-run (n'écrit rien, montre ce qui changerait) :
    python tools/make_universe_accounts_loggable.py --dry-run

    # Exécution réelle (mot de passe généré) :
    python tools/make_universe_accounts_loggable.py

    # Exécution avec ton propre mot de passe :
    WATT_UNIVERSE_PASSWORD="…" python tools/make_universe_accounts_loggable.py

Le script lit DATABASE_URL via app.config (settings) : il marche donc
aussi bien en Docker local qu'en prod (Railway), tant qu'il est lancé
dans l'environnement où DATABASE_URL pointe sur la bonne base.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import string
import sys
from pathlib import Path

# ── Bootstrap sys.path (même logique que seed_from_tracks_json.py) ─────────
_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.users import hash_password  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# Comptes-univers ciblés (miroir de UNIVERSES dans seed_from_tracks_json.py)
# ──────────────────────────────────────────────────────────────────────────
UNIVERSE_ACCOUNTS = [
    ("sunset-lover@smyleplay.local", "SUNSET LOVER"),
    ("jungle-osmose@smyleplay.local", "JUNGLE OSMOSE"),
    ("night-city@smyleplay.local", "NIGHT CITY"),
    ("hit-mix@smyleplay.local", "HIT MIX"),
]


def _generate_password(length: int = 16) -> str:
    """Mot de passe robuste, sans caractères ambigus."""
    alphabet = string.ascii_letters + string.digits + "!@#$%-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def run(password: str, dry_run: bool) -> None:
    hashed = hash_password(password)
    results: list[tuple[str, str, str]] = []  # (email, artist_name, status)

    async with SessionLocal() as session:
        for email, artist_name in UNIVERSE_ACCOUNTS:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if user is None:
                results.append((email, artist_name, "ABSENT (lance le seed d'abord)"))
                continue

            if dry_run:
                results.append((email, artist_name, "would update (password + profile_public)"))
                continue

            user.password_hash = hashed
            user.profile_public = True
            results.append((email, artist_name, "updated"))

        if not dry_run:
            await session.commit()

    # ── Résumé ────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  COMPTES-UNIVERS — réactivation login")
    print("=" * 70)
    for email, artist_name, status in results:
        print(f"  {artist_name:<14} {email:<32} → {status}")
    print("-" * 70)

    updated = [r for r in results if r[2] == "updated"]
    absent = [r for r in results if r[2].startswith("ABSENT")]

    if dry_run:
        print("  DRY-RUN : aucune écriture effectuée.")
    elif updated:
        print()
        print("  ✅ IDENTIFIANTS DE CONNEXION (note-les, le mot de passe")
        print("     n'est PAS récupérable ensuite) :")
        print()
        print(f"     Mot de passe (commun aux 4 comptes) : {password}")
        print()
        print("     Connecte-toi sur chaque profil avec son email ci-dessus")
        print("     + ce mot de passe, puis édite covers & recettes via le")
        print("     dashboard (« Modifier un son »).")
    if absent:
        print()
        print("  ⚠️  Comptes absents : lance d'abord")
        print("     python tools/seed_from_tracks_json.py")
    print("=" * 70)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'écrit rien, affiche seulement ce qui changerait.",
    )
    args = parser.parse_args()

    password = os.environ.get("WATT_UNIVERSE_PASSWORD") or _generate_password()
    asyncio.run(run(password=password, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
