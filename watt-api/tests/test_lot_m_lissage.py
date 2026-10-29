"""Lot M — lissage : aperçus à l'endroit (B1)."""
import io

from PIL import Image

from app.services.images import _generate_preview, _orientation_exif


def _photo_couchee() -> bytes:
    # 40 × 20 en pixels, mais l'EXIF dit « tourner de 90° » (orientation 6),
    # comme une photo prise téléphone à la verticale.
    img = Image.new("RGB", (40, 20), (200, 30, 30))
    exif = img.getexif()
    exif[0x0112] = 6
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_apercu_applique_orientation_exif():
    data = _photo_couchee()
    assert _orientation_exif(data) == 6
    with Image.open(io.BytesIO(_generate_preview(data))) as apercu:
        assert apercu.size == (20, 40)


def test_apercu_sans_exif_inchange():
    img = Image.new("RGB", (40, 20), (0, 0, 0))
    out = io.BytesIO()
    img.save(out, format="PNG")
    data = out.getvalue()
    assert _orientation_exif(data) == 1
    with Image.open(io.BytesIO(_generate_preview(data))) as apercu:
        assert apercu.size == (40, 20)


def test_feuille_de_lissage_injectee_sur_les_pages():
    from app.routers.pages import injecter_pwa

    html = injecter_pwa("<html><head><title>x</title></head><body></body></html>", actif=False)
    assert "/ui/pwa/lissage.css?v=" in html
    # Chargée APRÈS les correctifs mobiles : c'est elle qui harmonise.
    assert html.index("lissage.css") > html.index("mobile.css")


def test_lissage_css_existe_et_garde_les_couleurs_watt():
    from pathlib import Path

    css = (Path(__file__).resolve().parents[2] / "ui" / "pwa" / "lissage.css").read_text(encoding="utf-8")
    for couleur in ("#3d7bff", "#cc88ff", "#ffd700"):
        assert couleur in css
