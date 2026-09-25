"""Anti-squat PIONNIER — Lot 2 (décision Tom : « à vie, sauf fraude »).

Couvre :
  - retrait par la modération des ADN, ADN visuels et voix (en plus des
    prompts / images / morceaux) ; un contenu retiré RESTE caché même si le
    créateur tente de le republier (trigger 0092) et ne qualifie plus personne ;
  - révocation d'un rang par un admin : motif obligatoire, journal, compte
    exclu à vie, place REMISE EN JEU au prochain éligible ;
  - pas de doublon, jamais plus de 100 rangs, y compris en CONCURRENCE avec
    des attributions directes ;
  - numéros libres : après une révocation, l'attribution prend le trou.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.adn import Adn
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.models.visual_adn import VisualAdn
from app.models.voice import Voice
from app.schemas.user import UserCreate
from app.services.moderation import takedown_content
from app.services.pioneer import (
    PIONEER_SLOTS,
    PioneerNotHeld,
    award_pioneer,
    is_eligible,
    revoke_pioneer,
)
from app.services.users import create_user

# Date de première œuvre très ancienne : garantit que le candidat du test est
# le PREMIER de la file de réattribution, quel que soit l'état de la base.
_TRES_ANCIEN = datetime(2000, 1, 1, tzinfo=timezone.utc)


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _user(**flags) -> uuid.UUID:
    email = f"pytest-pio3-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    if flags:
        sets = ", ".join(f"{k} = :{k}" for k in flags)
        async with SessionLocal() as db:
            await db.execute(text(f"UPDATE users SET {sets} WHERE id = :u"), {**flags, "u": uid})
            await db.commit()
    return uid


async def _oeuvre(uid, *, created_at=None) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title=f"P {uuid.uuid4().hex[:8]}", description="Tagline",
                   prompt_text="X" * 100, price_credits=10, is_published=True)
        db.add(p)
        await db.commit()
        await db.refresh(p)
        pid = p.id
        if created_at is not None:
            await db.execute(text("UPDATE prompts SET created_at = :c WHERE id = :i"),
                             {"c": created_at, "i": pid})
            await db.commit()
    return pid


async def _createur(created_at=None, **flags) -> uuid.UUID:
    uid = await _user(**flags)
    await _oeuvre(uid, created_at=created_at)
    return uid


async def _rang(uid):
    async with SessionLocal() as db:
        return (await db.execute(
            text("SELECT pioneer_rank, is_pioneer, pioneer_excluded FROM users WHERE id = :u"),
            {"u": uid},
        )).first()


async def _award(uid, live=True):
    async with SessionLocal() as db:
        rang = await award_pioneer(db, uid, live=live)
        await db.commit()
    return rang


async def _revoke(uid, reason="Squat : œuvres bâclées publiées pour prendre une place"):
    async with SessionLocal() as db:
        out = await revoke_pioneer(db, user_id=uid, reason=reason, revoked_by=None)
        await db.commit()
    return out


async def _cleanup(*uids):
    async with SessionLocal() as db:
        await db.execute(text("DELETE FROM pioneer_revocations WHERE user_id = ANY(CAST(:i AS uuid[])) "
                              "OR reassigned_to = ANY(CAST(:i AS uuid[]))"), {"i": list(uids)})
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _prefill_sauf(libre_max: int) -> str:
    """Pose des rangs factices sur TOUS les numéros libres de 1..libre_max."""
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, is_pioneer, pioneer_rank) "
                "SELECT gen_random_uuid(), 'pytest-pfill3-' || g || '-' || :t "
                "|| '@smyleplay.example', TRUE, g FROM generate_series(1, CAST(:b AS int)) g "
                "WHERE NOT EXISTS (SELECT 1 FROM users WHERE pioneer_rank = g)"
            ),
            {"t": tag, "b": libre_max},
        )
        await db.commit()
    return tag


async def _cleanup_prefill(tag):
    async with SessionLocal() as db:
        await db.execute(text("DELETE FROM users WHERE email LIKE :p"),
                         {"p": f"pytest-pfill3-%-{tag}@smyleplay.example"})
        await db.commit()


async def _etat_rangs():
    async with SessionLocal() as db:
        r = (await db.execute(text(
            "SELECT count(*) AS n, count(DISTINCT pioneer_rank) AS d, "
            "COALESCE(MAX(pioneer_rank), 0) AS mx FROM users WHERE pioneer_rank IS NOT NULL"
        ))).first()
    return int(r.n), int(r.d), int(r.mx)


# ─── 1. Retrait des ADN, ADN visuels, voix ────────────────────────────────────

async def _adn(uid):
    async with SessionLocal() as db:
        o = Adn(artist_id=uid, description="D" * 200, price_credits=50, is_published=True)
        db.add(o)
        await db.commit()
        return o.id


async def _visual_adn(uid):
    async with SessionLocal() as db:
        o = VisualAdn(artist_id=uid, description="V" * 200, price_credits=50, is_published=True)
        db.add(o)
        await db.commit()
        return o.id


async def _voix(uid):
    async with SessionLocal() as db:
        o = Voice(artist_id=uid, name="Voix test", style="soul", genres=["soul"],
                  sample_url="https://example.invalid/s.mp3", license="personnel",
                  price_credits=100, is_published=True)
        db.add(o)
        await db.commit()
        return o.id


@pytest.mark.parametrize(
    "ttype, fabrique, modele",
    [("adn", _adn, Adn), ("visual_adn", _visual_adn, VisualAdn), ("voix", _voix, Voice)],
)
async def test_retrait_adn_adn_visuel_voix(ttype, fabrique, modele):
    uid = await _user()
    oid = await fabrique(uid)
    try:
        async with SessionLocal() as db:
            assert await is_eligible(db, uid, live=False) is True   # qualifie avant
            out = await takedown_content(db, ttype, str(oid), "squat")
            await db.commit()
        assert out["ok"], out
        async with SessionLocal() as db:
            o = await db.get(modele, oid)
            assert o.is_published is False and o.taken_down_at is not None
            assert await is_eligible(db, uid, live=False) is False  # ne qualifie plus
    finally:
        await _cleanup(uid)


async def test_contenu_retire_ne_peut_pas_etre_republie():
    """Le créateur republie (n'importe quel chemin d'écriture) : le trigger
    0092 maintient le contenu caché, il ne requalifie pas."""
    uid = await _user()
    pid = await _oeuvre(uid)
    try:
        async with SessionLocal() as db:
            await takedown_content(db, "prompt", str(pid), "squat")
            await db.commit()
        async with SessionLocal() as db:
            p = await db.get(Prompt, pid)
            p.is_published = True                  # tentative de republication
            await db.commit()
        async with SessionLocal() as db:
            p = await db.get(Prompt, pid)
            assert p.is_published is False
            assert await is_eligible(db, uid, live=False) is False
    finally:
        await _cleanup(uid)


async def test_morceau_retire_reste_supprime():
    uid = await _user()
    async with SessionLocal() as db:
        t = Track(artist_id=uid, title="Son retiré")
        db.add(t)
        await db.commit()
        tid = t.id
    try:
        async with SessionLocal() as db:
            await takedown_content(db, "track", str(tid), "squat")
            await db.commit()
        async with SessionLocal() as db:
            t = await db.get(Track, tid)
            t.is_deleted = False                   # tentative de restauration
            await db.commit()
        async with SessionLocal() as db:
            assert (await db.get(Track, tid)).is_deleted is True
    finally:
        await _cleanup(uid)


async def test_retrait_direct_admin_adn(client, test_user, auth_headers):
    uid = await _user()
    oid = await _adn(uid)
    try:
        body = {"target_type": "adn", "target_id": str(oid), "reason": "Squat Pionnier"}
        r = await client.post("/admin/moderation/takedown", headers=auth_headers, json=body)
        assert r.status_code == 403                       # pas officiel
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET is_official = TRUE WHERE id = :u"),
                             {"u": test_user["id"]})
            await db.commit()
        r = await client.post("/admin/moderation/takedown", headers=auth_headers,
                              json={**body, "reason": ""})
        assert r.status_code == 422                       # motif obligatoire
        r = await client.post("/admin/moderation/takedown", headers=auth_headers, json=body)
        assert r.status_code == 200, r.text
        async with SessionLocal() as db:
            assert (await db.get(Adn, oid)).taken_down_at is not None
    finally:
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET is_official = FALSE WHERE id = :u"),
                             {"u": test_user["id"]})
            await db.commit()
        await _cleanup(uid)


async def test_signalement_accepte_les_adn_et_voix(client):
    for ttype in ("adn", "visual_adn", "voix"):
        r = await client.post("/reports", json={
            "target_type": ttype, "target_id": str(uuid.uuid4()), "reason": "spam_arnaque",
            "detail": "Œuvres bâclées publiées en rafale",
        })
        assert r.status_code in (200, 201), (ttype, r.status_code, r.text)
    async with SessionLocal() as db:
        await db.execute(text("DELETE FROM content_reports WHERE target_type IN ('adn','visual_adn','voix')"))
        await db.commit()


# ─── 2. Révocation + remise en jeu ────────────────────────────────────────────

async def test_revocation_journalisee_et_place_reattribuee():
    squatteur = await _createur()
    suivant = await _createur(created_at=_TRES_ANCIEN)   # 1er de la file
    try:
        rang = await _award(squatteur, live=False)
        assert rang is not None
        out = await _revoke(squatteur)
        assert out["revoque"]["rang"] == rang
        # Le squatteur perd son rang ET est exclu à vie.
        r = await _rang(squatteur)
        assert r.pioneer_rank is None and r.is_pioneer is False and r.pioneer_excluded is True
        assert await _award(squatteur, live=False) is None
        # La place revient au prochain éligible, avec le numéro libéré.
        assert out["reattribue"]["user_id"] == str(suivant)
        assert (await _rang(suivant)).pioneer_rank == rang
        # Journal.
        async with SessionLocal() as db:
            j = (await db.execute(text(
                "SELECT rank, reason, reassigned_to FROM pioneer_revocations WHERE user_id = :u"),
                {"u": squatteur})).first()
        assert j.rank == rang and "Squat" in j.reason and j.reassigned_to == suivant
        n, d, mx = await _etat_rangs()
        assert n == d and mx <= PIONEER_SLOTS               # pas de doublon
    finally:
        await _cleanup(squatteur, suivant)


async def test_revocation_motif_obligatoire_et_compte_sans_rang():
    uid = await _createur()
    try:
        with pytest.raises(PioneerNotHeld):
            await _revoke(uid)
        await _award(uid, live=False)
        with pytest.raises(ValueError):
            await _revoke(uid, reason="  ")
        assert (await _rang(uid)).pioneer_rank is not None  # rien n'a bougé
    finally:
        await _cleanup(uid)


async def test_revocation_quand_les_100_places_sont_prises():
    """100 rangs pris (le squatteur en tient un) : la révocation libère une
    place, le suivant la prend — toujours exactement 100, max 100."""
    squatteur = await _createur()
    suivant = await _createur(created_at=_TRES_ANCIEN)
    rang = await _award(squatteur, live=False)
    tag = await _prefill_sauf(PIONEER_SLOTS)
    try:
        assert (await _etat_rangs())[0] == PIONEER_SLOTS
        out = await _revoke(squatteur)
        assert out["reattribue"]["user_id"] == str(suivant)
        assert (await _rang(suivant)).pioneer_rank == rang
        n, d, mx = await _etat_rangs()
        assert n == PIONEER_SLOTS and d == PIONEER_SLOTS and mx == PIONEER_SLOTS
    finally:
        await _cleanup(squatteur, suivant)
        await _cleanup_prefill(tag)


async def test_trou_de_rang_repris_par_l_attribution_directe():
    """Un rang libre au milieu (révocation sans successeur possible, ou compte
    supprimé) est repris par la prochaine attribution — jamais de 101."""
    tag = await _prefill_sauf(PIONEER_SLOTS)
    nouveau = await _createur()
    try:
        async with SessionLocal() as db:
            trou = int((await db.execute(text(
                "SELECT pioneer_rank FROM users WHERE email LIKE :p ORDER BY pioneer_rank DESC LIMIT 1"),
                {"p": f"pytest-pfill3-%-{tag}@smyleplay.example"})).scalar_one())
            await db.execute(text("UPDATE users SET pioneer_rank = NULL, is_pioneer = FALSE "
                                  "WHERE pioneer_rank = :r"), {"r": trou})
            await db.commit()
        assert await _award(nouveau, live=False) == trou
        n, d, mx = await _etat_rangs()
        assert n == PIONEER_SLOTS and d == n and mx == PIONEER_SLOTS
    finally:
        await _cleanup(nouveau)
        await _cleanup_prefill(tag)


# ─── 3. CONCURRENCE ───────────────────────────────────────────────────────────

async def test_concurrence_revocation_et_attributions_directes():
    """100 places prises dont celle du squatteur. En même temps : révocation
    + 5 créateurs qui publient. La place libérée n'est attribuée qu'UNE fois,
    le total reste 100, aucun doublon, jamais de 101."""
    squatteur = await _createur()
    await _award(squatteur, live=False)
    tag = await _prefill_sauf(PIONEER_SLOTS)
    concurrents = [await _createur() for _ in range(5)]
    try:
        resultats = await asyncio.wait_for(asyncio.gather(
            _revoke(squatteur), *(_award(u) for u in concurrents),
            return_exceptions=True,
        ), timeout=60)
        assert not any(isinstance(r, Exception) for r in resultats), resultats
        n, d, mx = await _etat_rangs()
        assert n == PIONEER_SLOTS and d == PIONEER_SLOTS and mx == PIONEER_SLOTS
        assert (await _rang(squatteur)).pioneer_rank is None
    finally:
        async with SessionLocal() as db:
            reassigned = (await db.execute(text(
                "SELECT reassigned_to FROM pioneer_revocations WHERE user_id = :u"),
                {"u": squatteur})).scalar_one_or_none()
        await _cleanup(squatteur, *concurrents)
        if reassigned is not None:
            async with SessionLocal() as db:
                await db.execute(text("UPDATE users SET pioneer_rank = NULL, is_pioneer = FALSE, "
                                      "pioneer_awarded_at = NULL WHERE id = :u"), {"u": reassigned})
                await db.commit()
        await _cleanup_prefill(tag)


async def test_concurrence_double_revocation_meme_compte():
    """Deux admins révoquent le même compte en même temps : une seule
    révocation journalisée, une seule réattribution."""
    squatteur = await _createur()
    suivant = await _createur(created_at=_TRES_ANCIEN)
    await _award(squatteur, live=False)
    try:
        res = await asyncio.wait_for(asyncio.gather(
            _revoke(squatteur), _revoke(squatteur), return_exceptions=True), timeout=60)
        ok = [r for r in res if not isinstance(r, Exception)]
        ko = [r for r in res if isinstance(r, Exception)]
        assert len(ok) == 1 and len(ko) == 1 and isinstance(ko[0], PioneerNotHeld)
        async with SessionLocal() as db:
            n = (await db.execute(text(
                "SELECT count(*) FROM pioneer_revocations WHERE user_id = :u"),
                {"u": squatteur})).scalar_one()
        assert int(n) == 1
        n, d, _ = await _etat_rangs()
        assert n == d
    finally:
        await _cleanup(squatteur, suivant)


# ─── 4. Endpoints admin ───────────────────────────────────────────────────────

async def test_endpoint_revocation_admin(client, test_user, auth_headers):
    squatteur = await _createur()
    suivant = await _createur(created_at=_TRES_ANCIEN)
    await _award(squatteur, live=False)
    try:
        url = f"/admin/pioneer/{squatteur}/revoke"
        r = await client.post(url, headers=auth_headers, json={"reason": "Fraude avérée"})
        assert r.status_code == 403                      # pas admin
        async with SessionLocal() as db:
            await db.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :u"),
                             {"u": test_user["id"]})
            await db.commit()
        r = await client.post(url, headers=auth_headers, json={})
        assert r.status_code == 422                      # motif obligatoire
        r = await client.post(url, headers=auth_headers, json={"reason": "Fraude avérée"})
        assert r.status_code == 200, r.text
        assert r.json()["reattribue"]["user_id"] == str(suivant)
        r = await client.post(url, headers=auth_headers, json={"reason": "Fraude avérée"})
        assert r.status_code == 404                      # plus de rang
        r = await client.get("/admin/pioneer/revocations", headers=auth_headers)
        assert r.status_code == 200
        assert any(x["user_id"] == str(squatteur) and x["motif"] == "Fraude avérée"
                   for x in r.json()["revocations"])
    finally:
        await _cleanup(squatteur, suivant)
