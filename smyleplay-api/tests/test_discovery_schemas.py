"""
Phase 9.4 — Tests UNITAIRES des schémas découverte/library.

Couverture critique : le gating du contenu.
  - Vues publiques NE DOIVENT PAS exposer prompt_text ni example_outputs
  - Vues library DOIVENT exposer ces champs
  - Carte artiste publique : pas d'email, pas de balance, pas de password_hash

Si un dev ajoute par erreur un champ gated dans un schéma public, ce
test pète. C'est notre filet de sécurité contre les régressions.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.discovery import (
    AdnPublicCard,
    AdnPublicDetail,
    ArtistPublicCard,
    ArtistPublicProfile,
    EffectivePricePreview,
    LibraryAdnItem,
    LibraryPromptItem,
    PromptPublicCard,
    PromptPublicDetail,
)


# -----------------------------------------------------------------------------
# Fixtures locales
# -----------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)


def _artist_dict():
    return {
        "id": uuid4(),
        "artist_name": "DJ Watt",
        "brand_color": "#FFAA00",
        "avatar_url": "https://example.com/avatar.png",
    }


# -----------------------------------------------------------------------------
# ArtistPublicCard : champs non exposés (email, balance, password_hash, …)
# -----------------------------------------------------------------------------

def test_artist_card_has_no_sensitive_fields():
    card = ArtistPublicCard(**_artist_dict())
    dumped = card.model_dump()
    forbidden = {
        "email", "password_hash",
        "credits_balance", "credits_earned_total",
        "language", "bio", "universe_description",  # ces 3 sont sur Profile, pas Card
    }
    leaked = forbidden & dumped.keys()
    assert not leaked, f"Card publique fuit des champs sensibles: {leaked}"


def test_artist_card_requires_artist_name():
    """Un artiste sans artist_name ne devrait jamais arriver dans une Card."""
    payload = _artist_dict()
    payload["artist_name"] = None
    with pytest.raises(ValidationError):
        ArtistPublicCard(**payload)


def test_artist_profile_no_email_or_credits():
    profile = ArtistPublicProfile(
        **_artist_dict(),
        bio="Live from Earth",
        universe_description="Tropical bounce",
        has_adn=True,
        prompts_published_count=12,
    )
    dumped = profile.model_dump()
    assert "email" not in dumped
    assert "credits_balance" not in dumped
    assert "credits_earned_total" not in dumped
    assert "password_hash" not in dumped


# -----------------------------------------------------------------------------
# Prompt — vues publiques NE DOIVENT PAS contenir prompt_text
# -----------------------------------------------------------------------------

def test_public_prompt_card_has_no_prompt_text():
    card = PromptPublicCard(
        id=uuid4(),
        title="Mon prompt",
        description="Pitch en 1 ligne",
        price_credits=10,
        artist=ArtistPublicCard(**_artist_dict()),
        created_at=NOW,
    )
    assert "prompt_text" not in card.model_dump()


def test_public_prompt_detail_has_no_prompt_text():
    detail = PromptPublicDetail(
        id=uuid4(),
        title="Mon prompt",
        description="Pitch",
        price_credits=10,
        artist=ArtistPublicCard(**_artist_dict()),
        created_at=NOW,
    )
    assert "prompt_text" not in detail.model_dump()


def test_public_prompt_card_rejects_prompt_text_injection():
    """Si un dev essaie d'injecter prompt_text, Pydantic doit refuser."""
    # PromptPublicCard n'a pas extra="forbid" car c'est une vue de sortie
    # (from_attributes), donc le champ extra est juste IGNORÉ. C'est OK
    # pour la sortie tant que le service ne le mappe pas. Vérifions que
    # le model_dump n'expose PAS prompt_text même si on l'injecte.
    card = PromptPublicCard.model_validate({
        "id": uuid4(),
        "title": "X" * 5,
        "description": None,
        "price_credits": 10,
        "artist": _artist_dict(),
        "created_at": NOW,
        "prompt_text": "GATED CONTENT - SHOULD NOT LEAK",
    })
    dumped = card.model_dump()
    assert "prompt_text" not in dumped, (
        "PromptPublicCard fuit prompt_text via injection !"
    )


# -----------------------------------------------------------------------------
# ADN — vues publiques NE DOIVENT PAS contenir example_outputs
# -----------------------------------------------------------------------------

def test_public_adn_card_has_no_example_outputs():
    card = AdnPublicCard(
        id=uuid4(),
        artist=ArtistPublicCard(**_artist_dict()),
        description="X" * 200,
        usage_guide="how to",
        price_credits=50,
    )
    assert "example_outputs" not in card.model_dump()


def test_public_adn_detail_has_no_example_outputs():
    detail = AdnPublicDetail(
        id=uuid4(),
        artist=ArtistPublicCard(**_artist_dict()),
        description="X" * 200,
        usage_guide="how to",
        price_credits=50,
    )
    assert "example_outputs" not in detail.model_dump()


def test_public_adn_card_rejects_example_outputs_injection():
    """Filet anti-leak : example_outputs injecté ne doit pas ressortir."""
    card = AdnPublicCard.model_validate({
        "id": uuid4(),
        "artist": _artist_dict(),
        "description": "X" * 200,
        "usage_guide": "guide",
        "price_credits": 50,
        "example_outputs": "GATED PREMIUM EXAMPLES",
    })
    dumped = card.model_dump()
    assert "example_outputs" not in dumped


# -----------------------------------------------------------------------------
# Library — DOIT contenir prompt_text et example_outputs (contenu payé)
# -----------------------------------------------------------------------------

def test_library_prompt_item_includes_prompt_text():
    item = LibraryPromptItem(
        unlocked_id=uuid4(),
        unlocked_at=NOW,
        prompt_id=uuid4(),
        title="Prompt that I bought",
        description="Pitch",
        prompt_text="THE FULL PAYLOAD HERE",
        price_credits=42,
        created_at=NOW,
        artist=ArtistPublicCard(**_artist_dict()),
    )
    assert item.prompt_text == "THE FULL PAYLOAD HERE"
    assert "prompt_text" in item.model_dump()


def test_library_adn_item_includes_example_outputs():
    item = LibraryAdnItem(
        adn_id=uuid4(),
        owned_at=NOW,
        description="X" * 200,
        usage_guide="guide",
        example_outputs="full premium examples",
        price_credits=50,
        artist=ArtistPublicCard(**_artist_dict()),
    )
    assert item.example_outputs == "full premium examples"
    assert "example_outputs" in item.model_dump()


def test_library_prompt_requires_prompt_text():
    """Si on construit une LibraryPromptItem sans prompt_text, ça pète :
    on ne veut PAS d'item de library sans le contenu acheté."""
    with pytest.raises(ValidationError):
        LibraryPromptItem(
            unlocked_id=uuid4(),
            unlocked_at=NOW,
            prompt_id=uuid4(),
            title="Title",
            description=None,
            # prompt_text manquant
            artist=ArtistPublicCard(**_artist_dict()),
        )


# -----------------------------------------------------------------------------
# EffectivePricePreview — invariants
# -----------------------------------------------------------------------------

def test_effective_price_preview_consistent():
    """Snapshot : les 3 champs sont indépendants, pas de validation logique
    inter-champs (c'est le service qui garantit paid <= base_price)."""
    p = EffectivePricePreview(base_price=10, paid=7, perk_applied=True)
    assert p.base_price == 10 and p.paid == 7 and p.perk_applied is True


def test_effective_price_no_perk_returns_base():
    p = EffectivePricePreview(base_price=10, paid=10, perk_applied=False)
    assert p.paid == p.base_price


# -----------------------------------------------------------------------------
# Cross-schema : aucune ressemblance public vs library qui révélerait
# accidentellement du contenu gated
# -----------------------------------------------------------------------------

def test_public_prompt_fields_are_strict_subset_of_library_fields_minus_gated():
    """Doc-as-test : les champs publics sont inclus dans library MOINS le
    contenu gated. Empêche les divergences silencieuses."""
    public_fields = set(PromptPublicCard.model_fields.keys())
    library_fields = set(LibraryPromptItem.model_fields.keys())
    # Champs publics doivent tous être dans library (sauf "id" qui devient "prompt_id")
    public_to_library = public_fields - {"id"}
    assert public_to_library.issubset(library_fields | {"prompt_id"}), (
        f"Champs publics absents de library: {public_to_library - library_fields}"
    )
    # Library doit avoir prompt_text en plus
    assert "prompt_text" in library_fields
    # Public ne doit PAS avoir prompt_text
    assert "prompt_text" not in public_fields


def test_public_adn_fields_strict_subset_of_library_minus_gated():
    public_fields = set(AdnPublicCard.model_fields.keys())
    library_fields = set(LibraryAdnItem.model_fields.keys())
    # Library doit avoir example_outputs (gated)
    assert "example_outputs" in library_fields
    # Public ne doit PAS avoir example_outputs
    assert "example_outputs" not in public_fields
