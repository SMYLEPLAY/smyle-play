"""
Accorde (ou retire) le rôle d'administration à un compte, par email.

K-01 / annexe B §2 (tâche B-M2). `users.is_admin` n'est exposé en write par
aucun endpoint — c'est volontaire : le droit d'administration se pose depuis
la machine d'ops, jamais depuis l'API. Ce script est la voie officielle.
Idempotent : rejouer la commande ne change rien et le dit.

USAGE
─────
    python tools/make_admin.py tom@example.com          # accorde
    python tools/make_admin.py tom@example.com --revoke # retire
    python tools/make_admin.py --list                   # liste les admins

Lit DATABASE_URL via app.config (donc la base pointée par watt-api/.env).
Sortie : 0 si l'état demandé est atteint, 1 si le compte est introuvable.
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

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


async def list_admins() -> int:
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(User).where((User.is_admin.is_(True)) | (User.is_official.is_(True)))
            )
        ).scalars().all()
    if not rows:
        print("Aucun compte administrateur.")
        return 0
    print(f"{len(rows)} compte(s) avec droit d'administration :")
    for u in sorted(rows, key=lambda x: (x.email or "")):
        flags = []
        if u.is_admin:
            flags.append("is_admin")
        if u.is_official:
            flags.append("is_official")
        print(f"  - {u.email}  ({', '.join(flags)})  id={u.id}")
    return 0


async def set_admin(email: str, value: bool) -> int:
    target = (email or "").strip().lower()
    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == target))
        ).scalars().first()
        if user is None:
            print(f"ERREUR : aucun compte avec l'email {target!r}.", file=sys.stderr)
            return 1
        before = bool(user.is_admin)
        if before == value:
            # Idempotent : on le dit, on ne réécrit pas.
            etat = "déjà administrateur" if value else "déjà non-administrateur"
            print(f"{target} : {etat} (is_admin={before}) — rien à faire.")
        else:
            user.is_admin = value
            await db.commit()
            print(f"{target} : is_admin {before} → {value}. OK.")
        print(
            f"  id={user.id}  is_admin={bool(user.is_admin)}  "
            f"is_official={bool(user.is_official)}  banni={bool(user.is_banned)}"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Rôle d'administration WATT (is_admin).")
    ap.add_argument("email", nargs="?", help="Email du compte cible.")
    ap.add_argument("--revoke", action="store_true", help="Retire le rôle au lieu de l'accorder.")
    ap.add_argument("--list", action="store_true", help="Liste les comptes administrateurs.")
    args = ap.parse_args()

    if args.list:
        return asyncio.run(list_admins())
    if not args.email:
        ap.error("email requis (ou --list)")
    return asyncio.run(set_admin(args.email, not args.revoke))


if __name__ == "__main__":
    raise SystemExit(main())
