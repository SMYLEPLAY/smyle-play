"""
C5 — Pricing du pack « œuvre complète » (compute_oeuvre_pack_price).

Fonction PURE (pas de DB) : on vérifie la cascade des perks et le plafond.
  - perk artiste -30% appliqué PAR FACE en amont ;
  - remise pack -15% sur la somme ;
  - le perk -20% « ADN collection » N'est PAS appliqué au pack (perk aval) ;
  - plancher : jamais < nombre de faces.
"""
from app.services.credits import compute_oeuvre_pack_price


class TestOeuvrePackPricing:
    def test_no_artist_perk(self):
        # (40 + 35) * 0.85 = 63.75 → 63 (arrondi inférieur).
        assert compute_oeuvre_pack_price([40, 35], False) == 63

    def test_with_artist_perk(self):
        # Par face -30% : 40→28, 35→24 ; somme 52 ; *0.85 = 44.2 → 44.
        assert compute_oeuvre_pack_price([40, 35], True) == 44

    def test_artist_perk_cheaper_than_without(self):
        base = compute_oeuvre_pack_price([100, 100], False)
        perked = compute_oeuvre_pack_price([100, 100], True)
        assert perked < base
        assert base == 170      # 200 * 0.85
        assert perked == 119    # (70+70) * 0.85

    def test_price_floor_never_zero(self):
        # Cumul max des remises sur des prix minuscules → plancher = nb faces.
        assert compute_oeuvre_pack_price([1, 1], True) == 2
        assert compute_oeuvre_pack_price([1, 1], False) >= 2

    def test_empty_raises(self):
        import pytest
        with pytest.raises(ValueError):
            compute_oeuvre_pack_price([], False)
