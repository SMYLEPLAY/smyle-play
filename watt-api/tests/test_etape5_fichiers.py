"""Étape 5 (2026-10-02) — contrôle des fichiers envoyés.

Type RÉEL par signature (l'extension et le Content-Type annoncés sont
ignorés), taille max par type (config.py), refus des SVG / HTML / scripts
déguisés, image décodable, nom de fichier généré côté serveur, plafond d'une
requête d'envoi complète. Messages en français.
"""
import io
import uuid

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.config import settings
from app.core import fichiers as f


# ── Fabriques de fichiers ──────────────────────────────────────────────────

def _image(fmt: str, taille=(16, 16)) -> bytes:
    buf = io.BytesIO()
    mode = "RGB" if fmt in ("JPEG",) else "RGBA"
    Image.new(mode, taille, (200, 30, 30, 255)[: len(mode)]).save(buf, format=fmt)
    return buf.getvalue()


PNG = _image("PNG")
JPG = _image("JPEG")
WEBP = _image("WEBP")
GIF = _image("GIF")
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
SVG_NU = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
HTML = b"\xef\xbb\xbf  <!DOCTYPE html><html><body><script>alert(document.cookie)</script>"
# Signature PNG valide suivie d'un script : « polyglotte » grossier.
PNG_PIEGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16 + b"<script>alert(1)</script>"
PNG_CASSE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

MP3_ID3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64
MP3_TRAME = b"\xff\xfb\x90\x64" + b"\x00" * 64
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64
FLAC = b"fLaC\x00\x00\x00\x22" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64
M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + b"\x00" * 64
AAC = b"\xff\xf1\x50\x80" + b"\x00" * 64
WEBM = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00" + b"\x00" * 64
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00" + b"\x00" * 64


# ── Détection ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("data,attendu", [
    (PNG, "png"), (JPG, "jpg"), (WEBP, "webp"), (GIF, "gif"),
    (SVG, None), (HTML, None), (MP3_ID3, None), (b"", None),
])
def test_detecter_image(data, attendu):
    assert f.detecter_image(data) == attendu


@pytest.mark.parametrize("data,attendu", [
    (MP3_ID3, "mp3"), (MP3_TRAME, "mp3"), (WAV, "wav"), (FLAC, "flac"),
    (OGG, "ogg"), (M4A, "m4a"), (AAC, "aac"), (WEBM, "webm"),
    (PNG, None), (HTML, None), (SVG, None), (b"x" * 40, None),
])
def test_detecter_audio(data, attendu):
    assert f.detecter_audio(data) == attendu


@pytest.mark.parametrize("data,attendu", [
    (MP4, "mp4"), (MOV, "mov"), (WEBM, "webm"),
    (PNG, None), (HTML, None), (MP3_ID3, None),
])
def test_detecter_video(data, attendu):
    assert f.detecter_video(data) == attendu


@pytest.mark.parametrize("data", [SVG, SVG_NU, HTML, PNG_PIEGE, b"  <html>"])
def test_balisage_detecte(data):
    assert f.contient_balisage(data)


@pytest.mark.parametrize("data", [PNG, JPG, WEBP, GIF, MP3_ID3, WAV, MP4])
def test_fichiers_legitimes_sans_balisage(data):
    assert not f.contient_balisage(data)


# ── Vérifications complètes ────────────────────────────────────────────────

def test_verifier_image_renvoie_le_vrai_type():
    assert f.verifier_image(PNG, ("png", "jpg", "webp")) == "png"
    assert f.verifier_image(JPG, ("png", "jpg", "webp")) == "jpg"


@pytest.mark.parametrize("data", [SVG, SVG_NU, HTML, PNG_PIEGE])
def test_verifier_image_refuse_le_balisage(data):
    with pytest.raises(HTTPException) as e:
        f.verifier_image(data, ("png", "jpg", "webp"))
    assert e.value.status_code == 400
    assert "SVG" in e.value.detail


def test_verifier_image_refuse_format_non_autorise():
    with pytest.raises(HTTPException) as e:
        f.verifier_image(GIF, ("png", "jpg", "webp"))
    assert "pas une image valide" in e.value.detail


def test_verifier_image_refuse_image_cassee():
    with pytest.raises(HTTPException) as e:
        f.verifier_image(PNG_CASSE, ("png",))
    assert "illisible" in e.value.detail


def test_verifier_image_refuse_trop_de_pixels(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_IMAGE_PIXELS", 100)
    with pytest.raises(HTTPException) as e:
        f.verifier_image(PNG, ("png",))
    assert "trop grande" in e.value.detail


def test_verifier_audio_et_video():
    assert f.verifier_audio(MP3_ID3) == "mp3"
    with pytest.raises(HTTPException) as e:
        f.verifier_audio(HTML)
    assert "audio" in e.value.detail
    with pytest.raises(HTTPException):
        f.verifier_audio(PNG)
    assert f.verifier_video(MP4) == "mp4"
    with pytest.raises(HTTPException):
        f.verifier_video(SVG)


def test_mime_deduit_du_contenu():
    assert f.mime_pour("png") == "image/png"
    assert f.mime_pour("mp3") == "audio/mpeg"
    assert f.mime_pour("webm", video=True) == "video/webm"
    assert f.mime_pour("webm") == "audio/webm"


async def test_lecture_bornee():
    up = UploadFile(file=io.BytesIO(b"a" * (2 * 1024 * 1024 + 1)), filename="x.mp3")
    with pytest.raises(HTTPException) as e:
        await f.lire_fichier_borne(up, 2 * 1024 * 1024)
    assert e.value.status_code == 413
    assert "Limite : 2 Mo" in e.value.detail

    vide = UploadFile(file=io.BytesIO(b""), filename="x.mp3")
    with pytest.raises(HTTPException) as e:
        await f.lire_fichier_borne(vide, 1024)
    assert e.value.status_code == 400

    ok = UploadFile(file=io.BytesIO(PNG), filename="x.png")
    assert await f.lire_fichier_borne(ok, 1024 * 1024) == PNG


async def test_image_ia_extension_deduite_du_contenu():
    """Un PNG nommé .jpg est stocké comme PNG (et pas l'inverse)."""
    from app.routers.images import _lire_image_controlee

    up = UploadFile(file=io.BytesIO(PNG), filename="photo.jpg")
    data, ext = await _lire_image_controlee(up)
    assert ext == "png" and data == PNG


# ── Routes réelles (R2 simulé) ─────────────────────────────────────────────

class _FauxR2:
    def __init__(self):
        self.objets: dict[str, dict] = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objets[Key] = {"bucket": Bucket, "type": ContentType, "taille": len(Body)}


@pytest.fixture
def faux_r2(monkeypatch):
    import app.services.r2 as r2

    stub = _FauxR2()
    monkeypatch.setattr(r2, "is_configured", lambda: True)
    monkeypatch.setattr(r2, "get_r2_client", lambda: stub)
    return stub


async def test_avatar_svg_deguise_refuse(client, auth_headers, faux_r2):
    r = await client.post(
        "/watt/upload-image",
        files={"file": ("avatar.png", SVG, "image/png")},
        data={"kind": "avatar"},
        headers=auth_headers,
    )
    assert r.status_code == 400, r.text
    assert "SVG" in r.json()["detail"]
    assert faux_r2.objets == {}


async def test_avatar_html_deguise_refuse(client, auth_headers, faux_r2):
    r = await client.post(
        "/watt/upload-image",
        files={"file": ("avatar.jpg", HTML, "image/jpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert faux_r2.objets == {}


async def test_avatar_valide_nom_et_type_cote_serveur(client, auth_headers, faux_r2):
    # PNG annoncé comme JPEG avec un nom piégé : le serveur s'en moque.
    r = await client.post(
        "/watt/upload-image",
        files={"file": ("../../evil.jpg.html", PNG, "image/jpeg")},
        data={"kind": "avatar"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    assert key.startswith("images/avatar/") and key.endswith(".png")
    assert "evil" not in key
    assert faux_r2.objets[key]["type"] == "image/png"


async def test_avatar_trop_lourd(client, auth_headers, faux_r2, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_AVATAR_MB", 1)
    gros = PNG + b"\x00" * (1024 * 1024)
    r = await client.post(
        "/watt/upload-image", files={"file": ("a.png", gros, "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 413
    assert "Limite : 1 Mo" in r.json()["detail"]


async def test_son_valide_et_son_deguise(client, auth_headers, faux_r2):
    r = await client.post(
        "/watt/upload", files={"file": ("mon son.wav", MP3_ID3, "audio/wav")},
        data={"name": "Mon son"}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    # Lot A (C1) : la clé est rangée sous le dossier du compte.
    prefixe, nom = key.rsplit("/", 1)
    assert prefixe.startswith("tracks/") and prefixe != "tracks"
    assert nom.startswith("mon-son-") and key.endswith(".mp3")
    assert faux_r2.objets[key]["type"] == "audio/mpeg"

    r = await client.post(
        "/watt/upload", files={"file": ("x.mp3", HTML, "audio/mpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "audio" in r.json()["detail"]


async def test_voix_trop_lourde(client, auth_headers, faux_r2, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_VOICE_MB", 1)
    r = await client.post(
        "/watt/upload-voice",
        files={"file": ("v.mp3", MP3_ID3 + b"\x00" * (1024 * 1024), "audio/mpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 413


async def test_couverture_playlist(client, auth_headers, test_user, faux_r2):
    r = await client.post(
        "/watt/upload-playlist-cover",
        files={"file": ("cover.webm", MP4, "video/webm")},
        data={"userId": "../autre-compte", "name": "<script>"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    key = r.json()["r2_key"]
    assert key.startswith(f"PLAYLISTS/{test_user['id']}/") and key.endswith(".mp4")
    assert "autre" not in key and "script" not in key
    assert faux_r2.objets[key]["type"] == "video/mp4"

    r = await client.post(
        "/watt/upload-playlist-cover",
        files={"file": ("cover.mp4", PNG, "video/mp4")},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "vidéo" in r.json()["detail"]


async def test_image_ia_svg_refusee(client, auth_headers, test_user, faux_r2):
    from sqlalchemy import update

    from app.database import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        await db.execute(
            update(User).where(User.id == test_user["id"]).values(profile_public=True)
        )
        await db.commit()
    form = {
        "title": "Test image IA", "image_platform": "chatgpt", "image_model_version": "4o",
        "prompt_text": "un chat", "price_credits": "5",
    }
    for nom, contenu in (("x.png", SVG), ("x.png", PNG_CASSE), ("x.webp", HTML)):
        r = await client.post(
            "/artist/me/images", files={"file": (nom, contenu, "image/png")},
            data=form, headers=auth_headers,
        )
        assert r.status_code == 400, (nom, r.text)
    assert faux_r2.objets == {}


# ── Plafond d'une requête d'envoi complète ─────────────────────────────────

async def test_requete_trop_lourde_content_length(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_REQUEST_MB", 1)
    r = await client.post(
        "/watt/upload-image",
        files={"file": ("a.png", PNG + b"\x00" * (2 * 1024 * 1024), "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 413
    assert "Envoi trop lourd" in r.json()["detail"]
    # La réponse 413 porte bien les en-têtes de sécurité.
    assert r.headers.get("x-content-type-options") == "nosniff"


async def test_requete_trop_lourde_sans_content_length(client, auth_headers, monkeypatch):
    """Corps envoyé en morceaux sans Content-Length : coupé au plafond."""
    monkeypatch.setattr(settings, "UPLOAD_MAX_REQUEST_MB", 1)
    limite = uuid.uuid4().hex
    entete = (
        f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n"
    ).encode()

    async def corps():
        yield entete + PNG
        for _ in range(3):
            yield b"\x00" * (512 * 1024)
        yield f"\r\n--{limite}--\r\n".encode()

    r = await client.post(
        "/watt/upload-image",
        content=corps(),
        headers={**auth_headers, "Content-Type": f"multipart/form-data; boundary={limite}"},
    )
    assert r.status_code == 413
    assert "Envoi trop lourd" in r.json()["detail"]


async def test_requete_json_non_concernee(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_REQUEST_MB", 0)
    r = await client.post("/auth/login", json={"email": "x@y.fr", "password": "abcdefgh"})
    assert r.status_code != 413


# ── Galerie : tout le lot est contrôlé avant le premier envoi ──────────────

@pytest.fixture
async def image_possedee(test_user):
    from sqlalchemy import delete

    from app.database import SessionLocal
    from app.models.prompt import Prompt
    from app.models.prompt_gallery_image import PromptGalleryImage
    from app.services.images import create_image

    async with SessionLocal() as db:
        img = await create_image(
            db, artist_id=test_user["id"], title="Galerie test", description=None,
            prompt_text="un chat", image_platform="chatgpt", image_model_version="4o",
            image_settings=None, negative_prompt=None, price_credits=5, max_supply=None,
            image_r2_key="images/originals/x.png", preview_r2_key="images/previews/x.jpg",
        )
        await db.commit()
        image_id = img.id
    try:
        yield image_id
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(PromptGalleryImage).where(PromptGalleryImage.prompt_id == image_id))
            await db.execute(delete(Prompt).where(Prompt.id == image_id))
            await db.commit()


@pytest.fixture
def faux_r2_images(faux_r2, monkeypatch):
    import app.services.images as svc

    monkeypatch.setattr(svc, "is_configured", lambda: True)
    monkeypatch.setattr(svc, "get_r2_client", lambda: faux_r2)
    return faux_r2


async def test_galerie_lot_piege_rien_n_est_envoye(client, auth_headers, image_possedee, faux_r2_images):
    r = await client.post(
        f"/artist/me/images/{image_possedee}/gallery",
        files=[("files", ("a.png", PNG, "image/png")), ("files", ("b.png", SVG, "image/png"))],
        headers=auth_headers,
    )
    assert r.status_code == 400, r.text
    assert faux_r2_images.objets == {}


async def test_galerie_lot_valide(client, auth_headers, image_possedee, faux_r2_images):
    r = await client.post(
        f"/artist/me/images/{image_possedee}/gallery",
        files=[("files", ("a.jpg", PNG, "image/jpeg")), ("files", ("b.png", JPG, "image/png"))],
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["count"] == 2
    originaux = sorted(
        v["type"] for k, v in faux_r2_images.objets.items() if k.startswith("images/originals/")
    )
    # Le type stocké vient du contenu, pas du nom ni du Content-Type annoncés.
    assert originaux == ["image/jpeg", "image/png"]
