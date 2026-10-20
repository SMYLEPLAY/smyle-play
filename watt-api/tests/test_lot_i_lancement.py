"""Lot I — corrections de l'audit du 15/10 avant le lancement Pionnier.

  - codes Pionnier : le rang en direct exige un code d'invitation ;
  - une même boîte mail = un seul compte (alias Gmail) ;
  - parrainage versé seulement aux emails vérifiés ;
  - connexion refusée « email non vérifié » avec un code exploitable ;
  - motif de suspension donné à la connexion ;
  - plus aucun nom ni slug public tiré de l'email ;
  - confirmation des droits commerciaux (IA) ;
  - pochette d'un son retiré déplacée si elle ne sert à rien d'autre ;
  - protection audio : essais plafonnés.
"""
import uuid

import pytest
from sqlalchemy import delete, text

from app.config import settings
from app.core.emails_canoniques import email_canonique
from app.core.slug import derive_artist_slug
from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import pioneer_codes
from app.services.pioneer import award_pioneer
from app.services.users import create_user


async def _user(**flags) -> uuid.UUID:
    email = f"pytest-loti-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    if flags:
        sets = ", ".join(f"{k} = :{k}" for k in flags)
        async with SessionLocal() as db:
            await db.execute(text(f"UPDATE users SET {sets} WHERE id = :u"), {**flags, "u": uid})
            await db.commit()
    return uid


async def _oeuvre(uid) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title=f"P {uuid.uuid4().hex[:8]}", description="T",
                   prompt_text="X" * 100, price_credits=10, is_published=True)
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _codes(n=1) -> list[str]:
    async with SessionLocal() as db:
        codes = await pioneer_codes.generer(db, n, note="pytest", admin_id=None)
        await db.commit()
    return codes


async def _nettoyer(*uids, codes=()):
    async with SessionLocal() as db:
        if codes:
            await db.execute(text("DELETE FROM pioneer_codes WHERE code = ANY(:c)"), {"c": list(codes)})
        for uid in uids:
            await db.execute(text("DELETE FROM pioneer_codes WHERE used_by = :u"), {"u": uid})
            await db.execute(delete(Prompt).where(Prompt.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


# ── Email canonique ─────────────────────────────────────────────────────────

def test_email_canonique():
    assert email_canonique("T.Om+watt@Gmail.com") == "tom@gmail.com"
    assert email_canonique("tom@googlemail.com") == "tom@gmail.com"
    assert email_canonique("a.b+c@orange.fr") == "a.b@orange.fr"
    assert email_canonique("pas-un-email") is None


async def test_inscription_refuse_un_alias_de_la_meme_boite(client):
    base = f"lotialias{uuid.uuid4().hex[:8]}"
    corps = {"password": "12345678", "accept_terms": True, "age_confirmed": True}
    r = await client.post("/auth/register", json={"email": f"{base}@gmail.com", **corps})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    try:
        for alias in (f"{base}+2@gmail.com", f"{base[:3]}.{base[3:]}@gmail.com",
                      f"{base}@googlemail.com"):
            r2 = await client.post("/auth/register", json={"email": alias, **corps})
            assert r2.status_code == 409, alias
    finally:
        await _nettoyer(uuid.UUID(uid))


# ── Codes Pionnier ──────────────────────────────────────────────────────────

def test_normaliser_code():
    assert pioneer_codes.normaliser(" watt 7k3-qx9 ") == "WATT-7K3QX9"
    assert pioneer_codes.normaliser("7K3QX9") == "WATT-7K3QX9"
    assert pioneer_codes.normaliser("") == ""


async def test_rang_en_direct_exige_un_code(monkeypatch):
    monkeypatch.setattr(settings, "PIONEER_CODE_REQUIRED", True)
    sans_code, avec_code = await _user(), await _user()
    await _oeuvre(sans_code)
    await _oeuvre(avec_code)
    (code,) = await _codes(1)
    try:
        async with SessionLocal() as db:
            assert await award_pioneer(db, sans_code, live=True) is None
            await pioneer_codes.utiliser(db, avec_code, code)
            rang = await award_pioneer(db, avec_code, live=True)
            await db.commit()
        assert rang is not None
        # Le rattrapage admin (live=False) n'exige pas de code.
        async with SessionLocal() as db:
            assert await award_pioneer(db, sans_code, live=False) is not None
            await db.rollback()
    finally:
        await _nettoyer(sans_code, avec_code, codes=[code])


async def test_code_usage_unique_et_un_seul_par_compte():
    a, b = await _user(), await _user()
    c1, c2 = await _codes(2)
    try:
        async with SessionLocal() as db:
            await pioneer_codes.utiliser(db, a, c1.lower())
            await db.commit()
        async with SessionLocal() as db:
            with pytest.raises(pioneer_codes.CodeInvalide):
                await pioneer_codes.utiliser(db, b, c1)
            with pytest.raises(pioneer_codes.CodeDejaUtilise):
                await pioneer_codes.utiliser(db, a, c2)
            with pytest.raises(pioneer_codes.CodeInvalide):
                await pioneer_codes.utiliser(db, b, "WATT-ZZZZZZ")
    finally:
        await _nettoyer(a, b, codes=[c1, c2])


async def test_inscription_avec_code(client):
    (code,) = await _codes(1)
    corps = {"password": "12345678", "accept_terms": True, "age_confirmed": True}
    r = await client.post("/auth/register", json={
        "email": f"pytest-loti-{uuid.uuid4().hex[:10]}@smyleplay.example",
        "pioneer_code": "WATT-ZZZZZZ", **corps})
    assert r.status_code == 400
    assert "Code Pionnier" in r.json()["detail"]
    r = await client.post("/auth/register", json={
        "email": f"pytest-loti-{uuid.uuid4().hex[:10]}@smyleplay.example",
        "pioneer_code": code.replace("-", " ").lower(), **corps})
    assert r.status_code == 201, r.text
    uid = uuid.UUID(r.json()["id"])
    try:
        async with SessionLocal() as db:
            assert await pioneer_codes.a_un_code(db, uid)
    finally:
        await _nettoyer(uid, codes=[code])


async def test_endpoint_code_puis_rang(client, test_user, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    monkeypatch.setattr(settings, "PIONEER_CODE_REQUIRED", True)
    await _oeuvre(test_user["id"])
    (code,) = await _codes(1)
    try:
        r = await client.post("/pioneer/code", headers=auth_headers, json={"code": "WATT-ZZZZZZ"})
        assert r.status_code == 400
        r = await client.post("/pioneer/code", headers=auth_headers, json={"code": code})
        assert r.status_code == 200, r.text
        assert r.json()["rang"] is not None
        r = await client.post("/pioneer/code", headers=auth_headers, json={"code": code})
        assert r.status_code == 409
        r = await client.get("/pioneer/moi", headers=auth_headers)
        assert r.json()["code_utilise"] is True
    finally:
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET pioneer_rank = NULL, is_pioneer = FALSE "
                                  "WHERE id = :u"), {"u": test_user["id"]})
            await db.execute(text("DELETE FROM pioneer_codes WHERE code = :c"), {"c": code})
            await db.execute(delete(Prompt).where(Prompt.artist_id == test_user["id"]))
            await db.commit()


async def test_admin_genere_et_liste_les_codes(client, test_user, auth_headers):
    r = await client.post("/admin/pioneer/codes", headers=auth_headers, json={"n": 2})
    assert r.status_code == 403
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :u"), {"u": test_user["id"]})
        await db.commit()
    codes = []
    try:
        r = await client.post("/admin/pioneer/codes", headers=auth_headers,
                              json={"n": 3, "note": "DM TikTok"})
        assert r.status_code == 200, r.text
        codes = r.json()["codes"]
        assert len(codes) == 3 and all(c.startswith("WATT-") for c in codes)
        r = await client.get("/admin/pioneer/codes", headers=auth_headers)
        vus = {c["code"]: c for c in r.json()["codes"]}
        assert all(vus[c]["note"] == "DM TikTok" and vus[c]["utilise_le"] is None for c in codes)
    finally:
        async with SessionLocal() as db:
            await db.execute(text("DELETE FROM pioneer_codes WHERE code = ANY(:c)"), {"c": codes})
            await db.execute(text("UPDATE users SET is_admin = FALSE WHERE id = :u"), {"u": test_user["id"]})
            await db.commit()


# ── Parrainage : email vérifié ──────────────────────────────────────────────

async def test_parrainage_attend_l_email_verifie():
    from app.models.referral import Referral, ReferralStatus
    from app.services.referrals import maybe_reward_referral

    parrain, filleul = await _user(), await _user()
    async with SessionLocal() as db:
        db.add(Referral(referrer_id=parrain, referred_id=filleul,
                        status=ReferralStatus.PENDING, reward_credits=20))
        await db.commit()
    try:
        async with SessionLocal() as db:
            assert await maybe_reward_referral(db, filleul) is False
            await db.commit()
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET email_verified = TRUE WHERE id = :u"), {"u": filleul})
            await db.commit()
        async with SessionLocal() as db:
            assert await maybe_reward_referral(db, filleul) is True
            await db.commit()
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Referral).where(Referral.referred_id == filleul))
            await db.commit()


# ── Connexion ───────────────────────────────────────────────────────────────

async def test_connexion_email_non_verifie_donne_un_code(client, test_user, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFIED", True)
    r = await client.post("/auth/login", json={"email": test_user["email"],
                                               "password": test_user["password"]})
    assert r.status_code == 403
    assert r.json()["code"] == "email_non_verifie"


async def test_connexion_compte_suspendu_donne_le_motif(client, test_user):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET is_banned = TRUE, banned_at = now(), "
                              "ban_reason = 'Spam répété' WHERE id = :u"), {"u": test_user["id"]})
        await db.commit()
    try:
        r = await client.post("/auth/login", json={"email": test_user["email"],
                                                   "password": test_user["password"]})
        assert r.status_code == 403
        corps = r.json()
        assert corps["code"] == "compte_suspendu"
        assert corps["motif"] == "Spam répété"
        assert corps["recours"]
    finally:
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET is_banned = FALSE, banned_at = NULL, "
                                  "ban_reason = NULL WHERE id = :u"), {"u": test_user["id"]})
            await db.commit()


# ── Données personnelles : rien de public tiré de l'email ───────────────────

def test_slug_sans_nom_ne_vient_plus_de_l_email():
    u = User(id=uuid.uuid4(), email="jean.dupont@exemple.fr", artist_name=None)
    s = derive_artist_slug(u)
    assert s.startswith("membre-") and "jean" not in s
    u2 = User(id=uuid.uuid4(), email="x@exemple.fr", artist_name="DJ Soleil")
    assert derive_artist_slug(u2) == "dj-soleil"


async def test_abonnes_publics_sans_email_ni_profil_prive(client):
    from app.models.user_follow import UserFollow
    from app.routers.watt_compat import _derive_artist_slug

    artiste = await _user(artist_name="Artiste LotI " + uuid.uuid4().hex[:6], profile_public=True)
    fan_public = await _user(profile_public=True)
    fan_prive = await _user(profile_public=False)
    try:
        async with SessionLocal() as db:
            db.add(UserFollow(follower_id=fan_public, followee_id=artiste))
            db.add(UserFollow(follower_id=fan_prive, followee_id=artiste))
            await db.commit()
            a = await db.get(User, artiste)
            slug = _derive_artist_slug(a)
            emails = [(await db.get(User, x)).email.split("@")[0] for x in (fan_public, fan_prive)]
        r = await client.get(f"/watt/artists/{slug}")
        assert r.status_code == 200, r.text
        texte = r.text
        for local in emails:
            assert local not in texte
        ids = [f.get("id") for f in r.json().get("followersSample", [])]
        assert str(fan_prive) not in ids
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(UserFollow).where(UserFollow.followee_id == artiste))
            await db.commit()
        await _nettoyer(artiste, fan_public, fan_prive)


# ── Droits commerciaux IA ───────────────────────────────────────────────────

async def test_droits_ia(client, test_user, auth_headers):
    r = await client.get("/users/me/droits-ia", headers=auth_headers)
    assert r.json() == {"confirme": False, "le": None}
    r = await client.post("/users/me/droits-ia", headers=auth_headers, json={"confirme": False})
    assert r.status_code == 400
    r = await client.post("/users/me/droits-ia", headers=auth_headers, json={"confirme": True})
    assert r.status_code == 200 and r.json()["confirme"] is True
    premiere = r.json()["le"]
    r = await client.post("/users/me/droits-ia", headers=auth_headers, json={"confirme": True})
    assert r.json()["le"] == premiere  # la première date est conservée


async def test_droits_ia_confirmation_ancienne_redemandee(client, test_user, auth_headers):
    """Une confirmation donnée avant la règle « ce qui est en vente est
    réutilisable » ne compte plus : la question est reposée."""
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET ia_rights_confirmed_at = "
                              "'2026-10-16T10:00:00+00' WHERE id = :u"),
                         {"u": test_user["id"]})
        await db.commit()
    r = await client.get("/users/me/droits-ia", headers=auth_headers)
    assert r.json() == {"confirme": False, "le": None}
    r = await client.post("/users/me/droits-ia", headers=auth_headers, json={"confirme": True})
    assert r.json()["confirme"] is True
    assert r.json()["le"] >= "2026-10-20"
    r = await client.get("/users/me/droits-ia", headers=auth_headers)
    assert r.json()["confirme"] is True


# ── Retrait : pochette ──────────────────────────────────────────────────────

async def test_retrait_inclut_la_pochette_et_l_execution_garde_les_partagees():
    from app.models.track import Track
    from app.services.fichiers_a_traiter import cles_du_contenu, utilise_hors_retrait

    uid = await _user()
    propre = f"tracks/{uid}/cover-{uuid.uuid4().hex}.png"
    partagee = f"tracks/{uid}/cover-{uuid.uuid4().hex}.png"
    ids = []
    try:
        async with SessionLocal() as db:
            for cover in (propre, partagee, partagee):
                t = Track(artist_id=uid, title="T",
                          r2_key=f"tracks/{uid}/{uuid.uuid4().hex}.mp3",
                          cover_url=f"/watt/images/{cover}")
                db.add(t)
                await db.flush()
                ids.append(t.id)
            await db.commit()
        async with SessionLocal() as db:
            assert propre in await cles_du_contenu(db, "track", ids[0])
            assert partagee in await cles_du_contenu(db, "track", ids[1])
            await db.execute(text("UPDATE tracks SET taken_down_at = now() WHERE id = ANY(:i)"),
                             {"i": [ids[0], ids[1]]})
            await db.commit()
        async with SessionLocal() as db:
            assert not await utilise_hors_retrait(db, propre)       # déplacée
            assert await utilise_hors_retrait(db, partagee)         # reste publique
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.commit()
        await _nettoyer(uid)


# ── Protection audio : essais plafonnés ─────────────────────────────────────

async def test_protection_audio_plafonnee_a_5_essais():
    from app.services.fichiers_a_traiter import (
        MAX_TENTATIVES_PROTECTION,
        programmer,
        traiter_en_attente,
    )

    cle = f"tracks/pytest/{uuid.uuid4().hex}.wav"
    async with SessionLocal() as db:
        (iid,) = await programmer(db, [cle], "proteger_audio")
        await db.execute(text("UPDATE fichiers_a_traiter SET tentatives = :t WHERE id = :i"),
                         {"t": MAX_TENTATIVES_PROTECTION, "i": iid})
        await db.commit()
    try:
        res = await traiter_en_attente([iid])
        assert res == {"faites": 0, "en_attente": 0, "echecs": 0}
    finally:
        async with SessionLocal() as db:
            await db.execute(text("DELETE FROM fichiers_a_traiter WHERE id = :i"), {"i": iid})
            await db.commit()


# ── Lot I bis (vérification « zéro trou ») ──────────────────────────────────

async def test_invite_avec_code_publie_sans_seuil(monkeypatch):
    from app.services.droit_de_vendre import statut_vente

    monkeypatch.setattr(settings, "FEATURE_SELL_GATE", True)
    monkeypatch.setattr(settings, "SELL_GATE_DEPUIS", "2020-01-01")
    uid = await _user()
    (code,) = await _codes(1)
    try:
        async with SessionLocal() as db:
            u = await db.get(User, uid)
            assert (await statut_vente(db, u))["peut_vendre"] is False
            await pioneer_codes.utiliser(db, uid, code)
            await db.commit()
        async with SessionLocal() as db:
            u = await db.get(User, uid)
            st = await statut_vente(db, u)
            assert st["peut_vendre"] is True and st["raison"] == "invite_pionnier"
    finally:
        await _nettoyer(uid, codes=[code])


async def test_code_refuse_sur_admin_ou_deja_pionnier():
    admin = await _user(is_admin=True)
    deja = await _user()
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET pioneer_rank = 99, is_pioneer = TRUE WHERE id = :u"),
                         {"u": deja})
        await db.commit()
    c1, c2 = await _codes(2)
    try:
        async with SessionLocal() as db:
            with pytest.raises(pioneer_codes.CompteNonEligible):
                await pioneer_codes.utiliser(db, admin, c1)
            with pytest.raises(pioneer_codes.CompteNonEligible):
                await pioneer_codes.utiliser(db, deja, c2)
            libres = (await db.execute(text(
                "SELECT count(*) FROM pioneer_codes WHERE code = ANY(:c) AND used_at IS NULL"),
                {"c": [c1, c2]})).scalar_one()
        assert libres == 2  # aucun code gaspillé
    finally:
        await _nettoyer(admin, deja, codes=[c1, c2])


async def test_retro_exige_le_code_une_fois_le_programme_ouvert(monkeypatch):
    from app.routers.admin import _retro_exige_code

    monkeypatch.setattr(settings, "PIONEER_CODE_REQUIRED", True)
    monkeypatch.setattr(settings, "FEATURE_PIONEER", False)
    assert _retro_exige_code() is False
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    assert _retro_exige_code() is True


async def test_playlist_publique_refuse_le_son_d_un_autre(client, test_user, auth_headers):
    from app.models.playlist import Playlist
    from app.models.track import Track

    autre = await _user()
    async with SessionLocal() as db:
        t = Track(artist_id=autre, title="Son d'un autre",
                  r2_key=f"tracks/{autre}/{uuid.uuid4().hex}.mp3")
        pl = Playlist(owner_id=test_user["id"], title="Publique", visibility="public")
        db.add_all([t, pl])
        await db.commit()
        tid, plid = t.id, pl.id
    try:
        r = await client.post(f"/playlists/{plid}/tracks", headers=auth_headers,
                              json={"track_id": str(tid)})
        assert r.status_code == 422, r.text
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Playlist).where(Playlist.id == plid))
            await db.execute(delete(Track).where(Track.id == tid))
            await db.commit()
        await _nettoyer(autre)


async def test_remise_playlist_seulement_sur_les_sons_du_proprietaire():
    from app.models.owned_playlist_adn import OwnedPlaylistAdn
    from app.models.playlist import Playlist, PlaylistTrack
    from app.models.track import Track
    from app.services.marketplace import user_owns_playlist_adn_for_prompt

    curateur, artiste, acheteur = await _user(), await _user(), await _user()
    p_artiste = await _oeuvre(artiste)
    p_curateur = await _oeuvre(curateur)
    async with SessionLocal() as db:
        t_a = Track(artist_id=artiste, title="A", prompt_id=p_artiste,
                    r2_key=f"tracks/{artiste}/{uuid.uuid4().hex}.mp3")
        t_c = Track(artist_id=curateur, title="C", prompt_id=p_curateur,
                    r2_key=f"tracks/{curateur}/{uuid.uuid4().hex}.mp3")
        pl = Playlist(owner_id=curateur, title="P", visibility="public")
        db.add_all([t_a, t_c, pl])
        await db.flush()
        # Son d'un autre glissé directement en base (ancienne playlist).
        db.add_all([PlaylistTrack(playlist_id=pl.id, track_id=t_a.id, position=0),
                    PlaylistTrack(playlist_id=pl.id, track_id=t_c.id, position=1)])
        db.add(OwnedPlaylistAdn(user_id=acheteur, playlist_id=pl.id))
        await db.commit()
        plid = pl.id
    try:
        async with SessionLocal() as db:
            assert await user_owns_playlist_adn_for_prompt(db, user_id=acheteur, prompt_id=p_curateur)
            assert not await user_owns_playlist_adn_for_prompt(db, user_id=acheteur, prompt_id=p_artiste)
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OwnedPlaylistAdn).where(OwnedPlaylistAdn.playlist_id == plid))
            await db.execute(delete(PlaylistTrack).where(PlaylistTrack.playlist_id == plid))
            await db.execute(delete(Playlist).where(Playlist.id == plid))
            await db.execute(delete(Track).where(Track.artist_id.in_([artiste, curateur])))
            await db.commit()
        await _nettoyer(curateur, artiste, acheteur)


async def test_offre_adn_album_refusee_quand_les_albums_sont_masques(monkeypatch):
    from app.services.adn_offers import AdnNotPurchasable, resolve_adn_target

    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_ALBUMS", False)
    async with SessionLocal() as db:
        with pytest.raises(AdnNotPurchasable):
            await resolve_adn_target(db, target_type="album_adn", target_id=uuid.uuid4())


async def test_migration_0108_reclasse_achetes_et_gagnes_en_promo():
    import importlib.util
    import pathlib

    chemin = pathlib.Path(__file__).resolve().parents[1] / "alembic/versions/0108_reclasse_achetes_promo.py"
    spec = importlib.util.spec_from_file_location("m0108", chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    uid = await _user()
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET credits_balance = 150, smyles_achetes = 100, smyles_gagnes = 20, "
            "smyles_promo = 30, smyles_promo_gagnes = 0 WHERE id = :u"), {"u": uid})
        await db.commit()
    try:
        async with SessionLocal() as db:
            await db.execute(text(m.SQL_RECLASSER + " AND id = :u"), {"u": uid})
            await db.commit()
            r = (await db.execute(text(
                "SELECT credits_balance, smyles_achetes, smyles_gagnes, smyles_promo, "
                "smyles_promo_gagnes FROM users WHERE id = :u"), {"u": uid})).first()
        assert tuple(r) == (150, 0, 0, 150, 20)
    finally:
        await _nettoyer(uid)


def test_telemetrie_props_bornees():
    from app.routers.telemetry import EventIn

    assert EventIn(name="x", props={"a": 1}).props == {"a": 1}
    assert EventIn(name="x", props={"a": "y" * 5000}).props is None
    assert EventIn(name="x", props={str(i): i for i in range(40)}).props is None
