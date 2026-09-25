"""Mesures « Prêt à sortir » — Lot 2.

Couvre :
  - activité par jour : écrite par toute requête connectée, AU PLUS une fois
    par jour et par compte, hors du chemin de la requête ; « écouter en étant
    connecté » pose le drapeau `listened` (l'écoute reste anonyme) ;
  - définitions : actif (vérifié ou compte antérieur à la vérification + une
    action réelle sur 30 jours), créateur actif, stock tirable, signalements
    (médiane + en retard > 48 h), rétention à 7 jours par cohorte ;
  - page admin : réservée à l'administration, une ligne par sortie M1…M6,
    feu + fiabilité, chiffres tirés de la base.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import activity
from app.services.launch_readiness import (
    _actifs,
    _debut_verification,
    _feu,
    _retention_j7,
    _signalements,
    _stock_tirable,
    readiness,
)
from app.services.moderation import takedown_content
from app.services.users import create_user


async def _user(**flags) -> uuid.UUID:
    async with SessionLocal() as db:
        uid = (await create_user(db, UserCreate(
            email=f"pytest-act-{uuid.uuid4().hex[:10]}@smyleplay.example", password="12345678"))).id
    if flags:
        sets = ", ".join(f"{k} = :{k}" for k in flags)
        async with SessionLocal() as db:
            await db.execute(text(f"UPDATE users SET {sets} WHERE id = :u"), {**flags, "u": uid})
            await db.commit()
    return uid


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(Prompt).where(Prompt.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _jours(uid):
    async with SessionLocal() as db:
        return (await db.execute(text(
            "SELECT day, listened FROM user_activity_days WHERE user_id = :u ORDER BY day"),
            {"u": uid})).all()


# ─── 1. Activité par jour ─────────────────────────────────────────────────────

async def test_requete_connectee_ecrit_une_seule_ligne_par_jour(client, test_user, auth_headers):
    activity.reset_cache()
    for _ in range(3):
        r = await client.get("/users/me", headers=auth_headers)
        assert r.status_code == 200
    await activity.drain()
    rows = await _jours(test_user["id"])
    assert len(rows) == 1
    assert rows[0].day == datetime.now(timezone.utc).date() and rows[0].listened is False


async def test_ecriture_hors_du_chemin_de_la_requete():
    """note_activity ne fait AUCUN appel base dans la requête : il programme
    une tâche, et ne programme rien pour un compte déjà noté aujourd'hui."""
    activity.reset_cache()
    uid = uuid.uuid4()                            # compte inexistant : l'écriture échoue…
    activity.note_activity(uid)
    assert len(activity._tasks) == 1
    activity.note_activity(uid)                   # déjà noté → rien de plus
    assert len(activity._tasks) == 1
    await activity.drain()                        # … sans jamais lever
    activity.note_activity(None)                  # visiteur anonyme → rien
    assert not activity._tasks


async def test_ecoute_connectee_pose_le_drapeau(client, test_user, auth_headers):
    activity.reset_cache()
    async with SessionLocal() as db:
        t = Track(artist_id=test_user["id"], title="Écoute test")
        db.add(t)
        await db.commit()
        tid = t.id
    try:
        await client.post(f"/watt/plays/{tid}")                         # anonyme
        await activity.drain()
        assert await _jours(test_user["id"]) == []
        await client.post(f"/watt/plays/{tid}", headers=auth_headers)   # connecté
        await activity.drain()
        rows = await _jours(test_user["id"])
        assert len(rows) == 1 and rows[0].listened is True
        # L'écoute reste anonyme : play_events n'a pas de colonne utilisateur.
        async with SessionLocal() as db:
            cols = (await db.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'play_events'"
            ))).scalars().all()
        assert "user_id" not in cols
    finally:
        async with SessionLocal() as db:
            await db.execute(text("DELETE FROM play_events WHERE track_id = :t"), {"t": tid})
            await db.execute(delete(Track).where(Track.id == tid))
            await db.commit()


# ─── 2. Définitions ───────────────────────────────────────────────────────────

async def test_actif_exige_verification_ou_compte_anterieur():
    # Pose une date de mise en place de la vérification (si aucune n'existe).
    temoin = await _user()
    async with SessionLocal() as db:
        await db.execute(text(
            "INSERT INTO email_verification_tokens (id, user_id, token_hash, created_at, expires_at) "
            "VALUES (gen_random_uuid(), :u, :h, now() - interval '1 hour', now() + interval '1 day')"),
            {"u": temoin, "h": uuid.uuid4().hex})
        await db.commit()
    non_verifie = await _user()
    verifie = await _user(email_verified=True)
    ancien = await _user()
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET created_at = now() - interval '400 days' WHERE id = :u"),
                         {"u": ancien})
        await db.commit()
    try:
        async with SessionLocal() as db:
            debut = await _debut_verification(db)
            avant = (await _actifs(db, debut))["actifs"]
        async with SessionLocal() as db:
            for uid in (non_verifie, verifie, ancien):
                db.add(Prompt(artist_id=uid, title="Publication test", description="Tagline",
                              prompt_text="X" * 100, price_credits=10, is_published=True))
            await db.commit()
        async with SessionLocal() as db:
            apres = (await _actifs(db, debut))["actifs"]
        # +2 : le vérifié et l'ancien compte ; pas le compte récent non vérifié.
        assert apres - avant == 2
    finally:
        await _cleanup(temoin, non_verifie, verifie, ancien)


async def test_ecouter_et_suivre_sont_des_actions_d_actif():
    a, b = await _user(email_verified=True), await _user(email_verified=True)
    try:
        async with SessionLocal() as db:
            debut = await _debut_verification(db)
            avant = (await _actifs(db, debut))
        async with SessionLocal() as db:
            await activity.record_activity(a, listened=True)
            await db.execute(text(
                "INSERT INTO user_follows (id, follower_id, followee_id) "
                "VALUES (gen_random_uuid(), :f, :e)"), {"f": b, "e": a})
            await db.commit()
        async with SessionLocal() as db:
            apres = (await _actifs(db, debut))
        assert apres["actifs"] - avant["actifs"] == 2
        assert apres["abonnements"] - avant["abonnements"] == 1
    finally:
        await _cleanup(a, b)


async def test_simple_visite_n_est_pas_une_action():
    uid = await _user(email_verified=True)
    try:
        async with SessionLocal() as db:
            debut = await _debut_verification(db)
            avant = (await _actifs(db, debut))["actifs"]
        await activity.record_activity(uid)          # vu connecté, sans action
        async with SessionLocal() as db:
            assert (await _actifs(db, debut))["actifs"] == avant
    finally:
        await _cleanup(uid)


async def test_stock_tirable_exclut_les_oeuvres_retirees():
    uid = await _user()
    try:
        async with SessionLocal() as db:
            avant = await _stock_tirable(db)
            p = Prompt(artist_id=uid, title="Tirable test", description="Tagline",
                       prompt_text="X" * 100, price_credits=10, is_published=True)
            db.add(p)
            await db.commit()
            pid = p.id
        async with SessionLocal() as db:
            assert await _stock_tirable(db) == avant + 1
            await takedown_content(db, "prompt", str(pid), "test")
            await db.commit()
        async with SessionLocal() as db:
            assert await _stock_tirable(db) == avant
    finally:
        await _cleanup(uid)


async def test_signalements_en_retard():
    async with SessionLocal() as db:
        avant = await _signalements(db)
        rid = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO content_reports (id, target_type, target_id, reason, detail, status, created_at) "
            "VALUES (:i, 'track', :t, 'autre', 'test', 'new', now() - interval '3 days')"),
            {"i": rid, "t": str(uuid.uuid4())})
        await db.commit()
    try:
        async with SessionLocal() as db:
            apres = await _signalements(db)
        assert apres["ouverts_plus_48h"] == avant["ouverts_plus_48h"] + 1
    finally:
        async with SessionLocal() as db:
            await db.execute(text("DELETE FROM content_reports WHERE id = :i"), {"i": rid})
            await db.commit()


async def test_retention_par_cohorte():
    j0 = datetime.now(timezone.utc) - timedelta(days=20)
    revenu, parti, temoin = await _user(), await _user(), await _user()
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET created_at = :c WHERE id = ANY(CAST(:i AS uuid[]))"),
                         {"c": j0, "i": [revenu, parti]})
        # Le suivi d'activité couvre la fenêtre J7–J13 de la cohorte.
        await db.execute(text("INSERT INTO user_activity_days (user_id, day) VALUES (:u, :d) "
                              "ON CONFLICT DO NOTHING"), {"u": temoin, "d": j0.date()})
        await db.execute(text("INSERT INTO user_activity_days (user_id, day) VALUES (:u, :d)"),
                         {"u": revenu, "d": j0.date() + timedelta(days=8)})
        await db.commit()
    try:
        async with SessionLocal() as db:
            ret = await _retention_j7(db)
        semaine = (j0.date() - timedelta(days=j0.date().weekday())).isoformat()
        c = [x for x in ret["cohortes"] if x["semaine"] == semaine]
        assert c and c[0]["inscrits"] >= 2 and c[0]["revenus"] >= 1
        assert ret["valeur"] is not None
    finally:
        await _cleanup(revenu, parti, temoin)


async def test_feux():
    def c(atteint, prog):
        return {"atteint": atteint, "progression": prog}
    assert _feu([c(True, 1.0), c(True, 1.0)], "et") == "vert"
    assert _feu([c(True, 1.0), c(False, 0.8)], "et") == "orange"
    assert _feu([c(True, 1.0), c(False, 0.2)], "et") == "rouge"
    assert _feu([c(False, 0.1), c(True, 1.0)], "ou") == "vert"
    assert _feu([c(False, 0.1), c(None, None)], "ou") == "orange"   # info manquante
    assert _feu([c(False, 0.1), c(False, 0.3)], "ou") == "rouge"


# ─── 3. Page admin ────────────────────────────────────────────────────────────

async def test_pret_a_sortir_reserve_admin_et_complet(client, test_user, auth_headers):
    r = await client.get("/admin/pret-a-sortir", headers=auth_headers)
    assert r.status_code == 403
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :u"), {"u": test_user["id"]})
        await db.commit()
    r = await client.get("/admin/pret-a-sortir", headers=auth_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [s["mois"] for s in d["sorties"]] == ["M1", "M2", "M3", "M4", "M5", "M6"]
    for s in d["sorties"]:
        assert s["feu"] in ("vert", "orange", "rouge")
        assert s["fiabilite"] in ("fiable", "partielle")
        for c in s["criteres"]:
            assert c["fiabilite"] in ("fiable", "partielle") and c["critere"] and c["cible"]
    assert "télémétrie" in d["source"]
    # M6 : le juridique ne se mesure pas → jamais vert sans Tom.
    assert d["sorties"][5]["feu"] != "vert"
    # La page HTML est servie (données chargées côté navigateur, admin seulement).
    assert (await client.get("/pret-a-sortir")).status_code == 200


async def test_readiness_ne_lit_pas_la_telemetrie():
    """Ajouter des événements de télémétrie ne change AUCUN chiffre."""
    async with SessionLocal() as db:
        avant = (await readiness(db))["chiffres"]
        await db.execute(text(
            "INSERT INTO analytics_events (id, session_id, name) "
            "SELECT gen_random_uuid(), 'pytest-' || g, 'visit' FROM generate_series(1, 20) g"))
        await db.commit()
    try:
        async with SessionLocal() as db:
            apres = (await readiness(db))["chiffres"]
        for k in ("actifs", "createurs_actifs", "deblocages_cumules", "stock_tirable"):
            assert apres[k] == avant[k], k
    finally:
        async with SessionLocal() as db:
            await db.execute(text("DELETE FROM analytics_events WHERE session_id LIKE 'pytest-%'"))
            await db.commit()
