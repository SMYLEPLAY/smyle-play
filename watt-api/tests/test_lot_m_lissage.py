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
