"""
Parcours V1 (décisions de Tom du 9 octobre 2026) — un test par point serveur.

  B1  un son se publie TOUJOURS avec son fichier audio (du compte, au format
      audio, présent sur le stockage quand il est configuré).
  B3  guide d'accueil : `onboarding_done_at` + POST /users/me/onboarding.
  B4  écran « Mes Œuvres » : liste, actions groupées (masquer, republier,
      prix 10–150, supprimer en douceur), modification unitaire, propriété
      vérifiée sur chaque route ; une Œuvre masquée disparaît des listes
      publiques mais reste accessible à son propriétaire et à ses acheteurs.
      RÈGLE DE PROTECTION DES ACHETEURS : prix, masquage, suppression ne
      retirent jamais l'accès de ceux qui ont payé (un test par cas).
  B5  pages obsolètes redirigées ; vidéos de playlist sur leur propre route ;
      adresse d'écoute signée pour l'acheteur d'un son supprimé.

Postgres requis (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.services import acces_audio

from tests.test_lot_a_securite import _cleanup, _get, _login, _prompt, _track, _user

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ─── Aides ─────────────────────────────────────────────────────────────────

async def _oeuvre(artist_id, *, prix_recette=15, prix_image=15):
    """Une Œuvre complète : son (avec audio) + recette + image liée au son."""
    rec = await _prompt(artist_id, price_credits=prix_recette)
    key = f"tracks/{artist_id}/son-{uuid.uuid4().hex[:8]}.wav"
    tid = await _track(artist_id, prompt_id=rec, r2_key=key,
                       audio_url=f"/watt/stream/{key}")
    async with SessionLocal() as db:
        img = Prompt(
            artist_id=artist_id, title=f"Image {uuid.uuid4().hex[:6]}",
            description="Pochette", prompt_text="une pochette", price_credits=prix_image,
            is_published=True, product_type="image", image_platform="midjourney",
            image_model_version="v7", preview_r2_key="images/previews/x.jpg",
            image_r2_key=f"images/image/{artist_id}/orig.png", linked_track_id=tid,
        )
        db.add(img)
        await db.commit()
        iid = img.id
    return {"track": tid, "recette": rec, "image": iid, "key": key}


async def _acheter(client, h, prompt_id):
    r = await client.post(f"/unlocks/prompts/{prompt_id}", headers=h)
    assert r.status_code in (200, 201), r.text


async def _bibliotheque(client, h) -> dict:
    r = await client.get("/me/library/prompts", params={"per_page": 100}, headers=h)
    assert r.status_code == 200, r.text
    return {i["prompt_id"]: i for i in r.json()["items"]}


async def _recents(client) -> set:
    r = await client.get("/watt/tracks-recent", params={"limit": 100})
    assert r.status_code == 200
    return {t["trackUuid"] for t in r.json()["tracks"]}


async def _action(client, h, ids, action, **kw):
    return await client.post("/artist/me/oeuvres/actions", headers=h, json={
        "track_ids": [str(i) for i in ids], "action": action, **kw})


# ═══ B1 — pas de son sans audio ═════════════════════════════════════════════

async def test_b1_son_refuse_sans_audio_valide(client):
    a, b = await _user(), await _user()
    try:
        h = await _login(client, a["email"])
        base = {"title": "Son", "full_prompt": "deep house"}
        refus = (
            {},                                                         # aucun fichier
            {"audio_url": "https://cdn.exemple.org/son.mp3"},          # externe
            {"r2_key": f"tracks/{b['id']}/son-0123abcd.wav"},          # d'un autre compte
            {"r2_key": f"tracks/{a['id']}/image-0123abcd.png"},        # pas un format audio
            {"r2_key": f"tracks/{a['id']}/a-0123abcd.wav",             # clé ≠ URL
             "audio_url": f"/watt/stream/tracks/{a['id']}/b-0123abcd.wav"},
        )
        for extra in refus:
            r = await client.post("/tracks/", json={**base, **extra}, headers=h)
            assert r.status_code == 422, (extra, r.text)
        async with SessionLocal() as db:
            n = (await db.execute(select(Track.id).where(Track.artist_id == a["id"]))).all()
        assert n == []
        r = await client.post("/tracks/", headers=h, json={
            **base, "r2_key": f"tracks/{a['id']}/son-0123abcd.mp3"})
        assert r.status_code == 201, r.text
    finally:
        await _cleanup(a["id"], b["id"])


async def test_b1_audio_absent_du_stockage_refuse(client, monkeypatch):
    import app.services.r2 as r2

    class _R2:
        def head_object(self, **kw):
            raise KeyError(kw["Key"])

    a = await _user()
    try:
        h = await _login(client, a["email"])
        monkeypatch.setattr(r2, "is_configured", lambda: True)
        monkeypatch.setattr(r2, "get_r2_client", lambda: _R2())
        r = await client.post("/tracks/", headers=h, json={
            "title": "Son", "full_prompt": "x", "r2_key": f"tracks/{a['id']}/s-0123abcd.wav"})
        assert r.status_code == 422 and "introuvable" in r.json()["detail"]
    finally:
        await _cleanup(a["id"])


async def test_b1_limite_audio_50_mo():
    assert settings.UPLOAD_MAX_AUDIO_MB == 50


# ═══ B3 — guide d'accueil ═══════════════════════════════════════════════════

async def test_b3_guide_vu_une_fois(client):
    a = await _user()
    try:
        h = await _login(client, a["email"])
        r = await client.get("/users/me", headers=h)
        assert r.json()["onboarding_done_at"] is None          # nouveau compte : à montrer
        r = await client.post("/users/me/onboarding", headers=h)
        assert r.status_code == 200
        premiere = r.json()["onboarding_done_at"]
        assert premiere
        r = await client.post("/users/me/onboarding", headers=h)  # rouvert depuis le menu
        assert r.json()["onboarding_done_at"] == premiere
        assert (await client.get("/users/me", headers=h)).json()["onboarding_done_at"]
        assert (await client.post("/users/me/onboarding")).status_code == 401
    finally:
        await _cleanup(a["id"])


# ═══ B4 — Mes Œuvres ════════════════════════════════════════════════════════

async def test_b4_liste_de_mes_oeuvres(client):
    a, b = await _user(), await _user(balance=500)
    o = await _oeuvre(a["id"], prix_recette=15, prix_image=30)
    autre = await _oeuvre(b["id"])
    try:
        hb = await _login(client, b["email"])
        await _acheter(client, hb, o["recette"])
        h = await _login(client, a["email"])
        r = await client.get("/artist/me/oeuvres", headers=h)
        assert r.status_code == 200
        items = r.json()["items"]
        assert [i["trackId"] for i in items] == [str(o["track"])]   # jamais celles d'autrui
        it = items[0]
        assert it["status"] == "publiee" and it["sales"] == 1
        assert it["recipe"]["priceCredits"] == 15 and it["image"]["priceCredits"] == 30
        assert it["streamUrl"] and it["oeuvreUrl"] == f"/o/{o['image']}"
        assert (await client.get("/artist/me/oeuvres")).status_code == 401
        assert str(autre["track"]) not in {i["trackId"] for i in items}
    finally:
        await _cleanup(a["id"], b["id"])


async def test_b4_proprietaire_verifie_sur_chaque_route(client):
    a, b = await _user(), await _user()
    o = await _oeuvre(b["id"])
    try:
        h = await _login(client, a["email"])
        for action, kw in (("masquer", {}), ("republier", {}), ("supprimer", {}),
                           ("prix", {"prix": 20})):
            r = await _action(client, h, [o["track"]], action, **kw)
            assert r.status_code == 200, r.text
            assert r.json()["faits"] == [] and r.json()["introuvables"] == 1
        r = await client.patch(f"/artist/me/oeuvres/{o['track']}", headers=h,
                               json={"title": "Volé"})
        assert r.status_code == 404
        t = await _get(Track, o["track"])
        assert t.hidden_at is None and not t.is_deleted and t.title != "Volé"
        assert (await _get(Prompt, o["recette"])).price_credits == 15
    finally:
        await _cleanup(a["id"], b["id"])


async def test_b4_prix_borne_10_150(client):
    a = await _user()
    o = await _oeuvre(a["id"])
    try:
        h = await _login(client, a["email"])
        for prix in (9, 151, None):
            r = await _action(client, h, [o["track"]], "prix", prix=prix)
            assert r.status_code == 422, (prix, r.text)
        r = await _action(client, h, [o["track"]], "prix", prix=45, cible="recette")
        assert r.status_code == 200 and r.json()["faits"] == [str(o["track"])]
        assert (await _get(Prompt, o["recette"])).price_credits == 45
        assert (await _get(Prompt, o["image"])).price_credits == 15
        r = await _action(client, h, [o["track"]], "prix", prix=150)
        assert (await _get(Prompt, o["image"])).price_credits == 150
    finally:
        await _cleanup(a["id"])


async def test_b4_masquer_retire_des_listes_publiques(client):
    a, c = await _user(), await _user()
    o = await _oeuvre(a["id"])
    try:
        h = await _login(client, a["email"])
        assert str(o["track"]) in await _recents(client)
        assert (await client.get(f"/watt/oeuvres/{o['image']}")).status_code == 200

        r = await _action(client, h, [o["track"]], "masquer")
        assert r.json()["faits"] == [str(o["track"])]
        assert (await _get(Track, o["track"])).hidden_at is not None
        assert not (await _get(Prompt, o["recette"])).is_published
        assert not (await _get(Prompt, o["image"])).is_published
        assert str(o["track"]) not in await _recents(client)
        r = await client.get(f"/watt/artists/{a['slug']}")
        if r.status_code == 200:
            assert str(o["track"]) not in r.text
        r = await client.get("/watt/search/tracks", params={"q": "Son"})
        assert str(o["track"]) not in r.text
        # /o/ : invisible pour un visiteur et un inconnu, visible pour le créateur.
        assert (await client.get(f"/watt/oeuvres/{o['image']}")).status_code == 404
        hc = await _login(client, c["email"])
        assert (await client.get(f"/watt/oeuvres/{o['image']}", headers=hc)).status_code == 404
        r = await client.get(f"/watt/oeuvres/{o['image']}", headers=h)
        assert r.status_code == 200 and r.json()["masquee"] is True
        assert (await client.get("/artist/me/oeuvres", headers=h)).json()["items"][0]["status"] == "masquee"

        r = await _action(client, h, [o["track"]], "republier")
        assert r.json()["faits"] == [str(o["track"])]
        assert str(o["track"]) in await _recents(client)
        assert (await _get(Prompt, o["image"])).is_published
    finally:
        await _cleanup(a["id"], c["id"])


async def test_b4_republier_soumis_au_droit_de_vendre(client, monkeypatch):
    a = await _user()
    o = await _oeuvre(a["id"])
    try:
        h = await _login(client, a["email"])
        await _action(client, h, [o["track"]], "masquer")
        monkeypatch.setattr(settings, "FEATURE_SELL_GATE", True)
        async with SessionLocal() as db:   # pas de droits acquis : rien en vente
            await db.execute(text("UPDATE prompts SET created_at = now() WHERE artist_id = :u"),
                             {"u": a["id"]})
            await db.commit()
        monkeypatch.setattr(settings, "SELL_GATE_DEPUIS", "2000-01-01")
        r = await _action(client, h, [o["track"]], "republier")
        assert r.status_code == 403, r.text
        assert (await _get(Track, o["track"])).hidden_at is not None
    finally:
        await _cleanup(a["id"])


async def test_b4_supprimer_en_douceur(client):
    a = await _user()
    o = await _oeuvre(a["id"])
    try:
        h = await _login(client, a["email"])
        r = await _action(client, h, [o["track"]], "supprimer")
        assert r.json()["faits"] == [str(o["track"])]
        t, rec, img = (await _get(Track, o["track"]), await _get(Prompt, o["recette"]),
                       await _get(Prompt, o["image"]))
        assert t is not None and t.is_deleted                       # rien d'effacé
        assert rec.is_deleted and img.is_deleted
        assert str(o["track"]) not in await _recents(client)
        assert (await client.get("/artist/me/oeuvres", headers=h)).json()["items"] == []
    finally:
        await _cleanup(a["id"])


async def test_b4_modifier_une_oeuvre(client):
    a, b = await _user(), await _user()
    o = await _oeuvre(a["id"])
    try:
        h = await _login(client, a["email"])
        r = await client.patch(f"/artist/me/oeuvres/{o['track']}", headers=h, json={
            "title": "Nouveau titre", "description": "Une description",
            "cover_url": f"/watt/images/images/track-cover/{a['id']}/c.png",
            "recipe_price": 30, "image_price": 45,
        })
        assert r.status_code == 200, r.text
        t, rec, img = (await _get(Track, o["track"]), await _get(Prompt, o["recette"]),
                       await _get(Prompt, o["image"]))
        assert t.title == rec.title == img.title == "Nouveau titre"
        assert rec.description == "Une description"
        assert (rec.price_credits, img.price_credits) == (30, 45)
        for corps in ({"cover_url": f"/watt/images/images/track-cover/{b['id']}/c.png"},
                      {"recipe_price": 151}, {"image_price": 9}, {"title": "abc"}):
            r = await client.patch(f"/artist/me/oeuvres/{o['track']}", headers=h, json=corps)
            assert r.status_code == 422, (corps, r.text)
    finally:
        await _cleanup(a["id"], b["id"])


# ═══ B4 — RÈGLE DE PROTECTION DES ACHETEURS (un test par cas) ═══════════════

async def _vente(client):
    a, acheteur = await _user(), await _user(balance=500)
    o = await _oeuvre(a["id"])
    hb = await _login(client, acheteur["email"])
    await _acheter(client, hb, o["recette"])
    await _acheter(client, hb, o["image"])
    h = await _login(client, a["email"])
    return a, acheteur, o, h, hb


async def _acces_intact(client, hb, o, acheteur_id):
    lib = await _bibliotheque(client, hb)
    assert str(o["recette"]) in lib and str(o["image"]) in lib
    assert lib[str(o["recette"])]["prompt_text"] == "X" * 100
    async with SessionLocal() as db:
        n = (await db.execute(select(UnlockedPrompt.id).where(
            UnlockedPrompt.current_owner_id == acheteur_id))).all()
    assert len(n) == 2
    # Téléchargement de l'original : jamais « non acheté » (403) ni introuvable.
    r = await client.get(f"/images/{o['image']}/download", headers=hb)
    assert r.status_code not in (403, 404), r.text
    return lib


async def test_acheteurs_changement_de_prix(client):
    a, acheteur, o, h, hb = await _vente(client)
    try:
        r = await _action(client, h, [o["track"]], "prix", prix=150)
        assert r.json()["faits"] == [str(o["track"])]
        await _acces_intact(client, hb, o, acheteur["id"])
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_acheteurs_masquage(client):
    a, acheteur, o, h, hb = await _vente(client)
    try:
        await _action(client, h, [o["track"]], "masquer")
        lib = await _acces_intact(client, hb, o, acheteur["id"])
        assert lib[str(o["recette"])]["audio_url"].startswith(f"/watt/stream/{o['key']}")
        # L'acheteur voit encore l'Œuvre masquée sur /o/.
        r = await client.get(f"/watt/oeuvres/{o['image']}", headers=hb)
        assert r.status_code == 200 and r.json()["masquee"] is True
        # Le son masqué reste écoutable (proxy : pas de 404 de retrait).
        r = await client.get(f"/watt/stream/{o['key']}")
        assert r.status_code != 404
        # Personne d'autre ne peut plus l'acheter.
        c = await _user(balance=500)
        hc = await _login(client, c["email"])
        r = await client.post(f"/unlocks/prompts/{o['recette']}", headers=hc)
        assert r.status_code >= 400
        await _cleanup(c["id"])
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_acheteurs_suppression(client):
    a, acheteur, o, h, hb = await _vente(client)
    try:
        await _action(client, h, [o["track"]], "supprimer")
        lib = await _acces_intact(client, hb, o, acheteur["id"])
        url = lib[str(o["recette"])]["audio_url"]
        assert url and url.startswith(f"/watt/stream/{o['key']}?acces=")
        # Sans signature : le son supprimé ne s'écoute plus (Lot A, E3).
        assert (await client.get(f"/watt/stream/{o['key']}")).status_code == 404
        # Avec l'adresse de la bibliothèque : servi (503 = stockage absent en test).
        assert (await client.get(url)).status_code != 404
        # Retiré par la MODÉRATION : coupé pour tout le monde, même signé.
        async with SessionLocal() as db:
            await db.execute(text("UPDATE tracks SET taken_down_at = now() WHERE id = :t"),
                             {"t": o["track"]})
            await db.commit()
        assert (await client.get(url)).status_code == 404
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_signature_audio():
    cle = "tracks/x/son-0123abcd.wav"
    j = acces_audio.signer(cle, maintenant=1000)
    assert acces_audio.verifier(cle, j, maintenant=1000)
    assert not acces_audio.verifier("tracks/x/autre.wav", j, maintenant=1000)
    assert not acces_audio.verifier(cle, j, maintenant=1000 + acces_audio.DUREE_SECONDES + 1)
    assert not acces_audio.verifier(cle, "123.abc", maintenant=0)
    assert not acces_audio.verifier(cle, None)
    assert acces_audio.url_acheteur("https://pub.r2.dev/a.wav") == "https://pub.r2.dev/a.wav"
    assert acces_audio.url_acheteur(None) is None


# ═══ B5 — pages obsolètes, vidéos de playlist ═══════════════════════════════

async def test_b5_pages_obsoletes_redirigees(client, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_EUROS", False)
    monkeypatch.setattr(settings, "SHOW_PALIERS", False)
    assert not settings.launch_flags_dict()["euros"]
    for path in ("/tarifs.html", "/offres.html", "/oeuvre.html"):
        r = await client.get(path, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == "/", path


async def test_b5_video_de_playlist_route_dediee(client, monkeypatch):
    uid = uuid.uuid4()
    ok = f"PLAYLISTS/{uid}/{uuid.uuid4().hex}.mp4"
    for mauvaise in ("PLAYLISTS/../tracks/x.wav", f"PLAYLISTS/{uid}/x.mp4",
                     f"tracks/{uid}/{uuid.uuid4().hex}.mp4", f"PLAYLISTS/{uid}/{uuid.uuid4().hex}.png"):
        assert (await client.get(f"/watt/playlist-video/{mauvaise}")).status_code == 404, mauvaise
    monkeypatch.setattr(type(settings), "effective_r2_public_base_url",
                        property(lambda self: "https://pub.example.r2.dev"))
    r = await client.get(f"/watt/playlist-video/{ok}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith(ok)
