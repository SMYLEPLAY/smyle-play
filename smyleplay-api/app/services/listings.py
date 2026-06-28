"""
Emplacements de vente par palier (C6.3).

Un « emplacement » = un produit PUBLIÉ et non supprimé, tous types confondus
(décision Tom 2026-06-26) : Prompt (recette / beat / image), ADN, Voix, ADN
Visuel. La limite dépend du palier (cf. app/services/tiers.py) :
Standard 10 · Premium 50 · Mythique illimité.

IMPORTANT — application différée : tant que `LISTING_SLOTS_ENFORCED` est False
(paiements pas ouverts), la jauge est CALCULÉE et affichée mais ne BLOQUE
jamais une publication. On évite ainsi de plafonner un créateur Standard qui
n'a encore aucun moyen de monter de palier. Le jour de Stripe, on passe le
flag à True et le blocage s'active.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.prompt import Prompt
from app.models.visual_adn import VisualAdn
from app.models.voice import Voice
from app.services.tiers import (
    listing_slots_for_tier,
    normalize_tier,
)

# Interrupteur d'APPLICATION de la jauge d'emplacements.
#   False (défaut) → la jauge est CALCULÉE et affichée (« 7/10 ») mais ne bloque
#                    AUCUNE publication. Indispensable tant que les paliers
#                    payants ne sont pas achetables : sinon un créateur Standard
#                    productif serait plafonné à 10 SANS moyen de monter
#                    (paiement pas ouvert) = état incohérent.
#   True            → blocage à la publication au-delà de la limite du palier.
# Avant de passer à True (jour de Stripe) : câbler `ensure_listing_slot_available`
# sur TOUS les chemins de publication (create + draft→publié) pour Prompt / ADN
# / Voix / ADN Visuel — cf. runbook activation paliers.
LISTING_SLOTS_ENFORCED = False


class ListingSlotLimitReached(Exception):
    """Levée quand un créateur atteint la limite d'emplacements de son palier
    et que l'application des emplacements est activée."""

    def __init__(self, used: int, limit: int, tier: str):
        self.used = used
        self.limit = limit
        self.tier = tier
        super().__init__(
            f"Listing slot limit reached: {used}/{limit} (tier={tier})"
        )


# Entités qui consomment un emplacement (publié + non supprimé).
_LISTING_MODELS = (Prompt, Adn, Voice, VisualAdn)


async def count_active_listings(db: AsyncSession, artist_id: UUID) -> int:
    """Nombre de produits PUBLIÉS et non supprimés de cet artiste, tous types
    confondus (Prompt + ADN + Voix + ADN Visuel)."""
    total = 0
    for model in _LISTING_MODELS:
        n = (await db.execute(
            select(func.count(model.id)).where(
                model.artist_id == artist_id,
                model.is_published.is_(True),
                model.is_deleted.is_(False),
            )
        )).scalar_one()
        total += int(n)
    return total


async def listing_slots_status(
    db: AsyncSession,
    artist_id: UUID,
    tier: object,
) -> dict:
    """Jauge d'emplacements pour l'UI (WattBoard, page Offres).

    `limit` = None → illimité (Mythique). `remaining` = None dans ce cas.
    `enforced` reflète si la limite bloque réellement les publications.
    """
    used = await count_active_listings(db, artist_id)
    limit = listing_slots_for_tier(tier)
    if limit is None:
        remaining = None
        over = False
    else:
        remaining = max(0, limit - used)
        over = used > limit
    return {
        "tier": normalize_tier(tier).value,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "over": over,
        "enforced": LISTING_SLOTS_ENFORCED,
    }


async def ensure_listing_slot_available(
    db: AsyncSession,
    artist_id: UUID,
    tier: object,
) -> None:
    """Garde à appeler AVANT de publier un nouveau produit.

    No-op si l'application est désactivée (`LISTING_SLOTS_ENFORCED=False`) ou si
    le palier est illimité. Sinon lève `ListingSlotLimitReached` quand le quota
    est déjà atteint. Ne retire jamais rien (les produits déjà publiés au-delà
    de la limite restent en vente — on bloque seulement l'ajout).
    """
    if not LISTING_SLOTS_ENFORCED:
        return
    limit = listing_slots_for_tier(tier)
    if limit is None:
        return
    used = await count_active_listings(db, artist_id)
    if used >= limit:
        raise ListingSlotLimitReached(
            used=used, limit=limit, tier=normalize_tier(tier).value
        )
