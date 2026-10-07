"""Étape 3 — seuil d'abonnés pour vendre (FEATURE_SELL_GATE).

Couvre :
  - barème des abonnés requis selon la taille de la plateforme (5/15/30/50) ;
  - flag OFF : rien ne change (publication autorisée, aucun calcul) ;
  - flag ON : mise en vente bloquée (403, « Encore X abonnés… ») tant que le
    seuil d'abonnés RÉELS n'est pas atteint — prompt, voix, ADN de playlist ;
  - brouillon toujours autorisé (seule la MISE EN VENTE est filtrée) ;
  - abonnés non réels ignorés (email non vérifié, suspendu, compte technique) ;
  - exemptions : Pionnier, administrateur, compte officiel ;
  - droits acquis : contenu payant en vente AVANT la date d'activation ;
  - GET /me/droit-de-vendre renvoie le message pour le front.
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.user import User
from app.models.voice import Voice
from app.schemas.user import UserCreate
from app.services import droit_de_vendre as ddv
from app.services.users import create_user


# ─── helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def gate_on(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_SELL_GATE", True)
    monkeypatch.setattr(settings, "SELL_GATE_DEPUIS", "")
    monkeypatch.setattr(settings, "SELL_GATE_PALIERS",
                        [(0, 5), (500, 15), (2000, 30), (10000, 50)])

    async def _petite_plateforme(db):
        return 12  # 0–499 actifs → 5 abonnés requis

    monkeypatch.setattr(ddv, "actifs_en_cache", _petite_plateforme)


async def _user(*, verified=True, **flags) -> uuid.UUID:
    email = f"pytest-ddv-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    sets = ["email_verified = :v"] + [f"{k} = :{k}" for k in flags]
    async with SessionLocal() as db:
        await db.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id = :u"),
                         {"v": verified, "u": uid, **flags})
        await db.commit()
    return uid


async def _followers(followee, n, **flags) -> list[uuid.UUID]:
    ids = []
    for _ in range(n):
        f = await _user(**flags)
        async with SessionLocal() as db:
            await db.execute(text(
                "INSERT INTO user_follows (id, follower_id, followee_id) VALUES (:i, :f, :t)"),
                {"i": uuid.uuid4(), "f": f, "t": followee})
            await db.commit()
        ids.append(f)
    return ids


async def _draft_prompt(uid, *, published=False) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title=f"Recette {uuid.uuid4().hex[:6]}",
                   description="Tagline", prompt_text="X" * 100, price_credits=30,
                   is_published=published)
        db.add(p)
        await db.commit()
        return p.id


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(text("DELETE FROM user_follows WHERE follower_id = :u OR followee_id = :u"), {"u": uid})
            await db.execute(delete(Playlist).where(Playlist.owner_id == uid))
            await db.execute(delete(Voice).where(Voice.artist_id == uid))
            await db.execute(delete(Prompt).where(Prompt.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _statut(uid):
    async with SessionLocal() as db:
        u = await db.get(User, uid)
        return await ddv.statut_vente(db, u)


# ─── barème (pur) ─────────────────────────────────────────────────────────────

def test_abonnes_requis_selon_la_taille(monkeypatch):
    monkeypatch.setattr(settings, "SELL_GATE_PALIERS",
                        [(0, 5), (500, 15), (2000, 30), (10000, 50)])
    assert ddv.abonnes_requis(0) == 5
    assert ddv.abonnes_requis(499) == 5
    assert ddv.abonnes_requis(500) == 15
    assert ddv.abonnes_requis(1999) == 15
    assert ddv.abonnes_requis(2000) == 30
    assert ddv.abonnes_requis(9999) == 30
    assert ddv.abonnes_requis(10000) == 50
    assert ddv.abonnes_requis(250000) == 50


def test_valeurs_par_defaut_dans_config():
    from app.config import Settings
    s = Settings()
    assert s.FEATURE_SELL_GATE is False
    assert [tuple(p) for p in s.SELL_GATE_PALIERS] == [(0, 5), (500, 15), (2000, 30), (10000, 50)]


# ─── flag OFF : rien ne change ────────────────────────────────────────────────

async def test_flag_off_publication_autorisee(client, test_user, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_SELL_GATE", False)
    pid = await _draft_prompt(test_user["id"])
    try:
        r = await client.patch(f"/artist/me/prompts/{pid}", headers=auth_headers,
                               json={"is_published": True})
        assert r.status_code == 200, r.text
        st = await _statut(test_user["id"])
        assert st["peut_vendre"] is True and st["raison"] == "seuil_inactif"
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Prompt).where(Prompt.id == pid))
            await db.commit()


# ─── flag ON : blocage + message ──────────────────────────────────────────────

async def test_publier_un_prompt_bloque_sans_abonnes(client, test_user, auth_headers, gate_on):
    pid = await _draft_prompt(test_user["id"])
    try:
        r = await client.patch(f"/artist/me/prompts/{pid}", headers=auth_headers,
                               json={"is_published": True})
        assert r.status_code == 403, r.text
        assert r.json()["detail"].startswith("Encore 5 abonnés pour pouvoir vendre")
        async with SessionLocal() as db:
            assert (await db.get(Prompt, pid)).is_published is False
        # Le brouillon reste modifiable (pas de mise en vente) :
        r = await client.patch(f"/artist/me/prompts/{pid}", headers=auth_headers,
                               json={"title": "Nouveau titre"})
        assert r.status_code == 200, r.text
        # Le front peut afficher le message avant même d'essayer :
        r = await client.get("/me/droit-de-vendre", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["actif"] is True and d["peut_vendre"] is False
        assert d["manquants"] == 5 and d["requis"] == 5 and d["abonnes"] == 0
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Prompt).where(Prompt.id == pid))
            await db.commit()


async def test_seuil_atteint_avec_abonnes_reels(client, test_user, auth_headers, gate_on):
    uid = test_user["id"]
    reels = await _followers(uid, 4)
    faux = []
    faux += await _followers(uid, 1, verified=False)              # email non vérifié
    faux += await _followers(uid, 1, is_banned=True)              # suspendu
    faux += await _followers(uid, 1, is_admin=True)               # admin / test
    faux += await _followers(uid, 1, pioneer_excluded=True)       # exclu par l'admin
    pid = await _draft_prompt(uid)
    try:
        st = await _statut(uid)
        assert st["abonnes"] == 4 and st["peut_vendre"] is False
        assert st["message"].startswith("Encore 1 abonné pour pouvoir vendre")
        r = await client.patch(f"/artist/me/prompts/{pid}", headers=auth_headers,
                               json={"is_published": True})
        assert r.status_code == 403

        reels += await _followers(uid, 1)  # le 5e abonné réel
        r = await client.patch(f"/artist/me/prompts/{pid}", headers=auth_headers,
                               json={"is_published": True})
        assert r.status_code == 200, r.text
        assert (await _statut(uid))["raison"] == "seuil_atteint"
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Prompt).where(Prompt.id == pid))
            await db.commit()
        await _cleanup(*reels, *faux)


async def test_seuil_suit_la_taille_de_la_plateforme(test_user, gate_on, monkeypatch):
    uid = test_user["id"]
    followers = await _followers(uid, 5)
    try:
        assert (await _statut(uid))["peut_vendre"] is True

        async def _plateforme_moyenne(db):
            return 600  # 500–1999 actifs → 15 abonnés

        monkeypatch.setattr(ddv, "actifs_en_cache", _plateforme_moyenne)
        st = await _statut(uid)
        assert st["requis"] == 15 and st["manquants"] == 10 and st["peut_vendre"] is False
    finally:
        await _cleanup(*followers)


async def test_voix_et_adn_playlist_filtres(client, test_user, auth_headers, gate_on, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_VOIX", True)  # voix cachées au lancement
    uid = test_user["id"]
    async with SessionLocal() as db:
        v = Voice(artist_id=uid, name="Voix", style="calme", genres=[],
                  sample_url="https://example.invalid/s.mp3", license="personnel",
                  price_credits=100, is_published=False)
        db.add(v)
        await db.commit()
        vid = v.id
    r = await client.patch(f"/api/voices/{vid}", headers=auth_headers, json={"is_published": True})
    assert r.status_code == 403, r.text
    r = await client.post("/playlists", headers=auth_headers,
                          json={"title": "P", "visibility": "public",
                                "adn_for_sale": True, "adn_price": 20})
    assert r.status_code == 403, r.text
    # Playlist sans vente : autorisée.
    r = await client.post("/playlists", headers=auth_headers,
                          json={"title": "P", "visibility": "public"})
    assert r.status_code == 201, r.text
    pl = r.json()["id"]
    r = await client.patch(f"/playlists/{pl}", headers=auth_headers,
                           json={"adn_for_sale": True, "adn_price": 20})
    assert r.status_code == 403, r.text
    # Privée « à vendre » (pas encore en vente) puis passage en public → filtré.
    r = await client.post("/playlists", headers=auth_headers,
                          json={"title": "Priv", "visibility": "private",
                                "adn_for_sale": True, "adn_price": 20})
    assert r.status_code == 201, r.text
    r = await client.patch(f"/playlists/{r.json()['id']}", headers=auth_headers,
                           json={"visibility": "public"})
    assert r.status_code == 403, r.text
    async with SessionLocal() as db:
        await db.execute(delete(Voice).where(Voice.id == vid))
        await db.execute(delete(Playlist).where(Playlist.owner_id == uid))
        await db.commit()


# ─── exemptions et droits acquis ──────────────────────────────────────────────

async def test_exemptes_pionnier_admin_officiel(gate_on):
    from types import SimpleNamespace

    def compte(**f):
        base = dict(id=uuid.uuid4(), is_admin=False, is_official=False, is_pioneer=False)
        return SimpleNamespace(**{**base, **f})

    async with SessionLocal() as db:
        assert (await ddv.statut_vente(db, compte(is_pioneer=True)))["raison"] == "pionnier"
        assert (await ddv.statut_vente(db, compte(is_admin=True)))["raison"] == "exempte"
        assert (await ddv.statut_vente(db, compte(is_official=True)))["raison"] == "exempte"
        # Aucun des trois n'est bloqué par exiger_droit_de_vendre :
        for f in ({"is_pioneer": True}, {"is_admin": True}, {"is_official": True}):
            await ddv.exiger_droit_de_vendre(db, compte(**f))


async def test_droits_acquis_contenu_en_vente_avant_activation(gate_on, monkeypatch):
    ancien = await _user()
    nouveau = await _user()
    try:
        await _draft_prompt(ancien, published=True)   # déjà en vente
        await _draft_prompt(nouveau, published=False)  # simple brouillon
        st = await _statut(ancien)
        assert st["peut_vendre"] is True and st["raison"] == "droits_acquis"
        assert (await _statut(nouveau))["peut_vendre"] is False

        # Avec une date d'activation passée, un contenu créé APRÈS ne compte pas.
        monkeypatch.setattr(settings, "SELL_GATE_DEPUIS", "2020-01-01")
        assert (await _statut(ancien))["peut_vendre"] is False
        monkeypatch.setattr(settings, "SELL_GATE_DEPUIS", "2999-01-01")
        assert (await _statut(ancien))["raison"] == "droits_acquis"
    finally:
        await _cleanup(ancien, nouveau)


def test_passe_en_vente_playlist_album():
    from types import SimpleNamespace as N
    P = lambda **k: N(**{"adn_for_sale": None, "visibility": None, **k})  # noqa: E731
    assert ddv.passe_en_vente(N(adn_for_sale=False, visibility="public"), P(adn_for_sale=True))
    assert ddv.passe_en_vente(N(adn_for_sale=True, visibility="private"), P(visibility="public"))
    assert not ddv.passe_en_vente(N(adn_for_sale=True, visibility="public"), P(adn_for_sale=True))
    assert not ddv.passe_en_vente(N(adn_for_sale=False, visibility="private"), P(adn_for_sale=True))
    assert not ddv.passe_en_vente(N(adn_for_sale=False, visibility="private"), P(visibility="public"))
