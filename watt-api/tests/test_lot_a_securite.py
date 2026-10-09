"""
Lot A — sécurité urgente (audit du 7 octobre 2026).

Un test (au moins) par correctif :
  C1  fichiers : clé R2 / URL audio / pochette = envois de CE compte ;
      suppression DOUCE (profil + tableau de bord), sans purge du stockage ;
      `r2_key` absent des réponses.
  E1  statiques : liste blanche de chemins ; /docs fermé par défaut.
  E2  recettes : propriété exigée (son, liaison image, Œuvre, pack).
  E3  contenus retirés : absents des listes publiques, du proxy audio.
  M1  auth optionnelle : version de jeton + compte suspendu vérifiés ;
      suppression depuis le profil = auth complète.
  M2  stock d'édition limitée recompté sous verrou.
  +   GET /tracks/ supprimée ; emails échappés ; mot de passe ≤ 72 ;
      parrainage versé une seule fois ; écoutes limitées et dédoublonnées.

Postgres requis (cf. conftest.py), sauf les tests marqués « sans base ».
"""
import asyncio
import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.playlist import Playlist, PlaylistTrack
from app.models.prompt import Prompt
from app.models.referral import Referral, ReferralStatus
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import ResetPasswordRequest, UserCreate, UserLogin
from app.services.media_ownership import (
    image_prefix,
    key_owned_by,
    media_url_key,
    safe_image_kind,
    track_audio_prefix,
)
from app.services.users import create_user, verify_password, hash_password

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PWD = "12345678"


# ─── Aides ─────────────────────────────────────────────────────────────────

async def _user(*, public: bool = True, balance: int = 0) -> dict:
    suffix = uuid.uuid4().hex[:10]
    email = f"pytest-lota-{suffix}@smyleplay.example"
    name = f"LotA Artiste {suffix}"
    async with SessionLocal() as db:
        uid = (await create_user(db, UserCreate(email=email, password=_PWD))).id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET profile_public = :p, artist_name = :n, "
                "credits_balance = :b, smyles_achetes = :b, smyles_gagnes = 0, "
                "smyles_promo = 0 WHERE id = :u"
            ),
            {"p": public, "n": name, "b": balance, "u": uid},
        )
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return {"id": uid, "email": email, "slug": f"lota-artiste-{suffix}"}


async def _login(client, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": _PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _prompt(artist_id, **kw) -> uuid.UUID:
    data = dict(
        artist_id=artist_id, title=f"Recette {uuid.uuid4().hex[:6]}",
        description="Tagline", prompt_text="X" * 100, price_credits=10,
        is_published=True,
    )
    data.update(kw)
    async with SessionLocal() as db:
        p = Prompt(**data)
        db.add(p)
        await db.commit()
        return p.id


async def _track(artist_id, **kw) -> uuid.UUID:
    data = dict(artist_id=artist_id, title=f"Son {uuid.uuid4().hex[:6]}")
    data.update(kw)
    async with SessionLocal() as db:
        t = Track(**data)
        db.add(t)
        await db.commit()
        return t.id


async def _get(model, oid):
    async with SessionLocal() as db:
        return await db.get(model, oid)


async def _cleanup(*uids) -> None:
    async with SessionLocal() as db:
        from app.models.dna import DNA

        for uid in uids:
            await db.execute(
                text("UPDATE prompts SET linked_prompt_id = NULL, linked_track_id = NULL "
                     "WHERE artist_id = :u"), {"u": uid})
            await db.execute(delete(Playlist).where(Playlist.owner_id == uid))
            await db.execute(delete(DNA).where(DNA.artist_id == uid))
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.execute(text(
            "UPDATE users SET credits_balance = 0, smyles_achetes = 0, "
            "smyles_gagnes = 0, smyles_promo = 0 WHERE is_treasury = TRUE"))
        await db.commit()


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeR2:
    def __init__(self):
        self.puts: list[str] = []

    def put_object(self, **kw):
        self.puts.append(kw["Key"])

    def head_object(self, **kw):
        # Parcours V1 : la publication d'un son vérifie que l'audio existe.
        if kw["Key"] not in self.puts:
            raise KeyError(kw["Key"])
        return {}


# ═══ C1 — propriété des fichiers (sans base) ════════════════════════════════

async def test_c1_cles_au_nom_du_compte():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert track_audio_prefix(a) == f"tracks/{a}"
    assert key_owned_by(f"tracks/{a}/mon-son-0123abcd.wav", a)
    assert not key_owned_by(f"tracks/{a}/mon-son.wav", b)
    assert not key_owned_by("tracks/ancien-son-0123abcd.wav", a)       # pas de dossier compte
    assert not key_owned_by(f"tracks/{a}/../{b}/x.wav", a)
    assert not key_owned_by(f"tracks/{a}/sous/dossier.wav", a)
    assert key_owned_by(f"{image_prefix('track-cover', a)}/abc.png", a)
    assert not key_owned_by(f"images/track-cover/{b}/abc.png", a)
    # Dossiers réservés au serveur : jamais choisissables ni « possédés ».
    assert safe_image_kind("originals") == "image"
    assert safe_image_kind("previews") == "image"
    assert not key_owned_by(f"images/originals/{a}/x.png", a)
    assert not key_owned_by("images/previews/x.jpg", a)


async def test_c1_url_vers_notre_stockage_detectee():
    a = uuid.uuid4()
    assert media_url_key(f"/watt/stream/tracks/{a}/s.wav") == (True, f"tracks/{a}/s.wav")
    assert media_url_key(f"https://watt.place/watt/images/images/cover/{a}/x.png") == (
        True, f"images/cover/{a}/x.png")
    assert media_url_key("https://pub-zzz.r2.dev/tracks/x%20y.wav") == (True, "tracks/x y.wav")
    assert media_url_key("https://cdn.exemple.org/son.mp3") == (False, None)
    assert media_url_key(None) == (False, None)


# ═══ C1 — création d'un son (HTTP) ══════════════════════════════════════════

async def test_c1_creation_refuse_les_fichiers_d_autrui(client):
    a, b = await _user(), await _user()
    try:
        h = await _login(client, a["email"])
        base = {"title": "Son", "full_prompt": "deep house 128bpm"}
        autrui = f"tracks/{b['id']}/son-de-b-0123abcd.wav"
        for extra in (
            {"r2_key": autrui},
            {"audio_url": f"/watt/stream/{autrui}"},
            {"audio_url": f"https://pub-x.r2.dev/{autrui}"},
            {"r2_key": "tracks/ancien-format-0123abcd.wav"},
            {"cover_url": f"/watt/images/images/track-cover/{b['id']}/c.png"},
            {"cover_url": "/watt/images/images/originals/abc.png"},
        ):
            r = await client.post("/tracks/", json={**base, **extra}, headers=h)
            assert r.status_code == 422, (extra, r.text)
        async with SessionLocal() as db:
            n = (await db.execute(
                select(func.count(Track.id)).where(Track.artist_id == a["id"])
            )).scalar()
        assert n == 0, "aucun son ne doit avoir été créé"

        # Fichiers à soi + URL externe : accepté, et la clé n'est pas renvoyée.
        mine = f"tracks/{a['id']}/mon-son-0123abcd.wav"
        r = await client.post("/tracks/", json={
            **base, "r2_key": mine, "audio_url": f"/watt/stream/{mine}",
            "cover_url": f"/watt/images/images/track-cover/{a['id']}/c.png",
        }, headers=h)
        assert r.status_code == 201, r.text
        tr = r.json()["track"]
        assert "r2_key" not in tr
        assert tr["stream_url"] == f"/watt/stream/{mine}"
        # Parcours V1 : un son se publie avec SON fichier audio envoyé sur
        # WATT — une URL externe seule est refusée.
        r = await client.post("/tracks/", json={
            **base, "audio_url": "https://cdn.exemple.org/son.mp3"}, headers=h)
        assert r.status_code == 422, r.text

        r = await client.get("/tracks/me", headers=h)
        assert r.status_code == 200
        assert all("r2_key" not in t for t in r.json())
    finally:
        await _cleanup(a["id"], b["id"])


async def test_c1_patch_pochette(client):
    a, b = await _user(), await _user()
    ancienne = "/watt/images/images/track-cover/ancienne-cle.jpg"   # avant Lot A
    tid = await _track(a["id"], cover_url=ancienne)
    try:
        h = await _login(client, a["email"])
        # Renvoyer la pochette existante (ancien format) : toujours accepté.
        r = await client.patch(f"/tracks/{tid}", json={"cover_url": ancienne, "title": "Nouveau"}, headers=h)
        assert r.status_code == 200, r.text
        r = await client.patch(f"/tracks/{tid}", json={
            "cover_url": f"/watt/images/images/track-cover/{b['id']}/x.png"}, headers=h)
        assert r.status_code == 422, r.text
        r = await client.patch(f"/tracks/{tid}", json={
            "cover_url": f"/watt/images/images/track-cover/{a['id']}/x.png"}, headers=h)
        assert r.status_code == 200, r.text
        assert "r2_key" not in r.json()
    finally:
        await _cleanup(a["id"], b["id"])


async def test_c1_parcours_createur_complet(client, monkeypatch):
    """Envoi audio + pochette → publication → recette → visible → suppression
    douce depuis le profil : rien n'est effacé du stockage."""
    import app.services.r2 as r2

    a = await _user()
    try:
        h = await _login(client, a["email"])
        # 1. Audio : R2 absent en test → clé « mock » mais déjà au nom du compte.
        monkeypatch.setattr(r2, "is_configured", lambda: False)
        r = await client.post("/watt/upload", headers=h,
                              files={"file": ("s.wav", b"RIFF0000WAVEfmt ", "audio/wav")},
                              data={"name": "Mon son"})
        assert r.status_code == 200, r.text
        key = r.json()["key"]
        assert key.startswith(f"tracks/{a['id']}/")

        # 2. Pochette : R2 simulé → clé images/track-cover/<compte>/…
        fake = _FakeR2()
        monkeypatch.setattr(r2, "is_configured", lambda: True)
        monkeypatch.setattr(r2, "get_r2_client", lambda: fake)
        r = await client.post("/watt/upload-image", headers=h,
                              files={"file": ("c.png", _png_bytes(), "image/png")},
                              data={"kind": "track-cover"})
        assert r.status_code == 200, r.text
        cover = r.json()["url"]
        assert fake.puts and fake.puts[-1].startswith(f"images/track-cover/{a['id']}/")
        r = await client.post("/watt/upload-image", headers=h,
                              files={"file": ("c.png", _png_bytes(), "image/png")},
                              data={"kind": "originals"})
        assert r.status_code == 200, r.text
        assert fake.puts[-1].startswith(f"images/image/{a['id']}/")

        # 3. Publication du son avec ces fichiers. Parcours V1 : le serveur
        #    vérifie que l'audio existe sur le stockage (absent → refus).
        r = await client.post("/tracks/", headers=h, json={
            "title": "Mon son", "full_prompt": "deep house",
            "audio_url": f"/watt/stream/{key}", "r2_key": key, "cover_url": cover,
        })
        assert r.status_code == 422, r.text
        fake.puts.append(key)  # le fichier audio est bien sur le stockage
        r = await client.post("/tracks/", headers=h, json={
            "title": "Mon son", "full_prompt": "deep house",
            "audio_url": f"/watt/stream/{key}", "r2_key": key, "cover_url": cover,
        })
        assert r.status_code == 201, r.text
        tid = r.json()["track"]["id"]

        # 4. Sa recette (à lui) liée après coup.
        rec = await _prompt(a["id"])
        r = await client.patch(f"/tracks/{tid}", json={"prompt_id": str(rec)}, headers=h)
        assert r.status_code == 200, r.text

        r = await client.get("/watt/tracks-recent", params={"limit": 100})
        assert any(t["trackUuid"] == tid for t in r.json()["tracks"])

        # 5. Suppression depuis le profil : douce, aucune purge du stockage.
        purges = []

        async def _purge(k):
            purges.append(k)
            return True

        monkeypatch.setattr(r2, "delete_r2_object", _purge)
        r = await client.delete(f"/watt/tracks/{tid}", headers=h)
        assert r.status_code == 200, r.text
        assert purges == []
        t = await _get(Track, uuid.UUID(tid))
        assert t is not None and t.is_deleted is True and t.r2_key == key
        p = await _get(Prompt, rec)
        assert p.is_published is False and p.is_deleted is False   # retirée de la vente
        r = await client.get("/watt/tracks-recent", params={"limit": 100})
        assert all(x["trackUuid"] != tid for x in r.json()["tracks"])
        # Deuxième suppression : déjà supprimé → 404.
        assert (await client.delete(f"/watt/tracks/{tid}", headers=h)).status_code == 404
    finally:
        await _cleanup(a["id"])


async def test_c1_suppression_douce_tableau_de_bord_et_oeuvre(client):
    """DELETE /tracks/{id} : recette retirée de la vente seulement si aucun
    autre son ne la porte ; l'image de l'Œuvre redevient autonome."""
    from app.services.links import link_image_to_track

    a = await _user()
    rec_partagee = await _prompt(a["id"])
    t1 = await _track(a["id"], prompt_id=rec_partagee)
    t2 = await _track(a["id"], prompt_id=rec_partagee)
    rec_seule = await _prompt(a["id"])
    t3 = await _track(a["id"], prompt_id=rec_seule)
    img = await _prompt(a["id"], product_type="image", prompt_text="néon",
                        image_platform="chatgpt", image_model_version="gpt-4o")
    async with SessionLocal() as db:
        await link_image_to_track(db, owner_id=a["id"], track_id=t3, image_id=img,
                                  bundle_exclusive=True)
        await db.commit()
    try:
        h = await _login(client, a["email"])
        assert (await client.delete(f"/tracks/{t1}", headers=h)).status_code == 204
        assert (await _get(Prompt, rec_partagee)).is_published is True   # t2 la porte encore
        assert (await client.delete(f"/tracks/{t3}", headers=h)).status_code == 204
        assert (await _get(Track, t3)).is_deleted is True
        assert (await _get(Prompt, rec_seule)).is_published is False
        im = await _get(Prompt, img)
        assert im.linked_track_id is None and im.linked_prompt_id is None
        assert im.bundle_exclusive is False and im.is_published is True
        # L'Œuvre n'a plus de page publique.
        assert (await client.get(f"/watt/oeuvres/{img}")).status_code == 404
    finally:
        await _cleanup(a["id"])


async def test_c1_suppression_profil_refusee_a_autrui(client):
    a, b = await _user(), await _user()
    tid = await _track(a["id"])
    try:
        hb = await _login(client, b["email"])
        assert (await client.delete(f"/watt/tracks/{tid}", headers=hb)).status_code == 403
        assert (await client.delete(f"/watt/tracks/{tid}")).status_code == 401
        assert (await _get(Track, tid)).is_deleted is False
    finally:
        await _cleanup(a["id"], b["id"])


async def test_get_tracks_liste_complete_supprimee(client):
    r = await client.get("/tracks/")
    assert r.status_code in (404, 405)


# ═══ E1 — statiques et documentation (sans base) ════════════════════════════

def _static_client() -> TestClient:
    from app.routers.pages import mount_static, router

    app = FastAPI()
    app.include_router(router)
    mount_static(app)
    return TestClient(app, follow_redirects=False)


async def test_e1_liste_blanche_des_statiques(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_EUROS", False)
    monkeypatch.setattr(settings, "SHOW_PALIERS", False)
    monkeypatch.setattr(settings, "SHOW_ALBUMS", False)
    c = _static_client()
    for path in (
        "/data/recipes_backfill_jungle.json", "/data/recipes_backfill_sunset.json",
        "/data/config/univers.json", "/data/config/styles.json",
        "/tracks.json", "/e2e/package.json", "/e2e/playwright.config.js",
        "/scripts/attach_recipes.py", "/agents/orchestrator.py",
        "/assets/the-plan/cover.png", "/watt-api/app/main.py",
        "/banner-demo.html",
        "/.github/workflows/ci.yml", "/ui/../tracks.json",
    ):
        assert c.get(path).status_code == 404, path
    # Parcours V1 — pages masquées : redirection vers l'accueil (plus de 404).
    for path in ("/tarifs.html", "/offres.html", "/oeuvre.html"):
        r = c.get(path)
        assert r.status_code == 302 and r.headers["location"] == "/", path
    for path in ("/index.html", "/style.css", "/dashboard.js", "/artiste.js",
                 "/ui/core/api.js", "/ui/core/tokens.css", "/o.html", "/legal.html"):
        assert c.get(path).status_code == 200, path
    # Pages masquées rouvertes avec leur interrupteur.
    monkeypatch.setattr(settings, "SHOW_EUROS", True)
    monkeypatch.setattr(settings, "SHOW_PALIERS", True)
    monkeypatch.setattr(settings, "SHOW_ALBUMS", True)
    # Rouvertes : l'adresse directe mène à la page officielle.
    assert c.get("/tarifs.html").headers["location"] == "/tarifs"
    assert c.get("/offres.html").headers["location"] == "/offres"
    assert c.get("/oeuvre.html").headers["location"] == "/"
    assert c.get("/tarifs").status_code == 200 and c.get("/offres").status_code == 200


async def test_e1_recettes_retirees_du_depot():
    from app.routers.pages import REPO_ROOT

    assert not list((REPO_ROOT / "data").glob("recipes_backfill_*.json"))


async def test_e1_documentation_api_fermee_par_defaut(monkeypatch):
    from app.main import create_app

    assert settings.API_DOCS_ENABLED is False
    c = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404, path
    monkeypatch.setattr(settings, "API_DOCS_ENABLED", True)
    c = TestClient(create_app())
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/docs").status_code == 200


# ═══ E2 — recettes d'autrui ═════════════════════════════════════════════════

async def test_e2_son_ne_porte_que_ses_recettes(client):
    a, b = await _user(), await _user()
    rec_b = await _prompt(b["id"])
    rec_a = await _prompt(a["id"])
    tid = await _track(a["id"])
    try:
        h = await _login(client, a["email"])
        base = {"title": "Son", "full_prompt": "x",
                "r2_key": f"tracks/{a['id']}/son-0123abcd.wav"}
        r = await client.post("/tracks/", json={**base, "prompt_id": str(rec_b)}, headers=h)
        assert r.status_code == 422, r.text
        r = await client.post("/tracks/", json={**base, "prompt_id": str(uuid.uuid4())}, headers=h)
        assert r.status_code == 422, r.text
        r = await client.patch(f"/tracks/{tid}", json={"prompt_id": str(rec_b)}, headers=h)
        assert r.status_code == 422, r.text
        assert (await _get(Track, tid)).prompt_id is None
        r = await client.post("/tracks/", json={**base, "prompt_id": str(rec_a)}, headers=h)
        assert r.status_code == 201, r.text
        r = await client.patch(f"/tracks/{tid}", json={"prompt_id": str(rec_a)}, headers=h)
        assert r.status_code == 200, r.text
    finally:
        await _cleanup(a["id"], b["id"])


async def test_e2_liaison_image_n_ecrit_pas_la_recette_d_autrui():
    """Morceau de A pointant (ancienne donnée) vers la recette de B : lier une
    image de A au morceau ne touche PAS la recette de B."""
    from app.services.links import link_image_to_track

    a, b = await _user(), await _user()
    rec_b = await _prompt(b["id"])
    tid = await _track(a["id"], prompt_id=rec_b)
    img = await _prompt(a["id"], product_type="image", prompt_text="néon",
                        image_platform="chatgpt", image_model_version="gpt-4o")
    try:
        async with SessionLocal() as db:
            await link_image_to_track(db, owner_id=a["id"], track_id=tid, image_id=img,
                                      bundle_exclusive=True)
            await db.commit()
        rb = await _get(Prompt, rec_b)
        assert rb.linked_prompt_id is None and rb.bundle_exclusive is False
    finally:
        await _cleanup(a["id"], b["id"])


async def test_e2_oeuvre_avec_recette_d_autrui_non_vendable(client):
    from app.services.oeuvre_c4_purchase import OeuvreNotBundlable, buy_oeuvre_atomic

    a, b, acheteur = await _user(), await _user(), await _user(balance=500)
    rec_b = await _prompt(b["id"], price_credits=30)
    img = await _prompt(a["id"], product_type="image", prompt_text="néon",
                        price_credits=40, image_platform="chatgpt",
                        image_model_version="gpt-4o")
    async with SessionLocal() as db:   # lien incohérent forcé en base
        await db.execute(text("UPDATE prompts SET linked_prompt_id = :r WHERE id = :i"),
                         {"r": rec_b, "i": img})
        await db.commit()
    try:
        with pytest.raises(OeuvreNotBundlable):
            async with SessionLocal() as db:
                await buy_oeuvre_atomic(db, buyer_id=acheteur["id"], oeuvre_id=img)
        r = await client.get(f"/watt/oeuvres/{img}")
        if r.status_code == 200:
            body = r.json()
            assert body["bundle"] is None
            assert body["sound"]["recipe"] is None if body.get("sound") else True
        async with SessionLocal() as db:
            n = (await db.execute(select(func.count(UnlockedPrompt.id)).where(
                UnlockedPrompt.current_owner_id == acheteur["id"]))).scalar()
        assert n == 0
    finally:
        await _cleanup(a["id"], b["id"], acheteur["id"])


async def test_e2_pack_avec_recette_d_autrui_refuse():
    from app.services.pack_purchase import PackNotPurchasable, buy_pack_atomic

    a, b, acheteur = await _user(), await _user(), await _user(balance=500)
    rec_b = await _prompt(b["id"], price_credits=80)
    beat_a = await _prompt(a["id"], product_type="beat", prompt_text=None, price_credits=10)
    tid = await _track(a["id"], prompt_id=rec_b, beat_id=beat_a, pack_price_credits=1)
    try:
        with pytest.raises(PackNotPurchasable):
            async with SessionLocal() as db:
                await buy_pack_atomic(db, buyer_id=acheteur["id"], track_id=tid)
    finally:
        await _cleanup(a["id"], b["id"], acheteur["id"])


# ═══ E3 — contenus retirés invisibles ═══════════════════════════════════════

async def test_e3_listes_publiques_et_proxy_audio(client, monkeypatch):
    import app.services.r2 as r2

    a = await _user()
    mot = f"zq{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    common = {"universe": "night-city"}
    vis = await _track(a["id"], title=f"{mot} visible", r2_key=f"tracks/{a['id']}/v.wav", **common)
    sup = await _track(a["id"], title=f"{mot} supprime", r2_key=f"tracks/{a['id']}/s.wav",
                       is_deleted=True, **common)
    ret = await _track(a["id"], title=f"{mot} retire", r2_key=f"tracks/{a['id']}/r.wav",
                       is_deleted=True, taken_down_at=now, **common)
    caches = {str(sup), str(ret)}
    async with SessionLocal() as db:
        pl = Playlist(owner_id=a["id"], title="Pub", visibility="public")
        db.add(pl)
        await db.flush()
        for i, t in enumerate((vis, sup, ret)):
            db.add(PlaylistTrack(playlist_id=pl.id, track_id=t, position=i))
        await db.commit()
        pl_id = pl.id
    try:
        r = await client.get("/watt/tracks-recent", params={"limit": 100})
        ids = {t["trackUuid"] for t in r.json()["tracks"]}
        assert str(vis) in ids and not (ids & caches)

        r = await client.get(f"/watt/artists/{a['slug']}")
        assert r.status_code == 200, r.text
        art = r.json()["artist"]
        assert {t["trackUuid"] for t in art["tracks"]} == {str(vis)}
        assert art["trackCount"] == 1

        r = await client.get("/watt/search/tracks", params={"q": mot})
        if r.status_code == 200:
            ids = {t["id"] for t in r.json()["tracks"]}
            assert str(vis) in ids and not (ids & caches)

        r = await client.get("/watt/tracks-catalog")
        ids = {t["trackUuid"] for t in r.json()["night-city"]["tracks"]}
        assert str(vis) in ids and not (ids & caches)

        r = await client.get(f"/watt/playlists/{pl_id}")
        assert r.status_code == 200, r.text
        assert [t["id"] for t in r.json()["tracks"]] == [str(vis)]

        # Proxy audio : clé d'un son retiré → 404 ; son visible → passe le
        # filtre. Lot E : redirection 302 vers l'objet R2 public (sans
        # domaine public configuré : repli proxy, 503 sans stockage).
        monkeypatch.setattr(r2, "is_configured", lambda: False)
        assert (await client.get(f"/watt/stream/tracks/{a['id']}/s.wav")).status_code == 404
        assert (await client.get(f"/watt/stream/tracks/{a['id']}/r.wav")).status_code == 404
        r = await client.get(f"/watt/stream/tracks/{a['id']}/v.wav")
        assert r.status_code == 302
        assert r.headers["location"].endswith(f"/tracks/{a['id']}/v.wav")
        from app.config import settings as _s
        monkeypatch.setattr(_s, "R2_PUBLIC_BASE_URL", "")
        assert (await client.get(f"/watt/stream/tracks/{a['id']}/v.wav")).status_code == 503

        # Écoute d'un son retiré : pas comptée.
        r = await client.post(f"/watt/plays/{sup}")
        assert r.json()["ok"] is False
    finally:
        await _cleanup(a["id"])


async def test_e3_inventaire_des_requetes_track():
    """Garde-fou : toute nouvelle requête `select(Track` dans les routeurs
    publics doit être relue (filtre E3 ou justification). Liste figée au
    Lot A — si ce test casse, vérifier le filtre puis mettre la liste à jour."""
    import re
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "app"
    trouve = {}
    for f in sorted((racine / "routers").glob("*.py")):
        n = len(re.findall(r"select\(\s*Track\b", f.read_text(encoding="utf-8")))
        if n:
            trouve[f.name] = n
    assert trouve == {
        "beats.py": 1,         # téléchargement payé : is_deleted + créateur
        "images.py": 3,        # cartes image / Œuvres : is_deleted
        "oeuvre.py": 2,        # collection : filtrée ; calcul de possession
        "search.py": 2,        # recherche + compteurs : visible_track_clause
        "trades.py": 1,        # échange : is_deleted
        "watt_compat.py": 12,  # listes filtrées ; plays/suppression par id (Lot E : /watt/adns retirée)
    }, trouve


# ═══ M1 — auth optionnelle ══════════════════════════════════════════════════

async def test_m1_jeton_revoque_ou_compte_suspendu(client):
    from app.auth.jwt import create_access_token

    a = await _user(public=False)
    tid = await _track(a["id"])
    try:
        perime = {"Authorization": "Bearer " + create_access_token(a["email"], token_version=99)}
        # Écriture : refusée avec un jeton révoqué (avant : acceptée).
        assert (await client.delete(f"/watt/tracks/{tid}", headers=perime)).status_code == 401
        # Lecture : le profil privé n'est plus servi en « aperçu créateur ».
        assert (await client.get(f"/watt/artists/{a['slug']}", headers=perime)).status_code == 404
        h = await _login(client, a["email"])
        assert (await client.get(f"/watt/artists/{a['slug']}", headers=h)).status_code == 200
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET is_banned = TRUE WHERE id = :u"), {"u": a["id"]})
            await db.commit()
        assert (await client.get(f"/watt/artists/{a['slug']}", headers=h)).status_code == 404
        assert (await client.delete(f"/watt/tracks/{tid}", headers=h)).status_code == 403
        assert (await _get(Track, tid)).is_deleted is False
    finally:
        await _cleanup(a["id"])


# ═══ M2 — stock sous verrou ═════════════════════════════════════════════════

async def test_m2_edition_unique_vendue_une_seule_fois():
    from app.services.unlocks import PromptNotPurchasable, unlock_prompt_atomic

    artiste = await _user()
    b1, b2 = await _user(balance=100), await _user(balance=100)
    pid = await _prompt(artiste["id"], max_supply=1)

    async def _achat(buyer):
        async with SessionLocal() as db:
            try:
                await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
                await db.commit()
                return "ok"
            except PromptNotPurchasable:
                await db.rollback()
                return "epuise"

    try:
        res = await asyncio.gather(_achat(b1["id"]), _achat(b2["id"]))
        assert sorted(res) == ["epuise", "ok"], res
        async with SessionLocal() as db:
            n = (await db.execute(select(func.count(UnlockedPrompt.id)).where(
                UnlockedPrompt.prompt_id == pid))).scalar()
        assert n == 1
    finally:
        await _cleanup(artiste["id"], b1["id"], b2["id"])


# ═══ Petits correctifs ══════════════════════════════════════════════════════

async def test_emails_echappent_les_textes(monkeypatch):
    import app.services.emails as emails

    envoyes = []

    async def _send(to, subject, html):
        envoyes.append(html)
        return True

    monkeypatch.setattr(emails, "_send", _send)
    piege = '<a href="https://x.example">clique</a>'
    await emails.send_sale_email("a@x.example", item_title=piege, amount=5, buyer_name="<b>Moi</b>")
    await emails.send_receipt_email("a@x.example", item_title=piege, amount=5)
    await emails.send_welcome_email("a@x.example", name="<img src=x>")
    assert envoyes and all("<a href=\"https://x.example\">" not in h for h in envoyes)
    assert all("&lt;a href=" in h for h in envoyes[:2])
    assert "<b>Moi</b>" not in envoyes[0] and "<img src=x>" not in envoyes[2]


async def test_signalement_email_moderateur_echappe(client, monkeypatch):
    import app.services.emails as emails

    envoyes = []

    async def _send(to, subject, html):
        envoyes.append(html)
        return True

    monkeypatch.setattr(emails, "_send", _send)
    monkeypatch.setenv("REPORT_NOTIFY_EMAIL", "modo@x.example")
    r = await client.post("/reports", json={
        "target_type": "track", "target_id": str(uuid.uuid4()),
        "reason": "autre", "detail": "<script>alert(1)</script>",
        "reporter_email": "r@x.example",
    })
    assert r.status_code == 201, r.text
    assert envoyes and all("<script>" not in h for h in envoyes)
    assert any("&lt;script&gt;" in h for h in envoyes)


async def test_mot_de_passe_72_maximum(client):
    ok = "a" * 72
    assert UserCreate(email="x@smyleplay.example", password=ok).password == ok
    for trop in ("a" * 73, "é" * 40):            # 73 caractères ; 80 octets
        with pytest.raises(ValidationError):
            UserCreate(email="x@smyleplay.example", password=trop)
        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="t" * 20, new_password=trop)
    with pytest.raises(ValidationError):
        UserLogin(email="x@smyleplay.example", password="a" * 73)
    assert verify_password("é" * 40, hash_password("motdepasse")) is False
    r = await client.post("/auth/register", json={
        "email": f"pytest-lota-{uuid.uuid4().hex[:8]}@smyleplay.example",
        "password": "a" * 80, "accept_terms": True, "age_confirmed": True})
    assert r.status_code == 422, r.text
    r = await client.post("/auth/login", json={"email": "x@smyleplay.example", "password": "a" * 100})
    assert r.status_code == 422, r.text


async def test_parrainage_verse_une_seule_fois():
    from app.services.referrals import maybe_reward_referral

    parrain, filleul = await _user(), await _user()
    async with SessionLocal() as db:
        db.add(Referral(referrer_id=parrain["id"], referred_id=filleul["id"],
                        status=ReferralStatus.PENDING, reward_credits=10))
        await db.commit()

    async def _tente():
        async with SessionLocal() as db:
            ok = await maybe_reward_referral(db, filleul["id"])
            await db.commit()
            return ok

    try:
        res = await asyncio.gather(_tente(), _tente(), _tente())
        assert sorted(res) == [False, False, True], res
        async with SessionLocal() as db:
            solde = (await db.execute(text(
                "SELECT credits_balance FROM users WHERE id = :u"), {"u": filleul["id"]})).scalar()
        assert solde == 10
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Referral).where(Referral.referred_id == filleul["id"]))
            await db.commit()
        await _cleanup(parrain["id"], filleul["id"])


async def test_ecoutes_dedoublonnees_et_limitees(client):
    from app.core.ratelimit import limiter
    from app.routers import watt_compat

    a = await _user()
    tid = await _track(a["id"])
    watt_compat._recent_plays.clear()
    ip = {"X-Forwarded-For": f"203.0.113.{uuid.uuid4().int % 250 + 1}"}
    try:
        r1 = await client.post(f"/watt/plays/{tid}", headers=ip)
        r2 = await client.post(f"/watt/plays/{tid}", headers=ip)
        assert r1.json() == {"ok": True, "plays": 1}
        assert r2.json() == {"ok": True, "plays": 1}       # même IP + même son : pas de +1
        autre = {"X-Forwarded-For": "198.51.100.77"}
        assert (await client.post(f"/watt/plays/{tid}", headers=autre)).json()["plays"] == 2

        etat = limiter.enabled
        limiter.reset()
        limiter.enabled = True
        try:
            codes = [
                (await client.post(f"/watt/plays/{tid}", headers=ip)).status_code
                for _ in range(61)
            ]
        finally:
            limiter.enabled = etat
            limiter.reset()
        assert codes[:60] == [200] * 60 and codes[60] == 429
    finally:
        watt_compat._recent_plays.clear()
        await _cleanup(a["id"])
