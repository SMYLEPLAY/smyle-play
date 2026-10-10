"""Lot D — conformité DSA / RGPD.

1. Boucle DSA : motif obligatoire, emails (auteur + signaleur, titres
   échappés, voie de recours), journal, retrait des collections, suspension
   qui masque puis rétablit les contenus, déclaration de bonne foi.
2. Version des CGU : enregistrée à l'inscription, écritures refusées tant
   qu'elle n'est pas à jour, ré-acceptation.
3. Suppression de compte complète (renonciation vérifiée par le serveur).
4. Export RGPD complet.
5. Mesure d'audience : jamais rattachée à un compte, purge à 13 mois.
6. Emails en minuscules (code + contrôle des doublons de la migration).
7. Pied de page légal sur les pages publiques.
"""
import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.legal import CGU_VERSION, CODE_CGU_A_ACCEPTER, CONTACT_EMAIL
from app.database import SessionLocal
from app.models.adn import Adn
from app.models.album import Album
from app.models.content_report import ContentReport
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

PWD = "12345678"
REPO = Path(__file__).resolve().parents[2]


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _mk_user(*, official=False, email=None, **flags) -> dict:
    email = email or f"pytest-lotd-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password=PWD))
        uid = u.id
        vals = dict(flags)
        if official:
            vals["is_official"] = True
        if vals:
            await db.execute(update(User).where(User.id == uid).values(**vals))
            await db.commit()
    return {"id": uid, "email": email.strip().lower()}


async def _h(client: AsyncClient, u: dict) -> dict:
    r = await client.post("/auth/login", json={"email": u["email"], "password": PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _sql(sql: str, **p):
    async with SessionLocal() as db:
        res = await db.execute(text(sql), p)
        try:
            rows = res.all()
        except Exception:  # noqa: BLE001 — requête sans résultat
            rows = None
        await db.commit()
        return rows


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(text("DELETE FROM content_reports WHERE reporter_id = :u"), {"u": uid})
            await db.execute(text("DELETE FROM pioneer_revocations WHERE user_id = :u"), {"u": uid})
            await db.execute(text("DELETE FROM dna WHERE artist_id = :u"), {"u": uid})
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest.fixture
def emails(monkeypatch):
    """Capture les envois (Resend n'est pas configuré en test)."""
    envoyes = []

    async def _faux_send(to, subject, html, *, reply_to=None):
        envoyes.append({"to": to, "subject": subject, "html": html, "reply_to": reply_to})
        return True

    monkeypatch.setattr("app.services.emails._send", _faux_send)
    return envoyes


async def _prompt(uid, title="Recette test", published=True) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title=title, description="Tagline",
                   prompt_text="X" * 100, price_credits=10, is_published=published)
        db.add(p)
        await db.commit()
        return p.id


async def _track(uid, prompt_id=None, title="Son test") -> uuid.UUID:
    async with SessionLocal() as db:
        t = Track(artist_id=uid, title=title, prompt_id=prompt_id,
                  r2_key=f"tracks/{uid}/son-{uuid.uuid4().hex[:6]}.mp3")
        db.add(t)
        await db.commit()
        return t.id


async def _playlist(uid, title="Ma playlist", visibility="public") -> uuid.UUID:
    async with SessionLocal() as db:
        p = Playlist(owner_id=uid, title=title, visibility=visibility)
        db.add(p)
        await db.commit()
        return p.id


async def _journal(cible_id, action):
    return await _sql("SELECT motif, details, admin_id FROM admin_journal "
                      "WHERE cible_id = :c AND action = :a ORDER BY created_at",
                      c=str(cible_id), a=action)


# ═══ 1. Boucle DSA ════════════════════════════════════════════════════════════

async def test_signalement_exige_la_bonne_foi(client):
    body = {"target_type": "track", "target_id": str(uuid.uuid4()),
            "reason": "autre", "detail": "Test bonne foi"}
    r = await client.post("/reports", json=body)
    assert r.status_code == 422, r.text
    assert "bonne foi" in r.json()["detail"]
    r = await client.post("/reports", json={**body, "good_faith": True})
    assert r.status_code == 201, r.text
    await _sql("DELETE FROM content_reports WHERE id = :i", i=uuid.UUID(r.json()["id"]))


async def test_retrait_sur_signalement_motif_obligatoire_emails_et_journal(client, emails):
    admin = await _mk_user(official=True)
    auteur = await _mk_user()
    signaleur = await _mk_user()
    try:
        pid = await _prompt(auteur["id"], title="<b>Titre</b> & piège")
        hs = await _h(client, signaleur)
        r = await client.post("/reports", headers=hs, json={
            "good_faith": True, "target_type": "prompt", "target_id": str(pid),
            "reason": "contrefacon", "detail": "copie"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        emails.clear()  # accusé de réception

        ha = await _h(client, admin)
        r = await client.post(f"/admin/reports/{rid}/takedown", headers=ha,
                              json={"ban_owner": False})
        assert r.status_code == 422, r.text  # motif absent
        r = await client.post(f"/admin/reports/{rid}/takedown", headers=ha,
                              json={"ban_owner": False, "reason": "  "})
        assert r.status_code == 422, r.text  # motif vide
        r = await client.post(f"/admin/reports/{rid}/takedown", headers=ha,
                              json={"ban_owner": False, "reason": "Contrefaçon avérée"})
        assert r.status_code == 200, r.text

        a = [e for e in emails if e["to"] == auteur["email"]]
        assert len(a) == 1, emails
        assert "Contrefaçon avérée" in a[0]["html"]
        assert CONTACT_EMAIL in a[0]["html"] and "réponds" in a[0]["html"]
        assert a[0]["reply_to"] == CONTACT_EMAIL
        assert "<b>Titre</b>" not in a[0]["html"]
        assert "&lt;b&gt;Titre&lt;/b&gt; &amp; piège" in a[0]["html"]
        s = [e for e in emails if e["to"] == signaleur["email"]]
        assert len(s) == 1 and "a retiré" in s[0]["html"], emails
        assert rid in s[0]["html"]

        j = await _journal(pid, "retrait")
        assert j and j[-1].motif == "Contrefaçon avérée" and j[-1].admin_id == admin["id"]
    finally:
        await _sql("DELETE FROM content_reports WHERE target_id = :t", t=str(pid))
        await _cleanup(admin["id"], auteur["id"], signaleur["id"])


async def test_rejet_du_signalement_informe_le_signaleur_anonyme(client, emails):
    admin = await _mk_user(official=True)
    try:
        r = await client.post("/reports", json={
            "good_faith": True, "target_type": "track", "target_id": str(uuid.uuid4()),
            "reason": "autre", "reporter_email": "Anonyme.Lotd@Example.org"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        emails.clear()
        r = await client.patch(f"/admin/reports/{rid}", headers=await _h(client, admin),
                               json={"status": "rejected"})
        assert r.status_code == 200, r.text
        assert len(emails) == 1, emails
        assert emails[0]["to"].lower() == "anonyme.lotd@example.org"
        assert "ne contrevient pas" in emails[0]["html"]
    finally:
        await _sql("DELETE FROM content_reports WHERE id = :i", i=uuid.UUID(rid))
        await _cleanup(admin["id"])


async def test_suspension_motif_obligatoire_masque_puis_retablit(client, emails):
    admin = await _mk_user(official=True)
    createur = await _mk_user(profile_public=True)
    acheteur = await _mk_user()
    try:
        uid = createur["id"]
        p_pub = await _prompt(uid, "Publiée")
        p_brouillon = await _prompt(uid, "Brouillon", published=False)
        p_retiree = await _prompt(uid, "Retirée pendant la suspension")
        tid = await _track(uid)
        pl = await _playlist(uid)
        # Un acheteur possède déjà un exemplaire : il le garde.
        await _sql("INSERT INTO unlocked_prompts (id, current_owner_id, prompt_id, original_artist_id) "
                   "VALUES (gen_random_uuid(), :b, :p, :a)", b=acheteur["id"], p=p_pub, a=uid)
        ha = await _h(client, admin)

        r = await client.post(f"/admin/users/{uid}/ban", headers=ha, json={})
        assert r.status_code == 422, r.text
        r = await client.post(f"/admin/users/{uid}/ban", headers=ha, json={"reason": "Fraude"})
        assert r.status_code == 200, r.text
        sus = [e for e in emails if e["to"] == createur["email"]]
        assert sus and "suspendu" in sus[0]["html"] and "Fraude" in sus[0]["html"]
        assert CONTACT_EMAIL in sus[0]["html"]

        etat = (await _sql(
            "SELECT (SELECT is_published FROM prompts WHERE id = :p) AS pub, "
            "(SELECT hidden_at IS NOT NULL FROM tracks WHERE id = :t) AS cache, "
            "(SELECT visibility FROM playlists WHERE id = :pl) AS vis, "
            "(SELECT profile_public FROM users WHERE id = :u) AS profil, "
            "(SELECT count(*) FROM unlocked_prompts WHERE prompt_id = :p AND current_owner_id = :b) AS achat",
            p=p_pub, t=tid, pl=pl, u=uid, b=acheteur["id"]))[0]
        assert etat.pub is False and etat.cache is True and etat.vis == "private"
        assert etat.profil is False and etat.achat == 1
        j = await _journal(uid, "bannissement")
        assert j and j[-1].motif == "Fraude"

        # Retrait décidé pendant la suspension : ne revient pas à la levée.
        r = await client.post("/admin/moderation/takedown", headers=ha, json={
            "target_type": "prompt", "target_id": str(p_retiree), "reason": "Hors règles"})
        assert r.status_code == 200, r.text

        emails.clear()
        r = await client.post(f"/admin/users/{uid}/unban", headers=ha, json={"reason": "Erreur"})
        assert r.status_code == 200, r.text
        assert any(e["to"] == createur["email"] and "rétabli" in e["subject"] for e in emails)
        etat = (await _sql(
            "SELECT (SELECT is_published FROM prompts WHERE id = :p) AS pub, "
            "(SELECT is_published FROM prompts WHERE id = :pb) AS brouillon, "
            "(SELECT is_published FROM prompts WHERE id = :pr) AS retiree, "
            "(SELECT hidden_at IS NULL FROM tracks WHERE id = :t) AS visible, "
            "(SELECT visibility FROM playlists WHERE id = :pl) AS vis, "
            "(SELECT profile_public FROM users WHERE id = :u) AS profil",
            p=p_pub, pb=p_brouillon, pr=p_retiree, t=tid, pl=pl, u=uid))[0]
        assert etat.pub is True and etat.visible is True and etat.vis == "public"
        assert etat.profil is True
        assert etat.brouillon is False  # jamais publié : reste un brouillon
        assert etat.retiree is False    # retiré par la modération : reste retiré
        assert await _journal(uid, "levee_suspension")
    finally:
        await _sql("DELETE FROM unlocked_prompts WHERE current_owner_id = :b", b=acheteur["id"])
        await _cleanup(admin["id"], createur["id"], acheteur["id"])


async def test_collections_retirables_et_restaurables(client, emails):
    admin = await _mk_user(official=True)
    owner = await _mk_user()
    try:
        pl = await _playlist(owner["id"], "Playlist <script>")
        async with SessionLocal() as db:
            al = Album(owner_id=owner["id"], title="Album test", visibility="public")
            db.add(al)
            await db.commit()
            alid = al.id
        ha = await _h(client, admin)
        for ttype, cid in (("playlist", pl), ("album", alid)):
            r = await client.post("/admin/moderation/takedown", headers=ha, json={
                "target_type": ttype, "target_id": str(cid), "reason": "Pochette illicite"})
            assert r.status_code == 200, r.text
        table = {"playlist": "playlists", "album": "albums"}
        for ttype, cid in (("playlist", pl), ("album", alid)):
            row = (await _sql(f"SELECT visibility, taken_down_at FROM {table[ttype]} WHERE id = :i",
                              i=cid))[0]
            assert row.visibility == "private" and row.taken_down_at is not None
            assert await _journal(cid, "retrait")
        # Le propriétaire ne peut pas la republier (trigger).
        await _sql("UPDATE playlists SET visibility = 'public' WHERE id = :i", i=pl)
        assert (await _sql("SELECT visibility FROM playlists WHERE id = :i", i=pl))[0].visibility == "private"
        with pytest.raises(DBAPIError):
            await _sql("UPDATE playlists SET taken_down_at = NULL WHERE id = :i", i=pl)
        # Disparaît des listes publiques.
        r = await client.get(f"/watt/playlists/{pl}")
        assert r.status_code in (403, 404), r.text
        # Email à l'auteur, titre échappé.
        mail = [e for e in emails if e["to"] == owner["email"]]
        assert mail and "&lt;script&gt;" in mail[0]["html"] and "<script>" not in mail[0]["html"]

        r = await client.get("/admin/contenus-retires", headers=ha)
        types = {(c["type"], c["id"]) for c in r.json()["contenus"]}
        assert ("playlist", str(pl)) in types and ("album", str(alid)) in types

        r = await client.post(f"/admin/contenus-retires/playlist/{pl}/restaurer", headers=ha,
                              json={"reason": "Pochette remplacée"})
        assert r.status_code == 200, r.text
        row = (await _sql("SELECT visibility, taken_down_at FROM playlists WHERE id = :i", i=pl))[0]
        assert row.visibility == "public" and row.taken_down_at is None
        assert await _journal(pl, "restauration")
    finally:
        await _cleanup(admin["id"], owner["id"])


# ═══ 2. Version des CGU ═══════════════════════════════════════════════════════

async def test_inscription_enregistre_la_version_des_cgu(client):
    email = f"pytest-lotd-reg-{uuid.uuid4().hex[:8]}@smyleplay.example"
    r = await client.post("/auth/register", json={
        "email": email, "password": PWD, "accept_terms": True, "age_confirmed": True})
    assert r.status_code == 201, r.text
    uid = uuid.UUID(r.json()["id"])
    try:
        row = (await _sql("SELECT accepted_terms_version, accepted_terms_at FROM users WHERE id = :u",
                          u=uid))[0]
        assert row.accepted_terms_version == CGU_VERSION and row.accepted_terms_at is not None
        me = (await client.get("/users/me", headers=await _h(client, {"email": email}))).json()
        assert me["cgu_a_jour"] is True and me["cgu_version"] == CGU_VERSION
    finally:
        await _cleanup(uid)


async def test_cgu_a_accepter_bloque_les_ecritures_pas_la_lecture(client):
    u = await _mk_user()
    try:
        await _sql("UPDATE users SET accepted_terms_version = NULL WHERE id = :u", u=u["id"])
        h = await _h(client, u)
        r = await client.get("/users/me", headers=h)
        assert r.status_code == 200 and r.json()["cgu_a_jour"] is False
        for methode, chemin, corps in (("PATCH", "/users/me", {"bio": "x"}),
                                       ("POST", "/playlists", {"title": "P"}),
                                       ("POST", f"/unlocks/prompts/{uuid.uuid4()}", None)):
            r = await client.request(methode, chemin, headers=h, json=corps)
            assert r.status_code == 403, (chemin, r.text)
            assert r.json()["code"] == CODE_CGU_A_ACCEPTER, r.text
            assert r.json()["cgu_version"] == CGU_VERSION
        r = await client.post("/users/me/accept-terms", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["accepted_terms_version"] == CGU_VERSION and r.json()["cgu_a_jour"] is True
        r = await client.patch("/users/me", headers=h, json={"bio": "ok"})
        assert r.status_code == 200, r.text
    finally:
        await _cleanup(u["id"])


async def test_migration_laisse_les_comptes_existants_a_null():
    src = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "0102_lot_d_conformite.py").read_text()
    assert 'sa.Column("accepted_terms_version", sa.String(20), nullable=True)' in src
    assert "UPDATE users SET accepted_terms_version" not in src


# ═══ 3. Suppression de compte ═════════════════════════════════════════════════

async def test_suppression_exige_la_renonciation(client):
    u = await _mk_user()
    try:
        h = await _h(client, u)
        r = await client.request("DELETE", "/users/me", headers=h)
        assert r.status_code == 422, r.text
        r = await client.request("DELETE", "/users/me", headers=h,
                                 json={"confirmation": "SUPPRIMER", "renonce_smyles": False})
        assert r.status_code == 422, r.text
        r = await client.request("DELETE", "/users/me", headers=h,
                                 json={"confirmation": "supprimer", "renonce_smyles": True})
        assert r.status_code == 422, r.text
        assert (await client.get("/users/me", headers=h)).status_code == 200
    finally:
        await _cleanup(u["id"])


async def test_suppression_complete(client, monkeypatch):
    from app.services import pioneer as pioneer_mod

    async def _personne(*a, **k):
        return []

    monkeypatch.setattr(pioneer_mod, "retro_candidates", _personne)

    vendeur = await _mk_user(signup_ip="203.0.113.7", profile_public=True)
    acheteur = await _mk_user()
    ami = await _mk_user()
    uid = vendeur["id"]
    try:
        p_vendu = await _prompt(uid, "Vendue")
        p_invendu = await _prompt(uid, "Invendue")
        t_vendu = await _track(uid, prompt_id=p_vendu)
        t_invendu = await _track(uid, prompt_id=p_invendu)
        pl = await _playlist(uid)
        async with SessionLocal() as db:
            a = Adn(artist_id=uid, description="D" * 200, price_credits=500, is_published=True)
            db.add(a)
            await db.commit()
            adn_id = a.id
        await _sql("INSERT INTO unlocked_prompts (id, current_owner_id, prompt_id, original_artist_id, resale_price) "
                   "VALUES (gen_random_uuid(), :b, :p, :a, NULL)", b=acheteur["id"], p=p_vendu, a=uid)
        await _sql("INSERT INTO user_follows (id, follower_id, followee_id) VALUES (gen_random_uuid(), :a, :b), "
                   "(gen_random_uuid(), :b, :a)", a=uid, b=ami["id"])
        th = (await _sql("INSERT INTO message_threads (id, participant_a, participant_b) "
                         "VALUES (gen_random_uuid(), :a, :b) RETURNING id", a=uid, b=ami["id"]))[0].id
        await _sql("INSERT INTO messages (id, thread_id, sender_id, content) VALUES "
                   "(gen_random_uuid(), :t, :a, 'salut')", t=th, a=uid)
        await _sql("UPDATE users SET avatar_url = :av WHERE id = :u",
                   av=f"/watt/images/images/avatar/{uid}/moi.jpg", u=uid)
        rang_libre = (await _sql("SELECT g FROM generate_series(1, 100) g WHERE NOT EXISTS "
                                 "(SELECT 1 FROM users WHERE pioneer_rank = g) LIMIT 1"))
        if rang_libre:
            await _sql("UPDATE users SET is_pioneer = TRUE, pioneer_rank = :r, pioneer_awarded_at = now() "
                       "WHERE id = :u", r=rang_libre[0].g, u=uid)
        tx_avant = (await _sql("SELECT count(*) AS n FROM transactions WHERE buyer_id = :u OR seller_id = :u",
                               u=uid))[0].n

        h = await _h(client, vendeur)
        apercu = (await client.get("/users/me/suppression", headers=h)).json()
        assert apercu["smyles"]["total"] == 30
        assert apercu["oeuvres"]["conservees_pour_acheteurs"] == 2  # recette vendue + son lié

        from app.services import account_deletion
        purges = []

        async def _faux_purger(cles):
            purges.extend(cles)

        monkeypatch.setattr(account_deletion, "purger_fichiers", _faux_purger)
        r = await client.request("DELETE", "/users/me", headers=h,
                                 json={"confirmation": "SUPPRIMER", "renonce_smyles": True})
        assert r.status_code == 204, r.text
        assert (await client.get("/users/me", headers=h)).status_code == 401

        u = (await _sql("SELECT * FROM users WHERE id = :u", u=uid))[0]
        assert u.email == f"deleted-{uid}@deleted.watt" and u.artist_name == "Artiste supprimé"
        assert u.signup_ip is None and u.avatar_url is None and u.profile_public is False
        assert u.credits_balance == 0 and u.smyles_promo == 0 and u.smyles_gagnes == 0
        assert u.pioneer_rank is None and u.is_pioneer is False
        # Œuvre achetée : conservée (acheteur), retirée du public.
        assert (await _sql("SELECT is_published FROM prompts WHERE id = :p", p=p_vendu))[0].is_published is False
        assert (await _sql("SELECT count(*) AS n FROM unlocked_prompts WHERE prompt_id = :p "
                           "AND current_owner_id = :b", p=p_vendu, b=acheteur["id"]))[0].n == 1
        assert (await _sql("SELECT count(*) AS n FROM tracks WHERE id = :t", t=t_vendu))[0].n == 1
        # Œuvres jamais achetées : effacées.
        for table, i in (("prompts", p_invendu), ("tracks", t_invendu), ("playlists", pl), ("adns", adn_id)):
            assert (await _sql(f"SELECT count(*) AS n FROM {table} WHERE id = :i", i=i))[0].n == 0, table
        # Messages, abonnements effacés.
        assert (await _sql("SELECT count(*) AS n FROM message_threads WHERE id = :t", t=th))[0].n == 0
        assert (await _sql("SELECT count(*) AS n FROM user_follows WHERE follower_id = :u OR followee_id = :u",
                           u=uid))[0].n == 0
        # Registre intact (+ la destruction du solde).
        tx = await _sql("SELECT type, credits_amount FROM transactions WHERE buyer_id = :u OR seller_id = :u",
                        u=uid)
        assert len(tx) == tx_avant + 1
        assert any(t.type == "burn" and t.credits_amount == 30 for t in tx)
        # Fichiers à purger : avatar + son invendu, jamais le son vendu.
        assert f"images/avatar/{uid}/moi.jpg" in purges
        assert any(k.startswith(f"tracks/{uid}/") for k in purges)
        cle_vendue = (await _sql("SELECT r2_key FROM tracks WHERE id = :t", t=t_vendu))[0].r2_key
        assert cle_vendue not in purges
        if rang_libre:
            rev = await _sql("SELECT reason FROM pioneer_revocations WHERE user_id = :u", u=uid)
            assert rev and "supprimé" in rev[0].reason
    finally:
        await _sql("DELETE FROM unlocked_prompts WHERE current_owner_id = :b", b=acheteur["id"])
        await _sql("DELETE FROM prompts WHERE artist_id = :u", u=uid)
        await _cleanup(acheteur["id"], ami["id"], uid)


async def test_purge_des_fichiers_epargne_ceux_encore_utilises(monkeypatch):
    from app.services import account_deletion, r2

    u = await _mk_user()
    supprimes = []

    async def _faux_delete(key, *, bucket=None):
        supprimes.append(key)
        return True

    monkeypatch.setattr(r2, "delete_r2_object", _faux_delete)
    try:
        utilise = f"tracks/{u['id']}/encore.mp3"
        await _track(u["id"])
        await _sql("UPDATE tracks SET r2_key = :k WHERE artist_id = :u", k=utilise, u=u["id"])
        orphelin = f"tracks/{u['id']}/orphelin.mp3"
        out = await account_deletion.purger_fichiers([utilise, orphelin])
        assert orphelin in supprimes and utilise not in supprimes
        assert out["gardes"] == 1
    finally:
        await _cleanup(u["id"])


# ═══ 4. Export RGPD ═══════════════════════════════════════════════════════════

async def test_export_couvre_toutes_les_donnees(client):
    u = await _mk_user()
    ami = await _mk_user()
    try:
        await _prompt(u["id"], "Mon œuvre")
        await _sql("INSERT INTO user_follows (id, follower_id, followee_id) VALUES (gen_random_uuid(), :a, :b)",
                    a=u["id"], b=ami["id"])
        th = (await _sql("INSERT INTO message_threads (id, participant_a, participant_b) "
                         "VALUES (gen_random_uuid(), :a, :b) RETURNING id", a=u["id"], b=ami["id"]))[0].id
        await _sql("INSERT INTO messages (id, thread_id, sender_id, content) VALUES "
                   "(gen_random_uuid(), :t, :a, 'bonjour')", t=th, a=ami["id"])
        h = await _h(client, u)
        r = await client.post("/reports", headers=h, json={
            "good_faith": True, "target_type": "track", "target_id": str(uuid.uuid4()),
            "reason": "spam_arnaque"})
        assert r.status_code == 201, r.text
        r = await client.get("/users/me/export", headers=h)
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        j = r.json()
        assert j["profile"]["email"] == u["email"]
        assert j["consentements"]["cgu"]["version_acceptee"] == CGU_VERSION
        assert any(o["title"] == "Mon œuvre" for o in j["oeuvres"]["recettes_et_images"])
        assert [m["content"] for m in j["messages"]] == ["bonjour"]
        assert j["messages"][0]["sens"] == "recu"
        assert len(j["signalements_faits"]) == 1
        assert len(j["abonnements"]["je_suis"]) == 1
        assert any(t["type"] == "bonus" for t in j["transactions"])
        for cle in ("achats", "ventes", "notifications", "parrainages", "echanges", "paiements_carte"):
            assert cle in j
        assert "password_hash" not in str(j)
    finally:
        await _cleanup(u["id"], ami["id"])


# ═══ 5. Mesure d'audience ═════════════════════════════════════════════════════

async def test_mesure_jamais_rattachee_au_compte(client):
    u = await _mk_user()
    sid = f"lotd-{uuid.uuid4().hex}"
    try:
        r = await client.post("/events", headers=await _h(client, u),
                              json={"session_id": sid, "events": [{"name": "page_view", "path": "/"}]})
        assert r.status_code == 202 and r.json()["accepted"] == 1
        rows = await _sql("SELECT user_id FROM analytics_events WHERE session_id = :s", s=sid)
        assert rows and all(x.user_id is None for x in rows)
        with pytest.raises(IntegrityError):
            await _sql("INSERT INTO analytics_events (id, session_id, user_id, name) "
                       "VALUES (gen_random_uuid(), :s, :u, 'visit')", s=sid, u=u["id"])
    finally:
        await _sql("DELETE FROM analytics_events WHERE session_id = :s", s=sid)
        await _cleanup(u["id"])


async def test_purge_mesure_13_mois(client):
    from app.services.analytics import purger_mesure_ancienne

    sid = f"lotd-purge-{uuid.uuid4().hex[:8]}"
    vieux = datetime.now(timezone.utc) - timedelta(days=13 * 31 + 5)
    recent = datetime.now(timezone.utc) - timedelta(days=12 * 30)
    await _sql("INSERT INTO analytics_events (id, session_id, name, created_at) VALUES "
               "(gen_random_uuid(), :s, 'visit', :v), (gen_random_uuid(), :s, 'visit', :r)",
               s=sid, v=vieux, r=recent)
    try:
        async with SessionLocal() as db:
            n = await purger_mesure_ancienne(db)
            await db.commit()
        assert n >= 1
        rows = await _sql("SELECT created_at FROM analytics_events WHERE session_id = :s", s=sid)
        assert len(rows) == 1 and rows[0].created_at > vieux
        admin = await _mk_user(official=True)
        lambda_ = await _mk_user()
        try:
            assert (await client.post("/admin/mesure/purge",
                                      headers=await _h(client, lambda_))).status_code == 403
            r = await client.post("/admin/mesure/purge", headers=await _h(client, admin))
            assert r.status_code == 200 and "supprimes" in r.json()
        finally:
            await _cleanup(admin["id"], lambda_["id"])
    finally:
        await _sql("DELETE FROM analytics_events WHERE session_id = :s", s=sid)


async def test_telemetry_ne_pose_rien_avant_accord():
    js = (REPO / "ui" / "core" / "telemetry.js").read_text()
    assert "var SID = _sid();" not in js
    assert "if (!_consented()) return null;" in js
    assert "Authorization" not in js  # jamais rattachée au compte
    assert "forget: forget" in js
    consent = (REPO / "ui" / "core" / "consent.js").read_text()
    assert "reopen:" in consent and "_oublier()" in consent


# ═══ 6. Emails en minuscules ══════════════════════════════════════════════════

async def test_emails_normalises_partout(client, monkeypatch):
    base = f"Pytest-LotD-{uuid.uuid4().hex[:8]}@SmylePlay.Example"
    r = await client.post("/auth/register", json={
        "email": f"  {base} ", "password": PWD, "accept_terms": True, "age_confirmed": True})
    assert r.status_code == 201, r.text
    uid = uuid.UUID(r.json()["id"])
    try:
        assert r.json()["email"] == base.lower()
        r = await client.post("/auth/register", json={
            "email": base.upper(), "password": PWD, "accept_terms": True, "age_confirmed": True})
        assert r.status_code == 409, r.text
        r = await client.post("/auth/login", json={"email": base.upper(), "password": PWD})
        assert r.status_code == 200, r.text

        envoyes = []

        async def _faux(to, *, link):
            envoyes.append(to)
            return True

        monkeypatch.setattr("app.services.emails.send_password_reset_email", _faux)
        monkeypatch.setattr("app.services.emails.send_verification_email", _faux)
        assert (await client.post("/auth/forgot-password", json={"email": f" {base.upper()}"})).status_code == 200
        assert (await client.post("/auth/resend-verification", json={"email": base.upper()})).status_code == 200
        assert envoyes == [base.lower(), base.lower()]

        with pytest.raises(IntegrityError):
            await _sql("INSERT INTO users (id, email, password_hash) VALUES (gen_random_uuid(), :e, 'x')",
                       e=base.upper())
    finally:
        await _sql("DELETE FROM password_reset_tokens WHERE user_id = :u", u=uid)
        await _cleanup(uid)


async def test_migration_emails_echoue_clairement_sur_doublon():
    chemin = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0103_emails_minuscules.py"
    spec = importlib.util.spec_from_file_location("m0103", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        await db.execute(text("DROP INDEX ux_users_email_lower"))
        await db.execute(text(
            "INSERT INTO users (id, email, password_hash) VALUES "
            "(gen_random_uuid(), :a, 'x'), (gen_random_uuid(), :b, 'x')"),
            {"a": f"dup-{tag}@ex.example", "b": f"Dup-{tag}@Ex.example"})
        with pytest.raises(DBAPIError) as exc:
            await db.execute(text(mod._CONTROLE))
        await db.rollback()  # l'index revient, les comptes de test disparaissent
    assert "Migration 0103 arrêtée" in str(exc.value)
    assert f"dup-{tag}@ex.example (2 comptes)" in str(exc.value)
    assert (await _sql("SELECT count(*) AS n FROM pg_indexes WHERE indexname = 'ux_users_email_lower'"))[0].n == 1


# ═══ 7. Pied de page légal ════════════════════════════════════════════════════

@pytest.mark.parametrize("page", [
    "o.html", "comment-ca-marche.html", "reset.html", "verifier-email.html", "oeuvre.html",
    "index.html", "dashboard.html", "library.html", "artiste.html", "mes-oeuvres.html",
    "offres.html", "tarifs.html",
])
async def test_pied_de_page_legal_present(page):
    assert "ui/core/legal-footer.js" in (REPO / page).read_text()


async def test_pied_de_page_legal_contenu():
    js = (REPO / "ui" / "core" / "legal-footer.js").read_text()
    for attendu in ("/legal#mentions", "/legal#cgu", "/legal#confidentialite",
                    "Cookies / mesure d’audience", "Contact", "SmyleConsent.reopen"):
        assert attendu in js, attendu
