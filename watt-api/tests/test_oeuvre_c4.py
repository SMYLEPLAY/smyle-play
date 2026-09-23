"""Œuvre C4 (1 son + 1 image) — Lot 2.

Couvre :
  - liaison au niveau du MORCEAU (0093) : un son publié SANS recette reçoit
    une image ; avec recette, la liaison historique recette <-> image est
    posée en plus (rétrocompatibilité) ;
  - 1:1 strict (un morceau = une image, une image = une œuvre), y compris
    entre l'ancienne liaison (recette) et la nouvelle (morceau) ;
  - candidats liables (morceaux sans recette proposés à une image) ;
  - déliaison ;
  - lecture PUBLIQUE /watt/oeuvres/{id} + page à partager /o/{id} avec
    aperçu social (og:title, og:image) ; 404 si privé / retiré / brouillon ;
  - listing public /oeuvres (œuvres « morceau » incluses, avec oeuvreId) ;
  - l'achat de l'Œuvre entière n'existe PAS (bundle = None).
"""
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.services.moderation import takedown_content


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _profil_public(uid, name="Artiste Oeuvre"):
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET profile_public = TRUE, artist_name = :n WHERE id = :u"),
            {"u": uid, "n": name})
        await db.commit()


async def _image(uid, *, published=True, title=None) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title=title or f"Image {uuid.uuid4().hex[:6]}",
                   description="Tagline", prompt_text="un chat au soleil", price_credits=40,
                   is_published=published, product_type="image",
                   image_platform="chatgpt", image_model_version="gpt-4o",
                   preview_r2_key=f"previews/{uuid.uuid4().hex}.webp")
        db.add(p)
        await db.commit()
        return p.id


async def _recette(uid) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title=f"Recette {uuid.uuid4().hex[:6]}",
                   description="Tagline", prompt_text="X" * 100, price_credits=30,
                   is_published=True)
        db.add(p)
        await db.commit()
        return p.id


async def _morceau(uid, *, prompt_id=None, title=None) -> uuid.UUID:
    async with SessionLocal() as db:
        t = Track(artist_id=uid, title=title or f"Son {uuid.uuid4().hex[:6]}",
                  prompt_id=prompt_id, audio_url="https://example.invalid/a.mp3")
        db.add(t)
        await db.commit()
        return t.id


async def _get(model, oid):
    async with SessionLocal() as db:
        return await db.get(model, oid)


async def _cleanup(uid):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE prompts SET linked_prompt_id = NULL, linked_track_id = NULL "
                              "WHERE artist_id = :u"), {"u": uid})
        await db.execute(delete(Track).where(Track.artist_id == uid))
        await db.execute(delete(Prompt).where(Prompt.artist_id == uid))
        await db.commit()


# ─── 1. Liaison au niveau du morceau ──────────────────────────────────────────

async def test_son_sans_recette_recoit_une_image(client, test_user, auth_headers):
    uid = test_user["id"]
    await _profil_public(uid)
    trk = await _morceau(uid, title="Nuit tropicale")
    img = await _image(uid)
    try:
        r = await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                              json={"image_id": str(img)})
        assert r.status_code == 200, r.text
        assert r.json() == {"oeuvreId": str(img), "url": f"/o/{img}"}
        i = await _get(Prompt, img)
        assert i.linked_track_id == trk and i.linked_prompt_id is None

        r = await client.get(f"/artist/me/tracks/{trk}/link", headers=auth_headers)
        assert r.json()["linked"] is True and r.json()["oeuvreId"] == str(img)

        r = await client.get(f"/watt/oeuvres/{img}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "Nuit tropicale"
        assert d["sound"]["trackId"] == str(trk)
        assert d["sound"]["recipe"] is None             # écoute libre, pas d'achat
        assert d["sound"]["streamUrl"]
        assert d["image"]["id"] == str(img) and d["image"]["priceCredits"] == 40
        assert d["creator"]["slug"]
        assert d["bundle"] is None                      # prix de l'Œuvre : décision en attente
        # Anti-fuite : jamais la recette de l'image ni son original.
        assert "prompt_text" not in r.text and "image_r2_key" not in r.text
    finally:
        await _cleanup(uid)


async def test_son_avec_recette_pose_aussi_la_liaison_historique(client, test_user, auth_headers):
    uid = test_user["id"]
    await _profil_public(uid)
    rec = await _recette(uid)
    trk = await _morceau(uid, prompt_id=rec)
    img = await _image(uid)
    try:
        r = await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                              json={"image_id": str(img)})
        assert r.status_code == 200, r.text
        i, s = await _get(Prompt, img), await _get(Prompt, rec)
        assert i.linked_track_id == trk
        assert i.linked_prompt_id == rec and s.linked_prompt_id == img
        d = (await client.get(f"/watt/oeuvres/{img}")).json()
        assert d["sound"]["recipe"]["id"] == str(rec)   # moitié son achetable
    finally:
        await _cleanup(uid)


async def test_oeuvre_historique_recette_image_lisible(client, test_user, auth_headers):
    """Rétrocompatibilité : une Œuvre liée AVANT 0093 (recette <-> image) se lit
    sur /watt/oeuvres/{id}, et son morceau est retrouvé par tracks.prompt_id."""
    uid = test_user["id"]
    await _profil_public(uid)
    rec = await _recette(uid)
    trk = await _morceau(uid, prompt_id=rec)
    img = await _image(uid)
    try:
        r = await client.post(f"/artist/me/prompts/{img}/link", headers=auth_headers,
                              json={"other_prompt_id": str(rec)})
        assert r.status_code == 204, r.text
        d = (await client.get(f"/watt/oeuvres/{img}")).json()
        assert d["sound"]["trackId"] == str(trk)
        assert d["sound"]["recipe"]["id"] == str(rec)
        # Le morceau est bien vu comme lié (pas de seconde image possible).
        img2 = await _image(uid)
        r = await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                              json={"image_id": str(img2)})
        assert r.status_code == 409
    finally:
        await _cleanup(uid)


async def test_un_pour_un_strict(client, test_user, auth_headers):
    uid = test_user["id"]
    await _profil_public(uid)
    t1, t2 = await _morceau(uid), await _morceau(uid)
    i1, i2 = await _image(uid), await _image(uid)
    try:
        assert (await client.post(f"/artist/me/tracks/{t1}/link", headers=auth_headers,
                                  json={"image_id": str(i1)})).status_code == 200
        # Même morceau, autre image → 409.
        assert (await client.post(f"/artist/me/tracks/{t1}/link", headers=auth_headers,
                                  json={"image_id": str(i2)})).status_code == 409
        # Même image, autre morceau → 409.
        assert (await client.post(f"/artist/me/tracks/{t2}/link", headers=auth_headers,
                                  json={"image_id": str(i1)})).status_code == 409
        # Filet en base : index unique partiel.
        with pytest.raises(IntegrityError):
            async with SessionLocal() as db:
                await db.execute(text("UPDATE prompts SET linked_track_id = :t WHERE id = :i"),
                                 {"t": t1, "i": i2})
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_seule_une_image_porte_un_morceau(test_user):
    uid = test_user["id"]
    rec = await _recette(uid)
    trk = await _morceau(uid)
    try:
        with pytest.raises(IntegrityError):
            async with SessionLocal() as db:
                await db.execute(text("UPDATE prompts SET linked_track_id = :t WHERE id = :i"),
                                 {"t": trk, "i": rec})
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_recette_ne_se_lie_pas_si_son_morceau_a_deja_une_image(client, test_user, auth_headers):
    uid = test_user["id"]
    trk = await _morceau(uid)
    i1, i2 = await _image(uid), await _image(uid)
    try:
        assert (await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                                  json={"image_id": str(i1)})).status_code == 200
        # Le créateur ajoute ensuite une recette à ce morceau…
        rec = await _recette(uid)
        async with SessionLocal() as db:
            await db.execute(text("UPDATE tracks SET prompt_id = :p WHERE id = :t"),
                             {"p": rec, "t": trk})
            await db.commit()
        # … et tente de lier la recette à une AUTRE image → refusé.
        r = await client.post(f"/artist/me/prompts/{i2}/link", headers=auth_headers,
                              json={"other_prompt_id": str(rec)})
        assert r.status_code == 409
    finally:
        await _cleanup(uid)


async def test_pas_de_liaison_avec_le_contenu_d_un_autre(client, test_user, auth_headers):
    uid = test_user["id"]
    from app.schemas.user import UserCreate
    from app.services.users import create_user
    from app.models.user import User

    async with SessionLocal() as db:
        autre = (await create_user(db, UserCreate(
            email=f"pytest-oe-{uuid.uuid4().hex[:8]}@smyleplay.example", password="12345678"))).id
    trk_autre = await _morceau(autre)
    img = await _image(uid)
    try:
        r = await client.post(f"/artist/me/tracks/{trk_autre}/link", headers=auth_headers,
                              json={"image_id": str(img)})
        assert r.status_code == 404
    finally:
        await _cleanup(uid)
        await _cleanup(autre)
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == autre))
            await db.commit()


async def test_candidats_et_deliaison(client, test_user, auth_headers):
    uid = test_user["id"]
    trk = await _morceau(uid, title="Son libre")
    img = await _image(uid)
    try:
        # L'image propose le morceau sans recette comme son liable.
        r = await client.get(f"/artist/me/prompts/{img}/linkable", headers=auth_headers)
        assert r.status_code == 200
        kinds = {(c["id"], c.get("kind")) for c in r.json()}
        assert (str(trk), "track") in kinds
        # Le morceau propose l'image.
        r = await client.get(f"/artist/me/tracks/{trk}/linkable", headers=auth_headers)
        assert str(img) in [c["id"] for c in r.json()]

        await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                          json={"image_id": str(img)})
        # Plus candidat une fois lié.
        r = await client.get(f"/artist/me/tracks/{trk}/linkable", headers=auth_headers)
        assert str(img) not in [c["id"] for c in r.json()]

        r = await client.delete(f"/artist/me/tracks/{trk}/link", headers=auth_headers)
        assert r.status_code == 204
        assert (await _get(Prompt, img)).linked_track_id is None
        r = await client.delete(f"/artist/me/tracks/{trk}/link", headers=auth_headers)
        assert r.status_code == 204                    # idempotent
    finally:
        await _cleanup(uid)


# ─── 2. Page publique + aperçu de partage ─────────────────────────────────────

async def test_page_a_partager_avec_apercu_social(client, test_user, auth_headers):
    uid = test_user["id"]
    await _profil_public(uid, name="Lumen")
    trk = await _morceau(uid, title="Aube électrique")
    img = await _image(uid)
    try:
        await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                          json={"image_id": str(img)})
        r = await client.get(f"/o/{img}")
        assert r.status_code == 200
        html = r.text
        assert 'property="og:title" content="Aube électrique — Lumen"' in html
        assert 'property="og:image"' in html and "previews/" in html
        assert f'property="og:url" content="http://test/o/{img}"' in html
        assert 'name="twitter:card" content="summary_large_image"' in html
        assert 'property="og:type" content="music.song"' in html
    finally:
        await _cleanup(uid)


async def test_page_introuvable_sans_fuite(client):
    r = await client.get(f"/o/{uuid.uuid4()}")
    assert r.status_code == 200                         # page brute (état « introuvable »)
    assert "og:title" not in r.text
    r = await client.get("/o/pas-un-uuid")
    assert r.status_code == 200 and "og:title" not in r.text


@pytest.mark.parametrize("cas", ["profil_prive", "brouillon", "retiree"])
async def test_oeuvre_non_publique_404(client, test_user, auth_headers, cas):
    uid = test_user["id"]
    await _profil_public(uid)
    trk = await _morceau(uid)
    img = await _image(uid, published=(cas != "brouillon"))
    try:
        await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                          json={"image_id": str(img)})
        if cas == "profil_prive":
            async with SessionLocal() as db:
                await db.execute(text("UPDATE users SET profile_public = FALSE WHERE id = :u"),
                                 {"u": uid})
                await db.commit()
        if cas == "retiree":
            async with SessionLocal() as db:
                await takedown_content(db, "image", str(img), "test")
                await db.commit()
        r = await client.get(f"/watt/oeuvres/{img}")
        assert r.status_code == 404
        assert "og:title" not in (await client.get(f"/o/{img}")).text
    finally:
        await _cleanup(uid)


async def test_listing_public_inclut_les_oeuvres_morceau(client, test_user, auth_headers):
    uid = test_user["id"]
    await _profil_public(uid)
    trk = await _morceau(uid, title="Son du listing")
    img = await _image(uid)
    try:
        await client.post(f"/artist/me/tracks/{trk}/link", headers=auth_headers,
                          json={"image_id": str(img)})
        r = await client.get("/oeuvres?limit=24")
        assert r.status_code == 200
        mine = [o for o in r.json()["oeuvres"] if o.get("oeuvreId") == str(img)]
        assert len(mine) == 1
        assert mine[0]["sound"]["trackId"] == str(trk)
        assert mine[0]["sound"]["priceCredits"] is None
    finally:
        await _cleanup(uid)
