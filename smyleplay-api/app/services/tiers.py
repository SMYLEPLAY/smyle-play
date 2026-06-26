"""
Paliers d'abonnement créateur (C6 — paliers + Offres).

Trois paliers : Standard (gratuit, défaut), Premium, Mythique.
Un palier supérieur débloque DEUX choses (décision Tom 2026-06-26) :
  1. une COMMISSION réduite sur chaque vente (la plateforme prélève moins) ;
  2. plus d'EMPLACEMENTS de vente simultanés + de la VISIBILITÉ (mise en avant).

Barème commission (ce que la plateforme prélève) : 20 / 12 / 5.
  → la part artiste = 100 - commission = 80 / 88 / 95.
Le palier Standard (80%) reproduit EXACTEMENT le comportement historique
(`PRIMARY_MARKET_ARTIST_PCT = 80`) : tant que personne n'est Premium/Mythique,
aucune vente ne change. Le mécanisme est donc neutre à l'activation.

Source de vérité unique : tout le reste du code (split de vente, jauge
d'emplacements, page Offres) lit ces constantes — ne pas dupliquer les
chiffres ailleurs.
"""
from __future__ import annotations

from enum import Enum


class UserTier(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    MYTHIQUE = "mythique"


DEFAULT_TIER = UserTier.STANDARD

# Commission plateforme par palier, en pourcentage du prix payé.
TIER_COMMISSION_PCT: dict[UserTier, int] = {
    UserTier.STANDARD: 20,
    UserTier.PREMIUM: 12,
    UserTier.MYTHIQUE: 5,
}

# Emplacements de vente simultanés autorisés (None = illimité).
TIER_LISTING_SLOTS: dict[UserTier, int | None] = {
    UserTier.STANDARD: 10,
    UserTier.PREMIUM: 50,
    UserTier.MYTHIQUE: None,
}

# Mise en avant / visibilité accrue dans les listes marketplace.
TIER_FEATURED: dict[UserTier, bool] = {
    UserTier.STANDARD: False,
    UserTier.PREMIUM: True,
    UserTier.MYTHIQUE: True,
}

# Libellé d'affichage (UI / page Offres).
TIER_LABEL: dict[UserTier, str] = {
    UserTier.STANDARD: "Standard",
    UserTier.PREMIUM: "Premium",
    UserTier.MYTHIQUE: "Mythique",
}


def normalize_tier(value: object) -> UserTier:
    """Convertit une valeur DB / API en UserTier, défaut STANDARD si inconnu.

    Robuste aux NULL (comptes pré-migration 0069), à la casse, et aux valeurs
    invalides : on ne casse jamais un flux de vente sur un palier corrompu.
    """
    try:
        return UserTier(str(value or DEFAULT_TIER.value).strip().lower())
    except ValueError:
        return DEFAULT_TIER


def commission_pct_for_tier(tier: object) -> int:
    """Commission plateforme (%) pour ce palier."""
    return TIER_COMMISSION_PCT[normalize_tier(tier)]


def artist_pct_for_tier(tier: object) -> int:
    """Part artiste (%) = 100 - commission. 80 / 88 / 95."""
    return 100 - commission_pct_for_tier(tier)


def listing_slots_for_tier(tier: object) -> int | None:
    """Nombre d'emplacements de vente (None = illimité)."""
    return TIER_LISTING_SLOTS[normalize_tier(tier)]


def is_featured_tier(tier: object) -> bool:
    """True si le palier bénéficie d'une mise en avant."""
    return TIER_FEATURED[normalize_tier(tier)]


def tier_public_info(tier: object) -> dict:
    """Récapitulatif d'un palier pour l'API / la page Offres."""
    t = normalize_tier(tier)
    return {
        "tier": t.value,
        "label": TIER_LABEL[t],
        "commission_pct": TIER_COMMISSION_PCT[t],
        "artist_pct": 100 - TIER_COMMISSION_PCT[t],
        "listing_slots": TIER_LISTING_SLOTS[t],
        "featured": TIER_FEATURED[t],
    }
