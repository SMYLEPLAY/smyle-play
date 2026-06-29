"""
Cockpit économique (A4) — agrégation lecture seule pour l'admin.

Deux couches (doctrine éco) :
  - Solvabilité (dérivée du ledger / réserve) : poches de réserve, dette
    encaissable, ratio payout/dette + feu tricolore, Smyles en circulation,
    incohérences de buckets (canari A1.2 — doit rester ~0).
  - Business : MRR / abonnés — disponibles seulement après Stripe (Phase B),
    renvoyés à 0 avec une note d'ici là.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.credits import count_bucket_inconsistencies
from app.services.reserve import reserve_status


async def eco_cockpit_data(db: AsyncSession) -> dict:
    res = await reserve_status(db)
    row = (await db.execute(
        text(
            "SELECT COALESCE(SUM(smyles_achetes), 0) AS a, "
            "COALESCE(SUM(smyles_gagnes), 0) AS g, "
            "COALESCE(SUM(smyles_promo), 0) AS p, COUNT(*) AS n FROM users"
        )
    )).first()
    a, g, p, n = int(row.a), int(row.g), int(row.p), int(row.n)
    return {
        "solvabilite": res,
        "smyles_en_circulation": {
            "achetes": a,
            "gagnes": g,
            "promo": p,
            "total": a + g + p,
        },
        "comptes": n,
        "incoherences_buckets": await count_bucket_inconsistencies(db),
        "business": {
            "mrr_cents": 0,
            "abonnes_payants": 0,
            "note": "MRR / abonnés disponibles après branchement Stripe (Phase B)",
        },
    }
