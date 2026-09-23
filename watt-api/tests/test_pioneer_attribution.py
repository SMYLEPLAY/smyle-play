"""Programme PIONNIER — attribution des rangs (Brique 2, décision Tom 23/09).

Pionnier = les 100 premiers créateurs qui PUBLIENT une œuvre. Rang figé à vie.
Couvre : éligibilité et exclusions ; attribution idempotente plafonnée à 100 ;
DEUX tests de concurrence (rangs distincts sous publications simultanées, et
dernière place attribuée une seule fois) ; attribution EN DIRECT par la chaîne
réelle (dépendance get_db, et vraie requête HTTP de publication) ; règle email ;
rattrapage admin en deux temps (aperçu sans écriture / confirmation) ; compteur
public ; garde du taux Pionnier derrière FEATURE_PIONEER.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import artist_pct_for_user
from app.services.moderation import takedown_content
from app.services.pioneer import (
    PIONEER_SLOTS,
    PioneerRetroConflict,
    award_pioneer,
    is_eligible,
    pioneer_stats,
    retro_candidates,
    retro_confirm,
)
from app.services.users import create_user


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _user(**flags) -> uuid.UUID:
    email = f"pytest-pio2-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    if flags:
        sets = ", ".join(f"{k} = :{k}" for k in flags)
        async with SessionLocal() as db:
            await db.execute(text(f"UPDATE users SET {sets} WHERE id = :u"), {**flags, "u": uid})
            await db.commit()
    return uid


async def _oeuvre(uid, *, published=True, created_at=None) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=uid, title=f"P {uuid.uuid4().hex[:8]}", description="Tagline",
            prompt_text="X" * 100, price_credits=10, is_published=published,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        pid = p.id
        if created_at is not None:
            await db.execute(text("UPDATE prompts SET created_at = :c WHERE id = :i"),
                             {"c": created_at, "i": pid})
            await db.commit()
    return pid


async def _createur(**flags) -> uuid.UUID:
    uid = await _user(**flags)
    await _oeuvre(uid)
    return uid


async def _rang(uid):
    async with SessionLocal() as db:
        r = (await db.execute(
            text("SELECT pioneer_rank, is_pioneer, pioneer_excluded FROM users WHERE id = :u"),
            {"u": uid},
        )).first()
    return r


async def _award(uid, live=True):
    async with SessionLocal() as db:
        rang = await award_pioneer(db, uid, live=live)
        await db.commit()
    return rang


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _prefill(jusqua: int) -> str:
    """Remplit des rangs factices jusqu'à `jusqua` inclus. Renvoie une étiquette
    de nettoyage."""
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        base = int((await db.execute(
            text("SELECT COALESCE(MAX(pioneer_rank), 0) FROM users")
        )).scalar_one())
        if base < jusqua:
            await db.execute(
                text(
                    "INSERT INTO users (id, email, is_pioneer, pioneer_rank) "
                    "SELECT gen_random_uuid(), 'pytest-pfill-' || g || '-' || :t "
                    "|| '@smyleplay.example', TRUE, g FROM generate_series(CAST(:a AS int), CAST(:b AS int)) g"
                ),
                {"t": tag, "a": base + 1, "b": jusqua},
            )
            await db.commit()
    return tag


async def _cleanup_prefill(tag):
    async with SessionLocal() as db:
        await db.execute(text("DELETE FROM users WHERE email LIKE :p"),
                         {"p": f"pytest-pfill-%-{tag}@smyleplay.example"})
        await db.commit()


# ─── 1. Éligibilité & exclusions ──────────────────────────────────────────────

async def test_eligible_avec_une_oeuvre_en_ligne():
    uid = await _createur()
    try:
        async with SessionLocal() as db:
            assert await is_eligible(db, uid, live=True) is True
    finally:
        await _cleanup(uid)


async def test_brouillon_ne_qualifie_pas():
    uid = await _user()
    await _oeuvre(uid, published=False)
    try:
        async with SessionLocal() as db:
            assert await is_eligible(db, uid, live=True) is False
    finally:
        await _cleanup(uid)


async def test_oeuvre_retiree_par_la_moderation_ne_qualifie_pas():
    """Anti-squat : seule une œuvre ACTUELLEMENT en ligne compte."""
    uid = await _user()
    pid = await _oeuvre(uid)
    try:
        async with SessionLocal() as db:
            out = await takedown_content(db, "prompt", str(pid))
            await db.commit()
        assert out["ok"]
        async with SessionLocal() as db:
            assert await is_eligible(db, uid, live=True) is False
    finally:
        await _cleanup(uid)


@pytest.mark.parametrize(
    "flags",
    [
        {"is_admin": True},
        {"is_banned": True},
        {"pioneer_excluded": True},
    ],
)
async def test_exclusions_automatiques_comptes(flags):
    uid = await _createur(**flags)
    try:
        async with SessionLocal() as db:
            assert await is_eligible(db, uid, live=True) is False
            assert await is_eligible(db, uid, live=False) is False
    finally:
        await _cleanup(uid)


async def test_compte_supprime_exclu():
    uid = await _createur()
    try:
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET email = :e WHERE id = :u"),
                             {"e": f"deleted-{uid}@deleted.watt", "u": uid})
            await db.commit()
            assert await is_eligible(db, uid, live=False) is False
    finally:
        await _cleanup(uid)


@pytest.mark.parametrize("drapeau", ["is_treasury", "is_official"])
async def test_tresorerie_et_vitrine_exclus(drapeau):
    """Les comptes société (trésorerie) et vitrine « Smyle » ne prennent pas
    de place, même s'ils ont une œuvre en ligne."""
    async with SessionLocal() as db:
        uid = (await db.execute(text(f"SELECT id FROM users WHERE {drapeau} LIMIT 1"))).scalar_one()
    pid = await _oeuvre(uid)
    try:
        async with SessionLocal() as db:
            assert await is_eligible(db, uid, live=False) is False
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Prompt).where(Prompt.id == pid))
            await db.commit()


# ─── 2. Attribution ───────────────────────────────────────────────────────────

async def test_attribution_rang_suivant_idempotente():
    uid = await _createur()
    try:
        async with SessionLocal() as db:
            base = int((await db.execute(
                text("SELECT COALESCE(MAX(pioneer_rank), 0) FROM users"))).scalar_one())
        rang = await _award(uid)
        assert rang == base + 1
        assert await _award(uid) == rang          # 2e appel : même rang, rien de neuf
        r = await _rang(uid)
        assert r.pioneer_rank == rang and r.is_pioneer is True
    finally:
        await _cleanup(uid)


async def test_plus_aucune_place_au_dela_de_100():
    tag = await _prefill(PIONEER_SLOTS)
    uid = await _createur()
    try:
        assert await _award(uid) is None
        assert (await _rang(uid)).pioneer_rank is None
        async with SessionLocal() as db:
            assert (await pioneer_stats(db))["restantes"] == 0
    finally:
        await _cleanup(uid)
        await _cleanup_prefill(tag)


# ─── 3. CONCURRENCE ───────────────────────────────────────────────────────────

async def test_concurrence_publications_simultanees_rangs_distincts():
    """10 créateurs publient au même instant : 10 rangs DISTINCTS et
    CONSÉCUTIFS, aucun doublon (verrou applicatif + UNIQUE en filet)."""
    uids = [await _createur() for _ in range(10)]
    try:
        async with SessionLocal() as db:
            base = int((await db.execute(
                text("SELECT COALESCE(MAX(pioneer_rank), 0) FROM users"))).scalar_one())
        rangs = await asyncio.wait_for(
            asyncio.gather(*(_award(u) for u in uids)), timeout=60)
        assert None not in rangs
        assert sorted(rangs) == list(range(base + 1, base + 11))
        assert len(set(rangs)) == 10
    finally:
        await _cleanup(*uids)


async def test_concurrence_derniere_place_attribuee_une_seule_fois():
    """99 rangs pris, 5 créateurs publient simultanément : EXACTEMENT un reçoit
    le rang 100, les autres rien. Jamais de 101, jamais de doublon."""
    tag = await _prefill(PIONEER_SLOTS - 1)
    uids = [await _createur() for _ in range(5)]
    try:
        rangs = await asyncio.wait_for(
            asyncio.gather(*(_award(u) for u in uids)), timeout=60)
        gagnants = [r for r in rangs if r is not None]
        assert gagnants == [PIONEER_SLOTS]
        async with SessionLocal() as db:
            n = (await db.execute(
                text("SELECT count(*) FROM users WHERE pioneer_rank IS NOT NULL"))).scalar_one()
            mx = (await db.execute(text("SELECT MAX(pioneer_rank) FROM users"))).scalar_one()
        assert int(n) == PIONEER_SLOTS and int(mx) == PIONEER_SLOTS
    finally:
        await _cleanup(*uids)
        await _cleanup_prefill(tag)


# ─── 4. EN DIRECT (chaîne réelle) ─────────────────────────────────────────────

async def _publier_via_get_db(uid):
    """Reproduit exactement ce que fait FastAPI : ouvre la session par la
    dépendance get_db, publie, commit, puis termine la dépendance."""
    gen = get_db()
    db = await gen.__anext__()
    db.add(Prompt(artist_id=uid, title="Direct", description="Tagline",
                  prompt_text="X" * 100, price_credits=10, is_published=True))
    await db.commit()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


async def test_direct_flag_on_rang_a_la_premiere_publication(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    uid = await _user()
    try:
        assert (await _rang(uid)).pioneer_rank is None
        await _publier_via_get_db(uid)
        assert (await _rang(uid)).pioneer_rank is not None
    finally:
        await _cleanup(uid)


async def test_direct_flag_off_aucune_attribution(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", False)
    uid = await _user()
    try:
        await _publier_via_get_db(uid)
        assert (await _rang(uid)).pioneer_rank is None
    finally:
        await _cleanup(uid)


async def test_direct_via_vraie_requete_de_publication(client, test_user, auth_headers, monkeypatch):
    """Bout en bout : publication d'un morceau par l'API (POST /tracks/) →
    le créateur reçoit son rang à la fin de la requête."""
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    async with SessionLocal() as db:  # porte « profil publié » de POST /tracks
        await db.execute(text("UPDATE users SET profile_public = TRUE WHERE id = :u"),
                         {"u": test_user["id"]})
        await db.commit()
    r = await client.post("/tracks/", headers=auth_headers,
                          json={"title": "Premier son", "full_prompt": "deep house"})
    assert r.status_code == 201, r.text
    assert (await _rang(test_user["id"])).pioneer_rank is not None


async def test_direct_email_exige_seulement_si_verification_active(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFIED", True)
    non_verifie = await _createur(email_verified=False)
    verifie = await _createur(email_verified=True)
    try:
        assert await _award(non_verifie, live=True) is None
        assert await _award(verifie, live=True) is not None
        # Au rattrapage, l'email n'est jamais exigé.
        assert await _award(non_verifie, live=False) is not None
    finally:
        await _cleanup(non_verifie, verifie)


# ─── 5. RATTRAPAGE admin en deux temps ────────────────────────────────────────

async def test_retro_apercu_ordonne_et_sans_ecriture():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a, b, c = await _user(), await _user(), await _user()
    await _oeuvre(b, created_at=t0)                        # le plus ancien
    await _oeuvre(c, created_at=t0 + timedelta(days=1))
    await _oeuvre(a, created_at=t0 + timedelta(days=2))
    try:
        async with SessionLocal() as db:
            cands = await retro_candidates(db)
        ids = [x["user_id"] for x in cands]
        mine = [i for i in ids if i in {str(a), str(b), str(c)}]
        assert mine == [str(b), str(c), str(a)]           # ordre de 1re œuvre
        # Rangs proposés consécutifs, email jamais en clair.
        assert all("@" in (x["email_masque"] or "@") and "***" in (x["email_masque"] or "***")
                   for x in cands)
        for u in (a, b, c):
            assert (await _rang(u)).pioneer_rank is None   # RIEN n'a été écrit
    finally:
        await _cleanup(a, b, c)


async def test_retro_confirme_ecrit_et_persiste_l_exclusion(monkeypatch):
    a, test_de_tom = await _createur(), await _createur()
    attribues = []
    try:
        async with SessionLocal() as db:
            apercu = await retro_candidates(db, [test_de_tom])
        attendu = [uuid.UUID(x["user_id"]) for x in apercu]
        assert test_de_tom not in attendu and a in attendu
        async with SessionLocal() as db:
            out = await retro_confirm(db, exclude_ids=[test_de_tom], expected_user_ids=attendu)
            await db.commit()
        attribues = [uuid.UUID(x["user_id"]) for x in out["attribues"]]
        assert a in attribues
        assert (await _rang(a)).pioneer_rank is not None
        # Exclusion PERSISTÉE : le compte de test ne prend jamais de place,
        # même en direct plus tard.
        assert (await _rang(test_de_tom)).pioneer_excluded is True
        monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
        assert await _award(test_de_tom, live=True) is None
    finally:
        await _cleanup(a, test_de_tom)
        await _reset(attribues)


async def _reset(uids):
    if not uids:
        return
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET pioneer_rank = NULL, is_pioneer = FALSE, "
                 "pioneer_awarded_at = NULL WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": list(uids)},
        )
        await db.commit()


async def test_retro_conflit_si_la_liste_a_change():
    a = await _createur()
    try:
        async with SessionLocal() as db:
            attendu = [uuid.UUID(x["user_id"]) for x in await retro_candidates(db)]
        nouveau = await _createur()                       # publie entre-temps
        try:
            with pytest.raises(PioneerRetroConflict):
                async with SessionLocal() as db:
                    await retro_confirm(db, exclude_ids=[], expected_user_ids=attendu)
            assert (await _rang(a)).pioneer_rank is None   # rien d'écrit
        finally:
            await _cleanup(nouveau)
    finally:
        await _cleanup(a)


async def test_retro_double_confirmation_idempotente():
    a = await _createur()
    attribues = []
    try:
        async with SessionLocal() as db:
            attendu = [uuid.UUID(x["user_id"]) for x in await retro_candidates(db)]
        async with SessionLocal() as db:
            out1 = await retro_confirm(db, exclude_ids=[], expected_user_ids=attendu)
            await db.commit()
        attribues = [uuid.UUID(x["user_id"]) for x in out1["attribues"]]
        rang = (await _rang(a)).pioneer_rank
        async with SessionLocal() as db:                  # 2e clic, même liste
            out2 = await retro_confirm(db, exclude_ids=[], expected_user_ids=attendu)
            await db.commit()
        assert out2["deja_applique"] is True and out2["attribues"] == []
        assert (await _rang(a)).pioneer_rank == rang       # rang figé, inchangé
    finally:
        await _cleanup(a)
        await _reset(attribues)


async def test_endpoints_admin_apercu_et_confirmation(client, test_user, auth_headers):
    a = await _createur()
    attribues = []
    try:
        # Non admin -> refusé.
        r = await client.post("/admin/pioneer/retro/preview", headers=auth_headers, json={})
        assert r.status_code == 403
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :u"),
                             {"u": test_user["id"]})
            await db.commit()
        r = await client.post("/admin/pioneer/retro/preview", headers=auth_headers, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ecrit"] is False
        attendu = [x["user_id"] for x in body["candidats"]]
        assert str(a) in attendu
        r = await client.post("/admin/pioneer/retro/confirm", headers=auth_headers,
                              json={"exclude_ids": [], "expected_user_ids": attendu})
        assert r.status_code == 200, r.text
        attribues = [uuid.UUID(x["user_id"]) for x in r.json()["attribues"]]
        assert (await _rang(a)).pioneer_rank is not None
        # Liste périmée -> 409.
        r = await client.post("/admin/pioneer/retro/confirm", headers=auth_headers,
                              json={"exclude_ids": [], "expected_user_ids": [str(uuid.uuid4())]})
        assert r.status_code == 409
    finally:
        await _cleanup(a)
        await _reset(attribues)


# ─── 6. Compteur public & garde du taux ───────────────────────────────────────

async def test_compteur_public_404_si_flag_off(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", False)
    r = await client.get("/pioneer/places")
    assert r.status_code == 404


async def test_compteur_public_si_flag_on(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    r = await client.get("/pioneer/places")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == PIONEER_SLOTS
    assert d["attribuees"] + d["restantes"] == PIONEER_SLOTS


async def test_taux_pionnier_inactif_tant_que_le_programme_est_off(monkeypatch):
    """Un rang posé au rattrapage (flag OFF) ne change PAS encore le taux :
    aucun effet argent avant l'activation."""
    uid = await _createur()
    try:
        await _award(uid, live=False)
        async with SessionLocal() as db:
            monkeypatch.setattr(settings, "FEATURE_PIONEER", False)
            assert await artist_pct_for_user(db, uid) == 80   # standard : 20 %
            monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
            assert await artist_pct_for_user(db, uid) == 90   # pionnier : 10 %
    finally:
        await _cleanup(uid)
