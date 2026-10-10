"""Lot G — sécurité et argent (un test par changement de comportement).

1. Téléchargement : l'acheteur garde son fichier quand le créateur supprime
   l'œuvre ; un contenu retiré par la modération n'est plus servi à personne.
2. Retrait : les fichiers quittent le bucket public (opération durable),
   reviennent à la restauration ; clés ambiguës refusées par les proxys.
3. Prix attendu : 409 « le prix a changé » ; prix relu sous verrou.
4. Suppression de compte : mot de passe, verrou, conversations gardées,
   fichiers de voix et de playlist purgés, purge inscrite en base.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

from tests.test_lot_a_securite import _PWD, _cleanup, _login, _prompt, _track, _user
from tests.test_parcours_v1 import _bibliotheque, _oeuvre, _vente

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _sql(sql: str, **p):
    async with SessionLocal() as db:
        res = await db.execute(text(sql), p)
        try:
            rows = res.all()
        except Exception:  # noqa: BLE001
            rows = None
        await db.commit()
        return rows


async def _retirer(cible_type: str, cible_id, motif="Contrefaçon avérée"):
    from app.services.moderation import takedown_content

    async with SessionLocal() as db:
        out = await takedown_content(db, cible_type, str(cible_id), motif)
        await db.commit()
    assert out["ok"], out


# ═══ 1. Téléchargements ═════════════════════════════════════════════════════

async def test_acheteur_telecharge_apres_suppression_par_le_createur(client):
    a, acheteur, o, h, hb = await _vente(client)
    autre = await _user()
    try:
        r = await client.post("/artist/me/oeuvres/actions", headers=h, json={
            "track_ids": [str(o["track"])], "action": "supprimer"})
        assert r.status_code == 200, r.text
        # Avant : 404 (filtre « supprimé »). Maintenant : l'accès est vérifié,
        # puis le stockage est lu (503 = stockage absent en test).
        r = await client.get(f"/products/{o['recette']}/download", headers=hb)
        assert r.status_code == 503, r.text
        # Quelqu'un qui ne l'a pas acheté : introuvable.
        hx = await _login(client, autre["email"])
        r = await client.get(f"/products/{o['recette']}/download", headers=hx)
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(a["id"], acheteur["id"], autre["id"])


async def test_contenu_retire_refuse_a_tous(client):
    a, acheteur, o, h, hb = await _vente(client)
    try:
        await _retirer("track", o["track"])
        for hh in (hb, h):  # acheteur ET créateur
            r = await client.get(f"/products/{o['recette']}/download", headers=hh)
            assert r.status_code == 410, r.text
        await _retirer("image", o["image"])
        for hh in (hb, h):
            r = await client.get(f"/images/{o['image']}/download", headers=hh)
            assert r.status_code == 410, r.text
            r = await client.get(f"/images/{o['image']}/gallery/{uuid.uuid4()}/download", headers=hh)
            assert r.status_code == 410, r.text
        await _retirer("prompt", o["recette"])
        r = await client.get(f"/products/{o['recette']}/download", headers=hb)
        assert r.status_code == 410, r.text
        # Bibliothèque : l'achat reste listé, son contenu n'est plus servi.
        lib = await _bibliotheque(client, hb)
        rec, img = lib[str(o["recette"])], lib[str(o["image"])]
        assert rec["retire"] is True and "retiré par la modération" in rec["prompt_text"]
        assert rec["lyrics"] is None and rec["audio_url"] is None
        assert img["retire"] is True and img["gallery"] == []
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_email_au_createur_dit_que_les_acheteurs_perdent_l_acces(monkeypatch):
    from app.services import emails

    envoyes = []

    async def _faux(to, subject, html, *, reply_to=None):
        envoyes.append(html)
        return True

    monkeypatch.setattr(emails, "_send", _faux)
    await emails.send_decision_auteur("x@example.org", nature="retrait", target_type="track",
                                      titre="Son", motif="Contrefaçon")
    assert "gardent leur accès" not in envoyes[0]
    assert "y compris par les personnes qui l'ont déjà acheté" in envoyes[0]


# ═══ 2. Fichiers d'un contenu retiré ════════════════════════════════════════

async def test_retrait_programme_le_deplacement_puis_la_restauration(monkeypatch):
    from app.services.moderation import restaurer_contenu

    a = await _user()
    admin = await _user()
    try:
        o = await _oeuvre(a["id"])
        await _sql("UPDATE prompts SET preview_r2_key = :p WHERE id = :i",
                   p=f"images/previews/{uuid.uuid4().hex}.jpg", i=o["image"])
        await _retirer("track", o["track"])
        await _retirer("image", o["image"])
        rows = await _sql("SELECT cle, action, fait_le FROM fichiers_a_traiter WHERE cle LIKE :m "
                          "OR cle LIKE 'images/previews/%' AND motif = 'retrait' ORDER BY cree_le",
                          m=f"%{a['id']}%")
        cles = {r.cle for r in rows if r.action == "vers_prive" and r.fait_le is None}
        assert o["key"] in cles  # audio du son
        assert f"images/image/{a['id']}/orig.png" in cles  # original de l'image
        async with SessionLocal() as db:
            await restaurer_contenu(db, admin_id=admin["id"], cible_type="track",
                                    cible_id=str(o["track"]), motif="Erreur de modération")
            await db.commit()
        rows = await _sql("SELECT action, resultat, fait_le FROM fichiers_a_traiter WHERE cle = :k "
                          "ORDER BY cree_le", k=o["key"])
        # Le déplacement en attente est annulé, la remise en public programmée.
        assert rows[0].action == "vers_prive" and rows[0].resultat == "annule"
        assert rows[-1].action == "vers_public" and rows[-1].fait_le is None
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"], admin["id"])


class _R2Memoire:
    """Doublure du stockage : {bucket: set(clés)}."""

    def __init__(self, contenu):
        self.b = {k: set(v) for k, v in contenu.items()}

    async def existe(self, key, *, bucket):
        return key in self.b.setdefault(bucket, set())

    async def copier(self, key, *, source, destination):
        assert key in self.b[source]
        self.b.setdefault(destination, set()).add(key)

    async def supprimer(self, key, *, bucket):
        self.b.setdefault(bucket, set()).discard(key)


def _brancher(monkeypatch, r2mem, prive):
    from app.services import r2

    monkeypatch.setattr(r2, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "R2_PRIVATE_BUCKET", prive)
    monkeypatch.setattr(r2, "objet_existe", r2mem.existe)
    monkeypatch.setattr(r2, "copier_objet", r2mem.copier)
    monkeypatch.setattr(r2, "supprimer_objet", r2mem.supprimer)


async def test_deplacement_vers_le_prive_puis_retour(monkeypatch):
    from app.services.fichiers_a_traiter import programmer, traiter_en_attente
    from app.services.moderation import restaurer_contenu

    a = await _user()
    admin = await _user()
    try:
        o = await _oeuvre(a["id"])
        pub = settings.R2_BUCKET
        mem = _R2Memoire({pub: {o["key"]}, "prive-test": set()})
        # Sans bucket privé : l'opération reste en attente, rien ne bouge.
        _brancher(monkeypatch, mem, None)
        await _retirer("track", o["track"])
        res = await traiter_en_attente()
        assert res["en_attente"] >= 1 and o["key"] in mem.b[pub]
        # Bucket privé posé : la boucle quotidienne déplace le fichier.
        _brancher(monkeypatch, mem, "prive-test")
        await traiter_en_attente()
        assert o["key"] not in mem.b[pub] and o["key"] in mem.b["prive-test"]
        # Restauration : retour dans le public.
        async with SessionLocal() as db:
            await restaurer_contenu(db, admin_id=admin["id"], cible_type="track",
                                    cible_id=str(o["track"]), motif="Recours accepté")
            await db.commit()
        await traiter_en_attente()
        assert o["key"] in mem.b[pub] and o["key"] not in mem.b["prive-test"]
        # Un fichier encore utilisé par un contenu NON retiré reste public.
        async with SessionLocal() as db:
            await programmer(db, [o["key"]], "vers_prive", "retrait")
            await db.commit()
        await traiter_en_attente()
        assert o["key"] in mem.b[pub]
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"], admin["id"])


def test_cle_sure():
    from app.services.media_ownership import cle_sure

    for ok in ("tracks/u/son.mp3", "SUNSET LOVER/titre.mp3", "images/avatar/u/a.b.png"):
        assert cle_sure(ok), ok
    for ko in ("", "/tracks/u/s.mp3", "tracks//s.mp3", "tracks/../s.mp3", "./s.mp3",
               "tracks/./s.mp3", "tracks\\s.mp3", "tracks/s\x00.mp3"):
        assert not cle_sure(ko), ko


# Points encodés (%2E) : un client HTTP normal réécrit « .. » avant l'envoi,
# un attaquant non. Le serveur décode puis doit refuser.
@pytest.mark.parametrize("cle", [
    "tracks/x/%2E%2E/y/son.mp3", "tracks//x/son.mp3", "%2E/tracks/x/son.mp3",
    "tracks/x/%2E/son.mp3", "/tracks/x/son.mp3",
])
async def test_proxy_audio_refuse_les_cles_ambigues(client, cle):
    r = await client.get(f"/watt/stream/{cle}", follow_redirects=False)
    assert r.status_code == 404, (cle, r.status_code)


async def test_proxy_images_refuse_les_cles_ambigues(client, monkeypatch):
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-test.r2.dev")
    for cle in ("images/avatar/%2E%2E/originals/x.png", "images/avatar//x.png",
                "images/%2E/originals/x.png"):
        r = await client.get(f"/watt/images/{cle}", follow_redirects=False)
        assert r.status_code == 404, (cle, r.status_code)
    r = await client.get("/watt/images/images/avatar/u/x.png", follow_redirects=False)
    assert r.status_code == 302


async def test_apercu_d_une_image_retiree_n_est_plus_servi(client, monkeypatch):
    from app.routers import watt_compat

    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-test.r2.dev")
    a = await _user()
    try:
        o = await _oeuvre(a["id"])
        apercu = f"images/previews/{uuid.uuid4().hex}.jpg"
        await _sql("UPDATE prompts SET preview_r2_key = :p WHERE id = :i", p=apercu, i=o["image"])
        watt_compat.oublier_apercus_retires()
        assert (await client.get(f"/watt/images/{apercu}", follow_redirects=False)).status_code == 302
        await _retirer("image", o["image"])
        assert (await client.get(f"/watt/images/{apercu}", follow_redirects=False)).status_code == 404
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"])
        watt_compat.oublier_apercus_retires()


def test_doublon_watt_images_supprime():
    from app.routers.images import router as images
    from app.routers.watt_compat import router as compat

    assert not [r.path for r in images.routes if r.path.startswith("/watt/images")]
    assert [r.path for r in compat.routes].count("/watt/images/{key:path}") == 1


# ═══ 3. Prix attendu ════════════════════════════════════════════════════════

async def test_prix_attendu_409_puis_confirmation(client):
    a, b = await _user(), await _user(balance=500)
    try:
        pid = await _prompt(a["id"], price_credits=15)
        hb = await _login(client, b["email"])
        # Le créateur change son prix entre l'affichage (15) et le paiement.
        await _sql("UPDATE prompts SET price_credits = 45 WHERE id = :i", i=pid)
        r = await client.post(f"/unlocks/prompts/{pid}", headers=hb, json={"prix_attendu": 15})
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["code"] == "prix_change" and d["prix"] == 45
        assert d["message"] == "Le prix a changé : 45 Smyles"
        solde = (await _sql("SELECT credits_balance FROM users WHERE id = :u", u=b["id"]))[0][0]
        assert solde == 500  # rien n'a été débité
        r = await client.post(f"/unlocks/prompts/{pid}", headers=hb, json={"prix_attendu": 45})
        assert r.status_code == 201, r.text
        assert r.json()["paid"] == 45
    finally:
        await _cleanup(a["id"], b["id"])


async def test_prix_attendu_absent_reste_accepte(client):
    a, b = await _user(), await _user(balance=500)
    try:
        pid = await _prompt(a["id"], price_credits=20)
        hb = await _login(client, b["email"])
        r = await client.post(f"/unlocks/prompts/{pid}", headers=hb)
        assert r.status_code == 201, r.text
    finally:
        await _cleanup(a["id"], b["id"])


async def test_prix_lu_sous_verrou(monkeypatch):
    """Le prix lu AVANT les verrous est périmé : celui qui fait foi est relu
    sous verrou (le créateur l'a changé pendant l'achat)."""
    from app.services import unlocks

    a, b = await _user(), await _user(balance=500)
    try:
        pid = await _prompt(a["id"], price_credits=15)
        origine = unlocks._acquire_user_locks

        async def _pendant_l_achat(db, ids):
            await origine(db, ids)
            async with SessionLocal() as autre:  # changement concurrent, déjà validé
                await autre.execute(text("UPDATE prompts SET price_credits = 30 WHERE id = :i"),
                                    {"i": pid})
                await autre.commit()

        monkeypatch.setattr(unlocks, "_acquire_user_locks", _pendant_l_achat)
        async with SessionLocal() as db:
            res = await unlocks.unlock_prompt_atomic(db, buyer_id=b["id"], prompt_id=pid)
            await db.commit()
        assert res.paid == 30 and res.base_price == 30
    finally:
        await _cleanup(a["id"], b["id"])


async def test_oeuvre_entiere_prix_attendu(client):
    a, b = await _user(), await _user(balance=500)
    try:
        o = await _oeuvre(a["id"], prix_recette=20, prix_image=30)
        hb = await _login(client, b["email"])
        r = await client.post(f"/watt/oeuvres/{o['image']}/acheter", headers=hb,
                              json={"prix_attendu": 40})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["prix"] == 45  # (20 + 30) − 10 %
        r = await client.post(f"/watt/oeuvres/{o['image']}/acheter", headers=hb,
                              json={"prix_attendu": 45})
        assert r.status_code == 201, r.text
    finally:
        await _cleanup(a["id"], b["id"])


# ═══ 4. Suppression de compte ═══════════════════════════════════════════════

_SUPPR = {"confirmation": "SUPPRIMER", "renonce_smyles": True}


async def test_suppression_redemande_le_mot_de_passe(client):
    u = await _user()
    try:
        h = await _login(client, u["email"])
        r = await client.request("DELETE", "/users/me", headers=h, json=_SUPPR)
        assert r.status_code == 403, r.text
        r = await client.request("DELETE", "/users/me", headers=h,
                                 json={**_SUPPR, "mot_de_passe": "mauvais-mdp"})
        assert r.status_code == 403, r.text
        assert "Mot de passe incorrect" in r.json()["detail"]
        assert (await client.get("/users/me", headers=h)).status_code == 200
        r = await client.post("/users/me/delete", headers=h, json={**_SUPPR, "mot_de_passe": _PWD})
        assert r.status_code == 204, r.text
    finally:
        await _cleanup(u["id"])


async def test_suppression_purge_voix_et_videos_de_playlist(client, monkeypatch):
    from app.services import fichiers_a_traiter

    async def _rien(*a, **k):
        return {}

    monkeypatch.setattr(fichiers_a_traiter, "traiter_en_attente", _rien)
    u = await _user()
    uid = u["id"]
    voix = f"voices/ma-voix-{uuid.uuid4().hex[:8]}.wav"
    video = f"PLAYLISTS/{uid}/{uuid.uuid4().hex}.mp4"
    try:
        await _sql("INSERT INTO voices_for_sale (id, artist_id, name, style, sample_url, license, "
                   "price_credits) VALUES (gen_random_uuid(), :u, 'Ma voix', 'pop', :s, 'personnel', 500)",
                   u=uid, s=f"/watt/stream/{voix}")
        await _sql("INSERT INTO playlists (id, owner_id, title, visibility, cover_video_url) "
                   "VALUES (gen_random_uuid(), :u, 'Pl', 'private', :v)",
                   u=uid, v=f"/watt/playlist-video/{video}")
        h = await _login(client, u["email"])
        r = await client.request("DELETE", "/users/me", headers=h, json={**_SUPPR, "mot_de_passe": _PWD})
        assert r.status_code == 204, r.text
        cles = {x.cle for x in await _sql(
            "SELECT cle FROM fichiers_a_traiter WHERE motif = 'suppression_compte' AND cle IN (:a, :b)",
            a=voix, b=video)}
        assert cles == {voix, video}
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle IN (:a, :b)", a=voix, b=video)
        await _cleanup(uid)


async def test_suppression_attend_l_achat_en_cours():
    """Un achat en cours (ligne du vendeur verrouillée) : la suppression
    attend, puis voit l'œuvre achetée et la CONSERVE pour l'acheteur."""
    from app.models.user import User
    from app.services.account_deletion import delete_account

    vendeur, acheteur = await _user(), await _user()
    try:
        pid = await _prompt(vendeur["id"])
        achat = SessionLocal()
        await achat.execute(text("SELECT id FROM users WHERE id = :u FOR UPDATE"), {"u": vendeur["id"]})

        async def _supprimer():
            async with SessionLocal() as db:
                user = await db.get(User, vendeur["id"])
                await delete_account(db, user)

        tache = asyncio.create_task(_supprimer())
        await asyncio.sleep(0.5)
        assert not tache.done(), "la suppression aurait dû attendre l'achat"
        await achat.execute(text(
            "INSERT INTO unlocked_prompts (id, current_owner_id, prompt_id, original_artist_id) "
            "VALUES (gen_random_uuid(), :b, :p, :a)"), {"b": acheteur["id"], "p": pid, "a": vendeur["id"]})
        await achat.commit()
        await achat.close()
        await asyncio.wait_for(tache, timeout=10)
        n = (await _sql("SELECT count(*) FROM prompts WHERE id = :p", p=pid))[0][0]
        assert n == 1, "l'œuvre achetée doit être conservée"
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{vendeur['id']}%")
        await _sql("DELETE FROM unlocked_prompts WHERE prompt_id IN "
                   "(SELECT id FROM prompts WHERE artist_id = :u)", u=vendeur["id"])
        await _sql("DELETE FROM prompts WHERE artist_id = :u", u=vendeur["id"])
        await _cleanup(vendeur["id"], acheteur["id"])
