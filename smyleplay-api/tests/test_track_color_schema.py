"""
Étape 2 — Schéma Pydantic TrackCreate.color : regex "#RRGGBB".

Ces tests valident la règle de validation AVANT le hit DB : ils n'ont pas
besoin de fixtures async ni de client HTTP. Ils garantissent que toute
valeur de `color` qui arrive jusqu'au service tracks.create_track_with_dna
est soit None, soit un hex strict à 7 caractères.
"""

import pytest
from pydantic import ValidationError

from app.schemas.track import TrackCreate


class TestTrackCreateColor:
    def test_color_optional_default_none(self) -> None:
        t = TrackCreate(title="Mon son", full_prompt="deep house 128bpm")
        assert t.color is None

    def test_color_explicit_none(self) -> None:
        t = TrackCreate(title="Mon son", full_prompt="deep house 128bpm", color=None)
        assert t.color is None

    @pytest.mark.parametrize(
        "valid_hex",
        [
            "#FFD700",   # or WATT
            "#8800ff",   # violet minuscules
            "#000000",   # noir
            "#FFFFFF",   # blanc
            "#1a2B3c",   # casse mixte
        ],
    )
    def test_valid_hex_colors_accepted(self, valid_hex: str) -> None:
        t = TrackCreate(title="T", full_prompt="x" * 10, color=valid_hex)
        assert t.color == valid_hex

    @pytest.mark.parametrize(
        "invalid",
        [
            "FFD700",       # sans dièse
            "#FFF",         # format court
            "#FFD70",       # trop court
            "#FFD7000",     # trop long
            "rgb(255,0,0)", # autre format
            "red",          # nom CSS
            "",             # vide → non-null mais invalide
            "#GGGGGG",      # hors hex
            " #FFD700 ",    # espaces (strict = pas de strip implicite)
            "#FFD700\n",    # newline en queue
        ],
    )
    def test_invalid_hex_colors_rejected(self, invalid: str) -> None:
        with pytest.raises(ValidationError):
            TrackCreate(title="T", full_prompt="x" * 10, color=invalid)

    def test_color_is_field_of_track_read(self) -> None:
        """Sanity : TrackRead expose le champ `color` pour que le front
        puisse l'utiliser au rendu. Si quelqu'un le retire par erreur,
        ce test saute immédiatement."""
        from app.schemas.track import TrackRead

        assert "color" in TrackRead.model_fields
