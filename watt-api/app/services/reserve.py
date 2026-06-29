"""
Réserve € & solvabilité (A3). Met en œuvre la règle maîtresse de la doctrine :

    Réserve € ≥ dette encaissable + provisions opérationnelles — à tout instant.

La réserve est segmentée en 4 poches (table platform_reserve) :
  payout (adosse la dette) · tax · refund · cash (trésorerie, jamais mêlée).

Dette encaissable = total des Smyles GAGNÉS × taux de payout. Conservateur :
on couvre TOUS les gagnés (chaque gagné est une créance potentielle en euros),
indépendamment de la maturation (qui ne fait que retarder le retrait).

Pilotage tricolore (sur payout / dette) :
  🟢 > 130 %  ·  🟠 110–130 %  ·  🔴 100–110 %  ·  ⚫ < 100 %

Lecture + helpers de mouvement. Le crédit réel (achat pack → payout, dépense
promo → payout) sera câblé avec Stripe (Phase B). Ici = structure + calcul.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Taux de remboursement d'un Smyle en cents (doctrine : ~0,70 €). Sert à
# valoriser la dette encaissable. Ajustable.
PAYOUT_RATE_CENTS = 70

_POCHES = ("payout", "tax", "refund", "cash")


async def cashable_debt_cents(db: AsyncSession) -> int:
    """Dette encaissable totale (cents) = Σ des Smyles gagnés × taux payout."""
    row = (await db.execute(
        text("SELECT COALESCE(SUM(smyles_gagnes), 0) AS g FROM users")
    )).first()
    return int(row.g) * PAYOUT_RATE_CENTS


async def reserve_poche_cents(db: AsyncSession, poche: str) -> int:
    if poche not in _POCHES:
        raise ValueError(f"unknown poche: {poche!r}")
    row = (await db.execute(
        text("SELECT amount_cents FROM platform_reserve WHERE poche = :p"),
        {"p": poche},
    )).first()
    return int(row.amount_cents) if row is not None else 0


async def move_reserve(db: AsyncSession, poche: str, delta_cents: int) -> None:
    """Crédite (delta>0) ou débite (delta<0) une poche de la réserve.
    Le débit est clampé à 0 par le CHECK ; à utiliser dans un flux locké."""
    if poche not in _POCHES:
        raise ValueError(f"unknown poche: {poche!r}")
    await db.execute(
        text(
            "UPDATE platform_reserve SET amount_cents = amount_cents + :d "
            "WHERE poche = :p"
        ),
        {"d": delta_cents, "p": poche},
    )


def _zone(payout_cents: int, debt_cents: int) -> str:
    """Feu tricolore sur le ratio payout / dette."""
    if debt_cents <= 0:
        return "🟢"
    ratio = payout_cents / debt_cents
    if ratio > 1.30:
        return "🟢"
    if ratio >= 1.10:
        return "🟠"
    if ratio >= 1.00:
        return "🔴"
    return "⚫"


async def reserve_status(db: AsyncSession) -> dict:
    """État de solvabilité : poches, dette encaissable, ratio, feu tricolore."""
    poches = {p: await reserve_poche_cents(db, p) for p in _POCHES}
    debt = await cashable_debt_cents(db)
    payout = poches["payout"]
    ratio_pct = None if debt <= 0 else round(payout / debt * 100, 1)
    return {
        "reserve_cents": poches,
        "cashable_debt_cents": debt,
        "payout_vs_debt_pct": ratio_pct,
        "zone": _zone(payout, debt),
        "solvable": payout >= debt,  # règle maîtresse (sur la poche payout)
    }
