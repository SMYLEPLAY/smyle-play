"""
Escrow des gains (A2). Maturation + gel des Smyles GAGNÉS avant retrait.

Modèle des états d'un gagné (doctrine éco) :
    vente → EN ATTENTE (fenêtre anti-fraude / chargeback) → DISPONIBLE → retirable
    + BLOQUÉ (litige / fraude / séquestre) = portion gelée non retirable.

Implémentation sans job ni colonne de date : la maturité se DÉRIVE du ledger
append-only — un gain est « maturé » quand la transaction qui l'a créé date de
plus de EARNINGS_MATURITY_DAYS. La portion gelée est `users.smyles_gagnes_bloque`.

Lecture seule + helper d'admin (gel). Aucune dépendance au payout (qui
consommera `withdrawable_gagnes` quand Stripe Connect sera branché — Phase D).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Fenêtre de maturation des gains avant qu'ils deviennent retirables
# (anti-fraude + délai de contestation / chargeback). Ajustable.
EARNINGS_MATURITY_DAYS = 7


async def matured_gagnes(db: AsyncSession, user_id: UUID) -> int:
    """Total BRUT des gains (artist_revenue) reçus il y a plus de
    EARNINGS_MATURITY_DAYS (toutes transactions de gain confondues)."""
    row = (await db.execute(
        text(
            "SELECT COALESCE(SUM(artist_revenue), 0) AS m FROM transactions "
            "WHERE seller_id = :uid AND artist_revenue > 0 "
            "AND status = 'completed' "
            "AND created_at <= now() - (:d * interval '1 day')"
        ),
        {"uid": user_id, "d": EARNINGS_MATURITY_DAYS},
    )).first()
    return int(row.m)


async def withdrawable_gagnes(db: AsyncSession, user_id: UUID) -> int:
    """Gains RETIRABLES = min(gagnés détenus non gelés, gains maturés).

    Conservateur : on ne peut jamais retirer plus que ce qu'on détient
    actuellement en gagnés (net des dépenses), ni plus que ce qui a maturé.
    """
    row = (await db.execute(
        text(
            "SELECT smyles_gagnes, smyles_gagnes_bloque "
            "FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    )).first()
    if row is None:
        return 0
    held_unblocked = int(row.smyles_gagnes) - int(row.smyles_gagnes_bloque)
    return max(0, min(held_unblocked, await matured_gagnes(db, user_id)))


async def gagnes_status(db: AsyncSession, user_id: UUID) -> dict:
    """Récap des états des gagnés pour l'UI / le payout (Phase D)."""
    row = (await db.execute(
        text(
            "SELECT smyles_gagnes, smyles_gagnes_bloque "
            "FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    )).first()
    if row is None:
        return {"total": 0, "bloque": 0, "retirable": 0, "en_attente": 0}
    total = int(row.smyles_gagnes)
    bloque = int(row.smyles_gagnes_bloque)
    retirable = await withdrawable_gagnes(db, user_id)
    en_attente = max(0, total - bloque - retirable)
    return {
        "total": total,
        "bloque": bloque,
        "retirable": retirable,
        "en_attente": en_attente,
    }


async def set_gagnes_bloque(db: AsyncSession, user_id: UUID, amount: int) -> None:
    """Gèle `amount` Smyles gagnés (litige/fraude/séquestre). Admin uniquement.
    Clampé à [0, smyles_gagnes]. Ne touche pas le solde ni les autres buckets."""
    if amount < 0:
        raise ValueError("amount must be >= 0")
    await db.execute(
        text(
            "UPDATE users SET smyles_gagnes_bloque = LEAST(:a, smyles_gagnes) "
            "WHERE id = :uid"
        ),
        {"a": amount, "uid": user_id},
    )
