"""
Phase 9.2 — Tests unitaires des schémas marketplace.

Tests purs Pydantic : validation, normalisation, bornes, refus
des champs inconnus. Pas de DB, pas d'HTTP. Les flows complets
sont couverts en Phase 9.5 (tests d'intégration).
"""
import pytest
from pydantic import ValidationError

from app.schemas.marketplace import (
    ADN_DESCRIPTION_MIN,
    ADN_PRICE_MAX,
    ADN_PRICE_MIN,
    PROMPT_PRICE_MAX,
    PROMPT_PRICE_MIN,
    PROMPT_TEXT_MAX,
    PROMPT_TEXT_MIN,
    PROMPT_TITLE_MIN,
    AdnCreate,
    AdnUpdate,
    BrandColorUpdate,
    PromptCreate,
    PromptUpdate,
)


# -----------------------------------------------------------------------------
# Helpers : payloads minimaux valides
# -----------------------------------------------------------------------------

VALID_DESCRIPTION = "x" * ADN_DESCRIPTION_MIN  # exactement la borne min
LONG_PROMPT_TEXT = "y" * PROMPT_TEXT_MIN
VALID_TITLE = "Z" * PROMPT_TITLE_MIN


def _adn_create_payload(**overrides):
    base = {
        "description": VALID_DESCRIPTION,
        "price_credits": ADN_PRICE_MIN,
    }
    base.update(overrides)
    return base


def _prompt_create_payload(**overrides):
    base = {
        "title": VALID_TITLE,
        "prompt_text": LONG_PROMPT_TEXT,
        "price_credits": PROMPT_PRICE_MIN,
    }
    base.update(overrides)
    return base


# -----------------------------------------------------------------------------
# AdnCreate
# -----------------------------------------------------------------------------

def test_adn_create_minimal_valid():
    a = AdnCreate(**_adn_create_payload())
    assert a.price_credits == ADN_PRICE_MIN
    assert a.usage_guide is None
    assert a.example_outputs is None


def test_adn_create_full_valid():
    a = AdnCreate(
        description=VALID_DESCRIPTION,
        usage_guide="how to use",
        example_outputs="output samples",
        price_credits=200,
    )
    assert a.usage_guide == "how to use"


@pytest.mark.parametrize("price", [0, 1, 29, ADN_PRICE_MAX + 1, 1000])
def test_adn_create_rejects_out_of_range_price(price):
    with pytest.raises(ValidationError):
        AdnCreate(**_adn_create_payload(price_credits=price))


def test_adn_create_rejects_short_description():
    with pytest.raises(ValidationError):
        AdnCreate(**_adn_create_payload(description="x" * (ADN_DESCRIPTION_MIN - 1)))


def test_adn_create_rejects_unknown_field():
    with pytest.raises(ValidationError):
        AdnCreate(**_adn_create_payload(is_published=True))


def test_adn_create_rejects_pack_eligible():
    """pack_eligible est réservé Phase 10, ne doit jamais passer."""
    with pytest.raises(ValidationError):
        AdnCreate(**_adn_create_payload(pack_eligible=True))


def test_adn_create_strips_whitespace():
    a = AdnCreate(**_adn_create_payload(description=f"  {VALID_DESCRIPTION}  "))
    # Après strip, on doit retomber pile sur la borne min
    assert len(a.description) == ADN_DESCRIPTION_MIN


# -----------------------------------------------------------------------------
# AdnUpdate
# -----------------------------------------------------------------------------

def test_adn_update_empty_is_valid():
    """PATCH vide = no-op explicite côté API."""
    u = AdnUpdate()
    assert u.model_dump(exclude_unset=True) == {}


def test_adn_update_partial_only_price():
    u = AdnUpdate(price_credits=42)
    assert u.model_dump(exclude_unset=True) == {"price_credits": 42}


def test_adn_update_partial_only_publish():
    u = AdnUpdate(is_published=True)
    assert u.model_dump(exclude_unset=True) == {"is_published": True}


def test_adn_update_rejects_unknown_field():
    with pytest.raises(ValidationError):
        AdnUpdate(artist_id="00000000-0000-0000-0000-000000000000")


def test_adn_update_rejects_invalid_price():
    with pytest.raises(ValidationError):
        AdnUpdate(price_credits=2)
    with pytest.raises(ValidationError):
        AdnUpdate(price_credits=ADN_PRICE_MAX + 1)


# -----------------------------------------------------------------------------
# PromptCreate
# -----------------------------------------------------------------------------

def test_prompt_create_minimal_valid():
    p = PromptCreate(**_prompt_create_payload())
    assert p.price_credits == PROMPT_PRICE_MIN
    assert p.description is None


@pytest.mark.parametrize("price", [0, 1, 2, PROMPT_PRICE_MAX + 1, 9999])
def test_prompt_create_rejects_out_of_range_price(price):
    with pytest.raises(ValidationError):
        PromptCreate(**_prompt_create_payload(price_credits=price))


def test_prompt_create_rejects_short_title():
    with pytest.raises(ValidationError):
        PromptCreate(**_prompt_create_payload(title="x" * (PROMPT_TITLE_MIN - 1)))


def test_prompt_create_rejects_short_text():
    with pytest.raises(ValidationError):
        PromptCreate(**_prompt_create_payload(prompt_text="x" * (PROMPT_TEXT_MIN - 1)))


def test_prompt_create_rejects_unknown_field():
    with pytest.raises(ValidationError):
        PromptCreate(**_prompt_create_payload(is_published=True))


def test_prompt_create_rejects_pack_eligible():
    """pack_eligible doit être inaccessible côté client en Phase 9."""
    with pytest.raises(ValidationError):
        PromptCreate(**_prompt_create_payload(pack_eligible=False))


def test_prompt_create_rejects_artist_id_injection():
    """Le client ne doit jamais pouvoir setter artist_id (vient du JWT)."""
    with pytest.raises(ValidationError):
        PromptCreate(
            **_prompt_create_payload(
                artist_id="11111111-1111-1111-1111-111111111111"
            )
        )


# -----------------------------------------------------------------------------
# PromptUpdate
# -----------------------------------------------------------------------------

def test_prompt_update_empty_valid():
    u = PromptUpdate()
    assert u.model_dump(exclude_unset=True) == {}


def test_prompt_update_only_publish():
    u = PromptUpdate(is_published=True)
    assert u.model_dump(exclude_unset=True) == {"is_published": True}


def test_prompt_update_rejects_pack_eligible():
    with pytest.raises(ValidationError):
        PromptUpdate(pack_eligible=False)


# -----------------------------------------------------------------------------
# BrandColorUpdate — normalisation uppercase
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("#ffaa00", "#FFAA00"),
        ("#FFAA00", "#FFAA00"),
        ("#AbCdEf", "#ABCDEF"),
        ("#000000", "#000000"),
        ("#FFFFFF", "#FFFFFF"),
    ],
)
def test_brand_color_normalized_uppercase(raw, expected):
    bc = BrandColorUpdate(brand_color=raw)
    assert bc.brand_color == expected


def test_brand_color_none_passes_through():
    """Permet de remettre brand_color à NULL (déselectionner sa couleur)."""
    bc = BrandColorUpdate(brand_color=None)
    assert bc.brand_color is None


@pytest.mark.parametrize(
    "bad",
    [
        "ffaa00",        # missing #
        "#fff",          # 3 chars only
        "#ffaa0",        # 5 chars
        "#ffaa000",      # 7 chars
        "#gghhii",       # invalid hex chars
        "rgb(0,0,0)",    # CSS function
        "  ",            # whitespace only
        "#FFAA 00",      # space inside
    ],
)
def test_brand_color_rejects_invalid_format(bad):
    with pytest.raises(ValidationError):
        BrandColorUpdate(brand_color=bad)


def test_brand_color_rejects_unknown_field():
    with pytest.raises(ValidationError):
        BrandColorUpdate(brand_color="#FFAA00", color="red")


# -----------------------------------------------------------------------------
# Cohérence cross-schema : limites partagées exposées
# -----------------------------------------------------------------------------

def test_constants_are_consistent_with_db():
    """
    Les bornes Pydantic doivent matcher les CHECK constraints DB
    (vérif manuelle ici : c'est de la doc-as-test).
    """
    # ADN : ck_adns_price_credits_range entre 30 et 500
    assert ADN_PRICE_MIN == 30
    assert ADN_PRICE_MAX == 500
    # ADN : ck_adns_description_min_length >= 200
    assert ADN_DESCRIPTION_MIN == 200
    # Prompt : ck_prompts_price_credits_min >= 3
    assert PROMPT_PRICE_MIN == 3
    # Prompt : ck_prompts_title_min_length >= 5
    assert PROMPT_TITLE_MIN == 5
    # Prompt : ck_prompts_prompt_text_length BETWEEN 100 AND 1000
    # (resserré en 0019 — Suno n'accepte pas plus de 1000 chars en entrée)
    assert PROMPT_TEXT_MIN == 100
    assert PROMPT_TEXT_MAX == 1000
