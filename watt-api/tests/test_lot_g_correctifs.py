"""Lot G — petits correctifs et décisions de Tom (un test par comportement)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

from tests.test_lot_a_securite import _PWD, _cleanup, _login, _prompt, _track, _user
from tests.test_parcours_v1 import _oeuvre

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


# ═══ Session ════════════════════════════════════════════════════════════════

def test_session_de_7_jours():
    assert settings.JWT_EXPIRE_MINUTES == 7 * 24 * 60


async def test_jeton_porte_l_identifiant_et_plus_l_email(client):
    import jwt

    from app.auth.jwt import create_access_token

    u = await _user()
    try:
        h = await _login(client, u["email"])
        claims = jwt.decode(h["Authorization"][7:], settings.SECRET_KEY,
                            algorithms=[settings.JWT_ALGORITHM])
        assert claims["sub"] == str(u["id"])
        # Un ancien jeton « email » ne désigne plus aucun compte.
        ancien = create_access_token(u["email"])
        r = await client.get("/users/me", headers={"Authorization": f"Bearer {ancien}"})
        assert r.status_code == 401
    finally:
        await _cleanup(u["id"])


async def test_compte_suspendu_peut_exporter_et_supprimer(client):
    u = await _user()
    try:
        h = await _login(client, u["email"])
        await _sql("UPDATE users SET is_banned = TRUE WHERE id = :u", u=u["id"])
        # Session ouverte avant la suspension : tout est refusé sauf ses données.
        assert (await client.get("/users/me", headers=h)).status_code == 403
        assert (await client.get("/users/me/export", headers=h)).status_code == 200
        # Connexion d'un compte suspendu : refus + jeton limité aux données.
        r = await client.post("/auth/login", json={"email": u["email"], "password": _PWD})
        assert r.status_code == 403
        body = r.json()
        assert body["code"] == "compte_suspendu" and body["jeton_rgpd"]
        hr = {"Authorization": f"Bearer {body['jeton_rgpd']}"}
        assert (await client.get("/users/me/export", headers=hr)).status_code == 200
        assert (await client.get("/users/me/suppression", headers=hr)).status_code == 200
        assert (await client.get("/users/me", headers=hr)).status_code == 401
        assert (await client.get("/me/library/prompts", headers=hr)).status_code == 401
        r = await client.post("/users/me/delete", headers=hr, json={
            "confirmation": "SUPPRIMER", "renonce_smyles": True, "mot_de_passe": _PWD})
        assert r.status_code == 204, r.text
    finally:
        await _cleanup(u["id"])


async def test_notifications_sans_cgu_a_jour(client):
    u = await _user()
    try:
        h = await _login(client, u["email"])
        await _sql("UPDATE users SET accepted_terms_version = NULL WHERE id = :u", u=u["id"])
        r = await client.post("/me/notifications/read-all", headers=h)
        assert r.status_code == 204, r.text
        r = await client.patch("/users/me", headers=h, json={"bio": "x"})
        assert r.status_code == 403  # le reste attend toujours l'acceptation
    finally:
        await _cleanup(u["id"])


# ═══ Export ═════════════════════════════════════════════════════════════════

async def test_export_rattache_les_signalements_par_email_verifie_seulement(client):
    u = await _user()
    rid = uuid.uuid4()
    try:
        await _sql("INSERT INTO content_reports (id, reporter_email, target_type, target_id, reason, "
                   "detail, status) VALUES (:i, :e, 'track', 'x', 'autre', 'Déposé anonymement', 'new')",
                   i=rid, e=u["email"].upper())
        h = await _login(client, u["email"])
        ids = {x["id"] for x in (await client.get("/users/me/export", headers=h)).json()["signalements_faits"]}
        assert str(rid) not in ids
        await _sql("UPDATE users SET email_verified = TRUE WHERE id = :u", u=u["id"])
        ids = {x["id"] for x in (await client.get("/users/me/export", headers=h)).json()["signalements_faits"]}
        assert str(rid) in ids
    finally:
        await _sql("DELETE FROM content_reports WHERE id = :i", i=rid)
        await _cleanup(u["id"])


# ═══ Collections, Mes Œuvres ════════════════════════════════════════════════

async def test_son_masque_absent_des_collections():
    from app.models.playlist import Playlist
    from app.routers.oeuvre import _son_payload

    a = await _user()
    try:
        rec = await _prompt(a["id"])
        visible = await _track(a["id"], prompt_id=rec)
        masque = await _track(a["id"], prompt_id=rec, hidden_at=datetime.now(timezone.utc))
        pl = (await _sql("INSERT INTO playlists (id, owner_id, title, visibility) VALUES "
                         "(gen_random_uuid(), :u, 'Col', 'public') RETURNING id", u=a["id"]))[0][0]
        for i, t in enumerate((visible, masque)):
            await _sql("INSERT INTO playlist_tracks (playlist_id, track_id, position) "
                       "VALUES (:p, :t, :i)", p=pl, t=t, i=i)
        async with SessionLocal() as db:
            p = await db.get(Playlist, pl)
            out = await _son_payload(db, p, set())
        assert [t["trackId"] for t in out["tracks"]] == [str(visible)]
    finally:
        await _cleanup(a["id"])


async def test_oeuvre_retiree_non_modifiable(client):
    from app.services.moderation import takedown_content

    a = await _user()
    try:
        o = await _oeuvre(a["id"])
        # L'image de l'Œuvre est retirée (le son lui-même reste listé dans
        # « Mes Œuvres ») : plus aucune modification possible.
        async with SessionLocal() as db:
            await takedown_content(db, "image", str(o["image"]), "Contrefaçon")
            await db.commit()
        h = await _login(client, a["email"])
        r = await client.patch(f"/artist/me/oeuvres/{o['track']}", headers=h, json={"title": "Nouveau titre"})
        assert r.status_code == 422 and "retirée par la modération" in r.json()["detail"]
        r = await client.post("/artist/me/oeuvres/actions", headers=h, json={
            "track_ids": [str(o["track"])], "action": "prix", "prix": 100})
        assert r.status_code == 200 and r.json()["ignores"] == [str(o["track"])]
        prix = (await _sql("SELECT price_credits FROM prompts WHERE id = :i", i=o["recette"]))[0][0]
        assert prix == 15
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"])


# ═══ Prix plafonnés, noms de fichiers, en-têtes, limites ════════════════════

def test_prix_des_beats_et_des_packs_plafonnes():
    from app.schemas.beat import BeatCreate
    from app.schemas.track import PACK_PRICE_MAX, TrackUpdate

    base = {"title": "Mon beat", "license_type": "lease"}
    BeatCreate(**base, price_credits=150)
    with pytest.raises(ValidationError):
        BeatCreate(**base, price_credits=151)
    TrackUpdate(pack_price_credits=PACK_PRICE_MAX)
    with pytest.raises(ValidationError):
        TrackUpdate(pack_price_credits=PACK_PRICE_MAX + 1)


def test_nom_de_fichier_utf8():
    from app.core.fichiers import entete_piece_jointe

    h = entete_piece_jointe("Cœur d'été 🌙", "mp3")
    h.encode("latin-1")  # sinon le serveur répondait 500
    assert h.startswith('attachment; filename="Coeur d\'ete .mp3"') or 'filename="' in h
    assert "filename*=UTF-8''C%C5%93ur%20d%27%C3%A9t%C3%A9%20%F0%9F%8C%99.mp3" in h
    assert entete_piece_jointe(None, "png", defaut="image").startswith('attachment; filename="image.png"')
    assert "/" not in entete_piece_jointe("../../etc/passwd", "txt").split("filename*=")[0]


async def test_en_tetes_de_securite_sur_images(client):
    for chemin in (f"/images/{uuid.uuid4()}/download", "/images-create.js"):
        r = await client.get(chemin)
        assert r.headers.get("x-content-type-options") == "nosniff", chemin
        assert r.headers.get("x-frame-options") == "SAMEORIGIN", chemin


def test_limites_de_debit_lot_g():
    from limits import parse_many

    import app.main  # noqa: F401
    from app.core import ratelimit as rl

    attendues = {
        "app.routers.mes_oeuvres.action_sur_mes_oeuvres": rl.LIMIT_OEUVRES_ACTIONS,
        "app.routers.users.export_me": rl.LIMIT_EXPORT,
        "app.routers.users.delete_me": rl.LIMIT_SUPPRESSION_COMPTE,
        "app.routers.users.delete_me_post": rl.LIMIT_SUPPRESSION_COMPTE,
    }
    for nom, lim in attendues.items():
        posees = {str(x.limit) for x in rl.limiter._route_limits[nom]}
        assert posees == {str(i) for i in parse_many(lim)}, nom


# ═══ Signalements ═══════════════════════════════════════════════════════════

async def test_signalement_explication_obligatoire(client):
    base = {"good_faith": True, "target_type": "track", "target_id": str(uuid.uuid4()),
            "reason": "autre"}
    for detail in (None, "", "   court  "):
        r = await client.post("/reports", json={**base, "detail": detail})
        assert r.status_code == 422, (detail, r.text)
        assert "10 caractères" in r.json()["detail"]
    r = await client.post("/reports", json={**base, "detail": "Contenu manifestement copié"})
    assert r.status_code == 201, r.text
    await _sql("DELETE FROM content_reports WHERE id = :i", i=uuid.UUID(r.json()["id"]))


async def test_accuse_de_reception_seulement_vers_un_email_verifie(client, monkeypatch):
    envoyes = []

    async def _faux(to, subject, html, *, reply_to=None):
        envoyes.append((to, subject))
        return True

    monkeypatch.setattr("app.services.emails._send", _faux)
    monkeypatch.delenv("REPORT_NOTIFY_EMAIL", raising=False)
    u = await _user()
    ids = []
    try:
        corps = {"good_faith": True, "target_type": "track", "target_id": str(uuid.uuid4()),
                 "reason": "autre", "detail": "Contenu manifestement copié"}
        r = await client.post("/reports", json={**corps, "reporter_email": "victime@example.org"})
        ids.append(r.json()["id"])
        h = await _login(client, u["email"])
        r = await client.post("/reports", headers=h, json=corps)
        ids.append(r.json()["id"])
        assert envoyes == []  # adresse tapée, ou compte non vérifié : rien
        await _sql("UPDATE users SET email_verified = TRUE WHERE id = :u", u=u["id"])
        r = await client.post("/reports", headers=h, json=corps)
        ids.append(r.json()["id"])
        assert [e[0] for e in envoyes] == [u["email"]]
    finally:
        for i in ids:
            await _sql("DELETE FROM content_reports WHERE id = :i", i=uuid.UUID(i))
        await _cleanup(u["id"])


async def test_purge_des_signalements_3_ans_apres_la_decision():
    from app.services.moderation import purger_signalements_anciens

    vieux = datetime.now(timezone.utc) - timedelta(days=3 * 365 + 2)
    recent = datetime.now(timezone.utc) - timedelta(days=3 * 365 - 2)
    ids = {k: uuid.uuid4() for k in ("vieux_retire", "vieux_rejete", "recent", "ouvert")}
    lignes = (("vieux_retire", "actioned", vieux), ("vieux_rejete", "rejected", vieux),
              ("recent", "actioned", recent), ("ouvert", "new", None))
    try:
        for k, st, quand in lignes:
            await _sql("INSERT INTO content_reports (id, target_type, target_id, reason, detail, status, "
                       "created_at, resolved_at) VALUES (:i, 'track', 'x', 'autre', 'Signalement ancien', "
                       ":s, :c, :r)", i=ids[k], s=st, c=vieux - timedelta(days=1), r=quand)
        async with SessionLocal() as db:
            n = await purger_signalements_anciens(db)
            await db.commit()
        assert n >= 2
        restants = {r[0] for r in await _sql(
            "SELECT id FROM content_reports WHERE id = ANY(:i)", i=list(ids.values()))}
        assert restants == {ids["recent"], ids["ouvert"]}
    finally:
        await _sql("DELETE FROM content_reports WHERE id = ANY(:i)", i=list(ids.values()))


# ═══ Publication d'un son ═══════════════════════════════════════════════════

async def test_pochette_et_outil_obligatoires(client):
    a = await _user()
    try:
        h = await _login(client, a["email"])
        base = {"title": "Son", "full_prompt": "deep house",
                "r2_key": f"tracks/{a['id']}/son-0123abcd.mp3"}
        cover = f"/watt/images/images/track-cover/{a['id']}/c.png"
        r = await client.post("/tracks/", headers=h, json={**base, "platform": "suno"})
        assert r.status_code == 422 and "pochette" in r.json()["detail"]
        r = await client.post("/tracks/", headers=h, json={**base, "cover_url": cover})
        assert r.status_code == 422 and "outil" in r.json()["detail"]
        r = await client.post("/tracks/", headers=h, json={**base, "cover_url": cover, "platform": "suno"})
        assert r.status_code == 201, r.text
    finally:
        await _cleanup(a["id"])


async def test_profil_public_automatiquement_au_premier_son(client):
    a = await _user(public=False)
    try:
        h = await _login(client, a["email"])
        r = await client.post("/tracks/", headers=h, json={
            "title": "Premier son", "full_prompt": "deep house", "platform": "suno",
            "r2_key": f"tracks/{a['id']}/son-0123abcd.mp3",
            "cover_url": f"/watt/images/images/track-cover/{a['id']}/c.png"})
        assert r.status_code == 201, r.text
        assert (await client.get("/users/me", headers=h)).json()["profile_public"] is True
    finally:
        await _cleanup(a["id"])


async def test_sans_nom_d_artiste_le_son_attend(client):
    a = await _user(public=False)
    try:
        await _sql("UPDATE users SET artist_name = NULL WHERE id = :u", u=a["id"])
        h = await _login(client, a["email"])
        r = await client.post("/tracks/", headers=h, json={
            "title": "Son", "full_prompt": "x", "platform": "suno",
            "r2_key": f"tracks/{a['id']}/son-0123abcd.mp3",
            "cover_url": f"/watt/images/images/track-cover/{a['id']}/c.png"})
        assert r.status_code == 409
        assert "nom d'artiste" in r.json()["detail"]["message"]
    finally:
        await _cleanup(a["id"])


def test_version_de_l_outil_obligatoire_pour_une_recette():
    from app.schemas.marketplace import PromptCreate

    base = {"title": "Ma recette", "prompt_text": "y" * 100, "price_credits": 15,
            "prompt_platform": "suno", "prompt_weirdness": "50",
            "prompt_style_influence": "house", "prompt_vocal_gender": "instrumental"}
    with pytest.raises(ValidationError):
        PromptCreate(**base)
    with pytest.raises(ValidationError):
        PromptCreate(**base, prompt_model_version="")
    assert PromptCreate(**base, prompt_model_version="v4.5").prompt_model_version == "v4.5"
