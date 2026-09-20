"""Compte TRÉSORERIE de la société (Brique 1).

La commission plateforme (`platform_fee`) était jusqu'ici seulement tracée au
ledger sans atterrir dans aucun solde : elle disparaissait de la circulation.
Brique 1 la route vers ce compte — « la poche de la société ».

Règles posées (décisions Tom 20/09) :
  - compte DISTINCT du profil vitrine « Smyle » (`is_official`) : on ne mélange
    pas une identité artiste publique et la trésorerie ;
  - non public (`profile_public = False`), `password_hash` NULL → aucune
    connexion possible : c'est un registre, pas un utilisateur ;
  - la commission va dans le bucket **`achetes` (NON retirable)**, JAMAIS dans
    `gagnes` — sinon la société figurerait dans la dette encaissable
    (`reserve.cashable_debt_cents` somme `smyles_gagnes` sur tous les comptes)
    et se devrait de l'argent à elle-même ;
  - aucun bucket dédié n'a été créé : le CHECK de somme A1.4 (migration 0088)
    reste INTACT (option (b)). Le solde société est identifiable par le drapeau,
    et reste intégralement reconstructible depuis le ledger append-only
    (`SUM(transactions.platform_fee)`) si l'on veut changer de structure plus tard.

RÉSOLUTION — jamais d'UUID en dur : l'id du compte est généré à la migration et
DIFFÈRE selon l'environnement. On le résout par `is_treasury = TRUE` (index
unique partiel `ix_users_is_treasury_true`, au plus une ligne).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Email du compte seedé par la migration 0089 (sert au seed et au diagnostic ;
# la résolution runtime passe par le drapeau, pas par l'email).
TREASURY_EMAIL = "tresorerie@smyleplay.com"


async def treasury_user_id(db: AsyncSession) -> UUID | None:
    """Id du compte trésorerie, ou None s'il n'existe pas (base pas encore
    migrée). Lecture indexée sur l'index partiel."""
    row = (await db.execute(
        text("SELECT id FROM users WHERE is_treasury = TRUE LIMIT 1")
    )).first()
    return row.id if row is not None else None


async def treasury_balance(db: AsyncSession) -> dict:
    """Trésorerie société, exposée comme une LIGNE À PART (elle est exclue des
    agrégats de circulation : ces Smyles n'appartiennent à aucun créateur).

    `gagnes` doit rester à 0 par construction — s'il devient non nul, c'est le
    signe qu'une commission a été mal routée (elle deviendrait retirable et
    gonflerait la dette encaissable)."""
    row = (await db.execute(
        text(
            "SELECT credits_balance, smyles_achetes, smyles_gagnes, smyles_promo "
            "FROM users WHERE is_treasury = TRUE LIMIT 1"
        )
    )).first()
    if row is None:
        return {"existe": False, "total": 0, "achetes": 0, "gagnes": 0, "promo": 0}
    return {
        "existe": True,
        "total": int(row.credits_balance),
        "achetes": int(row.smyles_achetes),
        "gagnes": int(row.smyles_gagnes),
        "promo": int(row.smyles_promo),
    }
