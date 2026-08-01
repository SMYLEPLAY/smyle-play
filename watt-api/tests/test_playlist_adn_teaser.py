"""Teaser ADN Playlist — tests DB-free des schémas (reconstruction de la
partie utile de l'ex-PR #401 ; la fuite seed_prompt d'origine est déjà
fermée : PlaylistRead n'expose plus le champ du tout)."""

import pytest
from pydantic import ValidationError

from app.schemas.playlist import (
    PlaylistCreate,
    PlaylistRead,
    PlaylistUpdate,
    PlaylistWithTracks,
)


def test_playlist_read_n_expose_jamais_le_genome():
    # La projection publique "liste" ne DOIT pas avoir de champ seed_prompt.
    assert "seed_prompt" not in PlaylistRead.model_fields
    assert "dna_description" in PlaylistRead.model_fields


def test_teaser_expose_dans_le_detail():
    assert "dna_description" in PlaylistWithTracks.model_fields


def test_teaser_borne_2000():
    PlaylistCreate(title="ok", dna_description="x" * 2000)  # borne incluse
    with pytest.raises(ValidationError):
        PlaylistCreate(title="ok", dna_description="x" * 2001)
    with pytest.raises(ValidationError):
        PlaylistUpdate(dna_description="x" * 2001)


def test_teaser_optionnel():
    assert PlaylistCreate(title="ok").dna_description is None
