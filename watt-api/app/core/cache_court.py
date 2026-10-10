"""Cache court en mémoire pour les listes publiques de l'accueil (Lot G).

`/watt/tracks-catalog` et `/watt/artists` sont appelées par CHAQUE visiteur
de l'accueil et ne dépendent pas de qui les demande. On garde la réponse
quelques dizaines de secondes par process : une nouveauté apparaît avec au
plus ce retard, et un pic de visites ne se transforme plus en autant de
requêtes lourdes sur la base.

- Une entrée par clé ; un seul calcul à la fois par clé (les requêtes
  simultanées attendent le même résultat au lieu de recalculer).
- Une erreur n'est jamais mise en cache.
- Durée : CACHE_COURT_SECONDES (45 s) ; 0 en environnement de test, pour que
  les tests voient tout de suite ce qu'ils viennent d'écrire.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from app.config import settings

CACHE_COURT_SECONDES = 0.0 if (settings.ENVIRONMENT or "").lower() == "test" else 45.0


class CacheCourt:
    def __init__(self) -> None:
        self._valeurs: dict[str, tuple[float, Any]] = {}
        self._verrous: dict[str, asyncio.Lock] = {}

    def vider(self) -> None:
        self._valeurs.clear()

    async def obtenir(self, cle: str, producteur: Callable[[], Awaitable[Any]]) -> Any:
        duree = CACHE_COURT_SECONDES if _duree is None else _duree
        if duree <= 0:
            return await producteur()
        trouve = self._valeurs.get(cle)
        if trouve and trouve[0] > time.monotonic():
            return trouve[1]
        verrou = self._verrous.setdefault(cle, asyncio.Lock())
        async with verrou:
            trouve = self._valeurs.get(cle)
            if trouve and trouve[0] > time.monotonic():
                return trouve[1]
            valeur = await producteur()
            self._valeurs[cle] = (time.monotonic() + duree, valeur)
            return valeur


# Surcharge de la durée (tests) : None = CACHE_COURT_SECONDES.
_duree: float | None = None

cache_accueil = CacheCourt()
