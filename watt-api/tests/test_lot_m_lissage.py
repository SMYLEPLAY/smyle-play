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


# ── Lot M — retirer / remettre un profil en vitrine (admin) ─────────────────
import uuid as _uuid_mod

import pytest
import pytest_asyncio
from sqlalchemy import text as _text, update as _update

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers_m(test_user: dict, auth_headers: dict):
    async with SessionLocal() as db:
        await db.execute(_update(User).where(User.id == test_user["id"]).values(is_admin=True))
        await db.commit()
    try:
        yield auth_headers
    finally:
        async with SessionLocal() as db:
            await db.execute(_update(User).where(User.id == test_user["id"]).values(is_admin=False))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_retire_et_remet_un_profil(client, admin_headers_m, auth_headers):
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(
            email=f"pytest-vitrine-{_uuid_mod.uuid4().hex[:8]}@smyleplay.example", password="12345678"))
        uid = u.id
        await db.execute(_text("UPDATE users SET artist_name = :n, profile_public = true WHERE id = :u"),
                         {"n": f"Vitrine {uid.hex[:6]}", "u": uid})
        await db.commit()
    try:
        liste = (await client.get("/admin/profils", headers=admin_headers_m)).json()["profils"]
        assert any(p["id"] == str(uid) and p["enVitrine"] for p in liste)

        r = await client.post(f"/admin/profils/{uid}/vitrine", json={"visible": False}, headers=admin_headers_m)
        assert r.status_code == 200 and r.json()["enVitrine"] is False
        noms = [a.get("artist_name") or a.get("name") for a in (await client.get("/watt/artists")).json().get("artists", [])]
        assert f"Vitrine {uid.hex[:6]}" not in noms

        r = await client.post(f"/admin/profils/{uid}/vitrine", json={"visible": True}, headers=admin_headers_m)
        assert r.json()["enVitrine"] is True
    finally:
        async with SessionLocal() as db:
            await db.execute(_text("DELETE FROM users WHERE id = :u"), {"u": uid})
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_vitrine_reservee_aux_admins(client, auth_headers):
    r = await client.post(f"/admin/profils/{_uuid_mod.uuid4()}/vitrine", json={"visible": False}, headers=auth_headers)
    assert r.status_code == 403
