"""
Phase 9.1 — Tests des helpers d'arithmétique entière marketplace.

Ces tests sont des tests UNITAIRES purs (pas de DB, pas d'auth, pas de
client HTTP). Ils valident exhaustivement la fonction compute_effective_price
(perk -30%) et compute_split (split artiste/plateforme).

Objectif: zéro float, zéro crédit perdu, zéro arrondi imprévisible.
"""

import pytest

from app.services.credits import (
    PERK_DENOMINATOR,
    PERK_NUMERATOR,
    PRIMARY_MARKET_ARTIST_PCT,
    compute_effective_price,
    compute_split,
)


# -----------------------------------------------------------------------------
# compute_effective_price — table de cas exhaustive
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "base_price, has_perk, expected",
    [
        # Sans perk: identité
        (3, False, 3),
        (5, False, 5),
        (7, False, 7),
        (10, False, 10),
        (50, False, 50),
        (200, False, 200),
        (500, False, 500),
        # Avec perk (-30%, arrondi inférieur)
        (3, True, 2),    # 3*7//10 = 2
        (4, True, 2),    # 4*7//10 = 2
        (5, True, 3),    # 5*7//10 = 3
        (6, True, 4),    # 6*7//10 = 4
        (7, True, 4),    # 7*7//10 = 4
        (8, True, 5),    # 8*7//10 = 5
        (9, True, 6),    # 9*7//10 = 6
        (10, True, 7),   # 10*7//10 = 7
        (50, True, 35),  # 50*7//10 = 35
        (100, True, 70),
        (200, True, 140),
        # Plancher: prix de base = 1 → perk donnerait 0, on force min 1
        (1, True, 1),    # max(1, 1*7//10) = max(1, 0) = 1
        (2, True, 1),    # max(1, 2*7//10) = max(1, 1) = 1
    ],
)
def test_compute_effective_price(base_price, has_perk, expected):
    assert compute_effective_price(base_price, has_perk) == expected


def test_compute_effective_price_rejects_zero():
    with pytest.raises(ValueError):
        compute_effective_price(0, False)


def test_compute_effective_price_rejects_negative():
    with pytest.raises(ValueError):
        compute_effective_price(-5, False)


def test_compute_effective_price_returns_int_always():
    """Vérifie qu'on ne retourne JAMAIS un float (paranoid check)."""
    for base in range(1, 501):
        for perk in (True, False):
            result = compute_effective_price(base, perk)
            assert isinstance(result, int), f"Non-int pour base={base} perk={perk}"
            assert result >= 1


def test_perk_constants_consistent():
    """Vérifie que le perk reste bien -30% (PERK_NUMERATOR/PERK_DENOMINATOR = 0.7)."""
    assert PERK_NUMERATOR == 7
    assert PERK_DENOMINATOR == 10


# -----------------------------------------------------------------------------
# compute_split — table de cas exhaustive (primary market 80/20)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "amount, artist_pct, expected_artist, expected_platform",
    [
        # Primary market 80/20 (default)
        (3, 80, 2, 1),       # 3*80//100 = 2, reste 1
        (5, 80, 4, 1),       # 5*80//100 = 4, reste 1
        (7, 80, 5, 2),       # 7*80//100 = 5, reste 2
        (10, 80, 8, 2),      # 10*80//100 = 8, reste 2
        (50, 80, 40, 10),
        (100, 80, 80, 20),
        (200, 80, 160, 40),
        (500, 80, 400, 100),
        # Cas plancher (1 crédit, edge case)
        (1, 80, 0, 1),       # 1*80//100 = 0, reste 1 (plateforme absorbe)
        (2, 80, 1, 1),       # 2*80//100 = 1, reste 1
        # Future Phase 10 : split P2P resale (artist=30%)
        (10, 30, 3, 7),      # 10*30//100 = 3, reste 7 (vendeur prend ce reste moins fee)
        (100, 30, 30, 70),
    ],
)
def test_compute_split(amount, artist_pct, expected_artist, expected_platform):
    artist_revenue, platform_fee = compute_split(amount, artist_pct)
    assert artist_revenue == expected_artist
    assert platform_fee == expected_platform


@pytest.mark.parametrize("amount", [1, 2, 3, 5, 7, 10, 13, 17, 50, 100, 200, 500, 1000])
def test_compute_split_sum_invariant(amount):
    """Invariant critique: artist_revenue + platform_fee == amount (zéro crédit perdu)."""
    artist_revenue, platform_fee = compute_split(amount)
    assert artist_revenue + platform_fee == amount


def test_compute_split_rejects_zero():
    with pytest.raises(ValueError):
        compute_split(0)


def test_compute_split_rejects_negative():
    with pytest.raises(ValueError):
        compute_split(-10)


def test_compute_split_rejects_invalid_pct():
    with pytest.raises(ValueError):
        compute_split(100, artist_pct=-1)
    with pytest.raises(ValueError):
        compute_split(100, artist_pct=101)


def test_compute_split_returns_int_always():
    """Vérifie qu'on retourne JAMAIS un float."""
    for amount in (1, 2, 3, 5, 7, 10, 50, 100, 500):
        artist, platform = compute_split(amount)
        assert isinstance(artist, int)
        assert isinstance(platform, int)


def test_primary_market_pct_is_80():
    """Le pourcentage artiste primary market est verrouillé à 80%."""
    assert PRIMARY_MARKET_ARTIST_PCT == 80


# -----------------------------------------------------------------------------
# Combinaison perk + split (scénario unlock complet)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "base_price, has_perk, expected_paid, expected_artist, expected_platform",
    [
        # Sans perk
        (3, False, 3, 2, 1),
        (5, False, 5, 4, 1),
        (10, False, 10, 8, 2),
        (50, False, 50, 40, 10),
        # Avec perk (le buyer paie moins, l'artiste touche moins, plateforme absorbe)
        (3, True, 2, 1, 1),    # 3 → 2 → split (1, 1)
        (5, True, 3, 2, 1),    # 5 → 3 → split (2, 1)
        (7, True, 4, 3, 1),    # 7 → 4 → split (3, 1)
        (10, True, 7, 5, 2),   # 10 → 7 → split (5, 2)
        (50, True, 35, 28, 7), # 50 → 35 → split (28, 7)
    ],
)
def test_full_unlock_pricing_pipeline(
    base_price, has_perk, expected_paid, expected_artist, expected_platform
):
    """
    Scénario unlock prompt complet:
      1. Calcul prix effectif (avec/sans perk)
      2. Split artist/platform sur ce prix effectif

    Invariants vérifiés:
      - paid == artist + platform (pas de crédit perdu)
      - paid >= 1 (jamais zéro)
      - tous entiers
    """
    paid = compute_effective_price(base_price, has_perk)
    artist, platform = compute_split(paid)
    assert paid == expected_paid
    assert artist == expected_artist
    assert platform == expected_platform
    assert artist + platform == paid  # invariant zéro-perte
    assert paid >= 1
