"""Quêtes de parrainage — Étape 3 (flag FEATURE_QUETES_PARRAINAGE).

Paliers (settings.QUETES_PARRAINAGE_PALIERS, par défaut) :
     3 filleuls ACTIFS →  10 Smyles
    10 filleuls ACTIFS →  50 Smyles
    25 filleuls ACTIFS → 150 Smyles + badge « Ambassadeur »

Règles :
  - Crédit dans le bucket PROMO UNIQUEMENT (type BONUS → promo, via
    `grant_credits_atomic`) : dépensable sur WATT, jamais retirable.
  - IDEMPOTENT par (parrain, palier) : clé `quete_parrainage:{parrain}:{seuil}`
    (index UNIQUE partiel du registre). Un palier n'est versé qu'une fois, même
    si le nombre de filleuls actifs redescend puis remonte, même en cas de
    double clic ou de requêtes simultanées.
  - Un filleul COMPTE s'il est :
      * ACTIF au sens de la définition UNIQUE (`launch_readiness.SQL_CTE_ACTIFS`,
        même CTE que « Prêt à sortir » — jamais dupliquée) ;
      * ET validé par le parrainage de base (`status = 'rewarded'`) : c'est ce
        qui CONSERVE les plafonds anti-abus existants de `referrals.py`
        (plafond quotidien par parrain, plafond par IP d'inscription) et
        l'ancrage sur une vraie action (1er son posté ou 1er achat).
  - Plafond GLOBAL : au plus `QUETES_PARRAINAGE_PLAFOND_24H` Smyles de quêtes
    versés sur 24 h glissantes, toute la plateforme confondue. Au-delà, le
    palier attend (il sera versé à une visite suivante : rien n'est perdu).
    Les versements de quêtes sont sérialisés par un verrou applicatif
    transactionnel → le plafond ne peut pas être dépassé par deux requêtes
    simultanées.

Déclenchement : paresseux, quand le parrain ouvre son panneau de parrainage
(POST /referrals/quetes). Le caller commit.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.transaction import TransactionType
from app.services.credits import grant_credits_atomic
from app.services.launch_readiness import SQL_CTE_ACTIFS, params_actifs

RAISON = "quete_parrainage"

# Verrou applicatif (pg_advisory_xact_lock) des versements de quêtes.
# ASCII « QUET » = 0x51554554. Unique à l'application.
_LOCK_KEY = 0x51554554

SQL_FILLEULS_ACTIFS = (
    "WITH " + SQL_CTE_ACTIFS + " "
    "SELECT count(*) FROM referrals r "
    "WHERE r.referrer_id = :parrain AND r.status = 'rewarded' "
    "AND r.referred_id IN (SELECT id FROM actifs)"
)


def cle(parrain_id: UUID, seuil: int) -> str:
    return f"{RAISON}:{parrain_id}:{int(seuil)}"


def paliers() -> list[tuple[int, int]]:
    return sorted((int(s), int(m)) for s, m in settings.QUETES_PARRAINAGE_PALIERS)


async def compter_filleuls_actifs(db: AsyncSession, parrain_id: UUID) -> int:
    params = await params_actifs(db)
    return int((await db.execute(
        text(SQL_FILLEULS_ACTIFS), {**params, "parrain": parrain_id}
    )).scalar_one())


async def _paliers_verses(db: AsyncSession, parrain_id: UUID) -> set[int]:
    cles = [cle(parrain_id, s) for s, _ in paliers()]
    if not cles:
        return set()
    rows = (await db.execute(
        text("SELECT idempotency_key FROM transactions WHERE idempotency_key = ANY(:k)"),
        {"k": cles},
    )).scalars().all()
    verses = set(rows)
    return {s for s, _ in paliers() if cle(parrain_id, s) in verses}


async def _verse_24h(db: AsyncSession) -> int:
    return int((await db.execute(
        text(
            "SELECT COALESCE(SUM(credits_amount), 0) FROM transactions "
            "WHERE type = 'bonus' AND status = 'completed' "
            "AND metadata_json->>'reason' = :r "
            "AND created_at > now() - interval '24 hours'"
        ),
        {"r": RAISON},
    )).scalar_one())


def _progression(n: int, verses: set[int], nouveaux: list[dict]) -> dict:
    liste = [
        {"seuil": s, "smyles": m, "atteint": n >= s, "verse": s in verses}
        for s, m in paliers()
    ]
    prochain = next((p for p in liste if not p["atteint"]), None)
    return {
        "actif": True,
        "filleuls_actifs": n,
        "paliers": liste,
        "prochain": None if prochain is None else {
            "seuil": prochain["seuil"],
            "smyles": prochain["smyles"],
            "manquants": prochain["seuil"] - n,
        },
        "ambassadeur": int(settings.QUETES_PARRAINAGE_PALIER_AMBASSADEUR) in verses,
        "nouveaux_versements": nouveaux,
    }


async def progression_quetes(db: AsyncSession, parrain_id: UUID) -> dict:
    """Lecture seule : où en est ce parrain (rien n'est versé)."""
    if not settings.FEATURE_QUETES_PARRAINAGE:
        return {"actif": False}
    n = await compter_filleuls_actifs(db, parrain_id)
    return _progression(n, await _paliers_verses(db, parrain_id), [])


async def verifier_et_verser_quetes(db: AsyncSession, parrain_id: UUID) -> dict:
    """Verse les paliers atteints et pas encore versés (bucket promo,
    idempotent), dans la limite du plafond global. Le caller commit."""
    if not settings.FEATURE_QUETES_PARRAINAGE:
        return {"actif": False}
    n = await compter_filleuls_actifs(db, parrain_id)
    verses = await _paliers_verses(db, parrain_id)
    a_verser = [(s, m) for s, m in paliers() if n >= s and s not in verses]
    nouveaux: list[dict] = []
    if a_verser:
        # Sérialise TOUS les versements de quêtes (plafond global exact).
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
        # Relu sous verrou : une requête simultanée a pu verser entre-temps.
        verses = await _paliers_verses(db, parrain_id)
        deja = await _verse_24h(db)
        plafond = int(settings.QUETES_PARRAINAGE_PLAFOND_24H)
        for seuil, montant in a_verser:
            if seuil in verses:
                continue
            if deja + montant > plafond:
                break  # plafond global : on reprendra plus tard
            await grant_credits_atomic(
                db,
                parrain_id,
                montant,
                reason=RAISON,
                tx_type=TransactionType.BONUS,  # → bucket promo (non retirable)
                metadata={"palier": seuil, "filleuls_actifs": n},
                idempotency_key=cle(parrain_id, seuil),
            )
            deja += montant
            verses.add(seuil)
            nouveaux.append({"seuil": seuil, "smyles": montant})
    return _progression(n, verses, nouveaux)
