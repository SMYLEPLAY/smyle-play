"""Objectif collectif « 1000 actifs » — Étape 3, Brique 3 (flag FEATURE_GOAL).

Une barre de progression publique : « {n} / 1000 actifs — à 1000, le retrait
en euros s'ouvre pour tous (au plus tard le 1er mai 2027) », avec des paliers
(500 / 1000 / 2500). Franchir un palier NE DÉCLENCHE RIEN : c'est de
l'affichage (« débloqué »). L'ouverture réelle du retrait reste une décision
manuelle (Brique 6, Stripe Connect).

Le nombre d'actifs vient de la définition UNIQUE
`launch_readiness.compter_actifs` (même chiffre que « Prêt à sortir ») — jamais
dupliquée. La requête parcourt plusieurs tables : on la met en CACHE ~60 s par
processus (l'endpoint est public et appelé à chaque affichage de l'accueil).
Le même cache sert au seuil d'abonnés pour vendre (taille de la plateforme).
"""
from __future__ import annotations

import time
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.launch_readiness import compter_actifs

CACHE_SECONDES = 60

_cache: dict = {"t": 0.0, "n": None}

_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre")


def vider_cache() -> None:
    """Oublie la valeur en cache (tests, ou après une action admin)."""
    _cache["t"] = 0.0
    _cache["n"] = None


async def actifs_en_cache(db: AsyncSession) -> int:
    """Nombre d'actifs (définition unique), recalculé au plus toutes les
    CACHE_SECONDES par processus. Pas de verrou asyncio (lié à une boucle
    d'événements) : au pire deux recalculs simultanés, sans conséquence."""
    n = _cache["n"]
    if n is not None and time.monotonic() - _cache["t"] < CACHE_SECONDES:
        return n
    n = await compter_actifs(db)
    _cache["n"] = n
    _cache["t"] = time.monotonic()
    return n


def date_en_francais(iso: str) -> str:
    """'2027-05-01' → '1er mai 2027'. Renvoie la chaîne brute si invalide."""
    try:
        d = date.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {_MOIS[d.month - 1]} {d.year}"


def objectif_payload(actifs: int) -> dict:
    """Contenu public de la barre (fonction pure, testable sans base)."""
    cible = max(1, int(settings.GOAL_CIBLE_ACTIFS))
    limite = date_en_francais(settings.GOAL_RETRAIT_AU_PLUS_TARD)
    paliers = [
        {"seuil": int(s), "atteint": actifs >= int(s)}
        for s in sorted({int(x) for x in settings.GOAL_PALIERS})
    ]
    return {
        "actifs": actifs,
        "cible": cible,
        "progression": round(min(1.0, actifs / cible), 4),
        "paliers": paliers,
        # Affichage seulement : aucun retrait ne s'ouvre automatiquement.
        "cible_atteinte": actifs >= cible,
        "retrait_au_plus_tard": settings.GOAL_RETRAIT_AU_PLUS_TARD,
        "texte": (
            f"{actifs} / {cible} actifs — à {cible}, le retrait en euros s'ouvre "
            f"pour tous (au plus tard le {limite})"
        ),
    }


async def objectif_public(db: AsyncSession) -> dict:
    return objectif_payload(await actifs_en_cache(db))
