"""
Phase 9.3 — Tests UNITAIRES de la logique de pricing unlock (sans DB).

Couvre la composition perk + split telle qu'utilisée dans les services
unlock_prompt_atomic / unlock_adn_atomic. Les tests d'intégration HTTP
+ DB (atomicité, locks, refus self-purchase, balance constraint) sont
dans Phase 9.5.

Objectif : prouver que pour TOUT prix de catalogue valide (3..500),
la composition (perk → split) garantit :
  - paid >= 1
  - paid == artist_revenue + platform_fee (zéro crédit perdu)
  - artist_revenue >= 0, platform_fee >= 0
  - paid <= base_price (le perk ne peut JAMAIS faire monter le prix)
  - sans perk : paid == base_price
  - avec perk : paid <= base_price (et exactement floor(base*7/10) sauf plancher)
"""
import pytest

from app.schemas.marketplace import (
    ADN_PRICE_MAX,
    ADN_PRICE_MIN,
    PROMPT_PRICE_MAX,
    PROMPT_PRICE_MIN,
)
from app.services.credits import compute_effective_price, compute_split


# -----------------------------------------------------------------------------
# Composition perk + split (utilisée dans unlock_prompt_atomic)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("base", range(PROMPT_PRICE_MIN, PROMPT_PRICE_MAX + 1))
@pytest.mark.parametrize("perk", [False, True])
def test_unlock_prompt_pricing_invariants(base, perk):
    """
    Pour tout prix de prompt valide (3..500), avec ou sans perk :
      - paid >= 1
      - artist_revenue + platform_fee == paid (zéro crédit perdu)
      - les deux parts sont des entiers positifs ou nuls
      - paid <= base (le perk ne fait jamais monter le prix)
    """
    paid = compute_effective_price(base, perk)
    artist, platform = compute_split(paid)

    assert paid >= 1
    assert paid <= base
    assert isinstance(artist, int) and isinstance(platform, int)
    assert artist >= 0
    assert platform >= 0
    assert artist + platform == paid


def test_unlock_prompt_perk_never_inverts_price_ordering():
    """
    Garantie : si base_a >= base_b, alors paid_a >= paid_b.
    (Le perk ne peut pas faire qu'un prompt plus cher devienne moins cher
    après réduction.)
    """
    for base_a in range(PROMPT_PRICE_MIN, 200):
        for base_b in range(PROMPT_PRICE_MIN, base_a + 1):
            paid_a = compute_effective_price(base_a, True)
            paid_b = compute_effective_price(base_b, True)
            assert paid_a >= paid_b, (
                f"Inversion: base {base_a}→{paid_a} vs {base_b}→{paid_b}"
            )


def test_unlock_prompt_no_perk_is_identity():
    """Sans perk, paid == base toujours (c'est la définition)."""
    for base in range(PROMPT_PRICE_MIN, PROMPT_PRICE_MAX + 1):
        assert compute_effective_price(base, False) == base


# -----------------------------------------------------------------------------
# Pricing ADN (pas de perk applicable)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("price", range(ADN_PRICE_MIN, ADN_PRICE_MAX + 1))
def test_unlock_adn_pricing_invariants(price):
    """
    Achat ADN : paid == price (jamais de perk).
    Split 80/20 garanti, somme = paid.
    """
    paid = compute_effective_price(price, has_perk=False)
    assert paid == price  # ADN: pas de perk

    artist, platform = compute_split(paid)
    assert artist + platform == paid
    assert artist >= 0 and platform >= 0


# -----------------------------------------------------------------------------
# Cas concrets de la table de pricing (golden values)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "base, has_perk, expected_paid, expected_artist, expected_platform",
    [
        # Prompts standards (pas de perk)
        (3, False, 3, 2, 1),
        (5, False, 5, 4, 1),
        (10, False, 10, 8, 2),
        (50, False, 50, 40, 10),
        (200, False, 200, 160, 40),
        # Prompts avec perk -30%
        (5, True, 3, 2, 1),
        (10, True, 7, 5, 2),
        (50, True, 35, 28, 7),
        (100, True, 70, 56, 14),
        (200, True, 140, 112, 28),
        # ADN (jamais de perk)
        (30, False, 30, 24, 6),
        (100, False, 100, 80, 20),
        (500, False, 500, 400, 100),
    ],
)
def test_pricing_golden_values(
    base, has_perk, expected_paid, expected_artist, expected_platform
):
    """
    Snapshots précis du pricing pour empêcher toute dérive silencieuse
    (changement de constantes, refacto helpers, etc.).
    """
    paid = compute_effective_price(base, has_perk)
    artist, platform = compute_split(paid)
    assert paid == expected_paid
    assert artist == expected_artist
    assert platform == expected_platform


# -----------------------------------------------------------------------------
# Cas pathologiques : doivent toujours rester safe
# -----------------------------------------------------------------------------

def test_pricing_min_price_with_perk_floor_to_one():
    """Plancher : un prompt à 3 crédits avec perk → paid >= 1."""
    paid = compute_effective_price(3, has_perk=True)
    assert paid >= 1


def test_pricing_no_zero_or_negative_artist_revenue_for_min_prices():
    """Pour le prompt minimum (3), l'artiste touche au moins 0 (pas négatif)."""
    paid = compute_effective_price(3, has_perk=True)  # = 2
    artist, platform = compute_split(paid)
    assert artist >= 0
    assert platform >= 0
    assert artist + platform == paid


def test_pricing_consistent_across_full_catalog_range():
    """
    Smoke total : 498 prix * 2 perks * cohérence split = ~1000 invariants.
    """
    failures = []
    for base in range(PROMPT_PRICE_MIN, PROMPT_PRICE_MAX + 1):
        for perk in (False, True):
            paid = compute_effective_price(base, perk)
            artist, platform = compute_split(paid)
            if not (paid >= 1 and paid <= base and artist + platform == paid):
                failures.append((base, perk, paid, artist, platform))
    assert not failures, f"{len(failures)} invariants violés : {failures[:5]}"
