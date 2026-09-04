"""
S-07 sécurité (2026-09-02) — course « double récompense » sur le check-in
quotidien (audit A §M2).

Avant : `claim_daily_checkin` lisait `last_checkin_date` sans verrou, décidait
en Python, puis écrivait ; `grant_credits_atomic` ne verrouillait la ligne
qu'APRÈS la décision. Deux requêtes concurrentes (2 workers uvicorn en prod,
ou N appels parallèles depuis un script) lisaient toutes la valeur périmée et
réclamaient toutes la récompense.

Désormais : UPDATE conditionnel atomique avec RETURNING — une seule des
transactions concurrentes obtient une ligne, les autres reçoivent None
(`already_claimed`). Plus un rate-limit `LIMIT_CHECKIN` sur la route.

Les appels partent en `asyncio.gather` sur le transport ASGI de httpx : les
requêtes s'entrelacent réellement sur la même boucle et partagent le pool
asyncpg, donc l'entrelacement de production est reproduit. Postgres requis
(cf. conftest.py).
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.core.ratelimit import LIMIT_CHECKIN
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.streak import reward_for_streak
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PASSWORD = "12345678"
_CONCURRENCY = 5


async def _make_user() -> dict:
    """Utilisateur neuf, trophées pré-attribués (aucun bonus parasite au solde)."""
    email = f"pytest-streak-race-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password=_PASSWORD))
        user_id = user.id
    async with SessionLocal() as db:
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=user_id, achievement_id=ach.id))
        await db.commit()
    return {"id": user_id, "email": email}


async def _cleanup(user_id) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _login(client, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": _PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _balance(user_id) -> int:
    async with SessionLocal() as db:
        return int((await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :u"), {"u": user_id}
        )).scalar_one())


async def test_checkin_concurrent_grants_once(client):
    """5 check-ins en parallèle → exactement 1 `claimed`, 1 seule récompense."""
    user = await _make_user()
    try:
        headers = await _login(client, user["email"])
        before = await _balance(user["id"])

        responses = await asyncio.gather(*[
            client.post("/streak/checkin", headers=headers)
            for _ in range(_CONCURRENCY)
        ])

        # Toutes aboutissent (le rate-limit est désactivé quand ENVIRONMENT=test).
        for r in responses:
            assert r.status_code == 200, r.text

        bodies = [r.json() for r in responses]
        claimed = [b for b in bodies if b["claimed"]]
        assert len(claimed) == 1, bodies

        assert claimed[0]["streak_count"] == 1
        assert claimed[0]["reward_granted"] == reward_for_streak(1)

        # Les perdantes sont des no-op idempotents, pas des erreurs.
        for b in bodies:
            if not b["claimed"]:
                assert b["already_claimed"] is True
                assert b["reward_granted"] == 0
                assert b["streak_count"] == 1

        # Le solde n'a bougé que d'UNE récompense (avant le correctif : ×5).
        assert await _balance(user["id"]) == before + reward_for_streak(1)
    finally:
        await _cleanup(user["id"])


async def test_checkin_sequential_behaviour_unchanged(client):
    """Comportement séquentiel identique à avant : 1er claim, 2e idempotent."""
    user = await _make_user()
    try:
        headers = await _login(client, user["email"])
        before = await _balance(user["id"])

        r1 = await client.post("/streak/checkin", headers=headers)
        assert r1.status_code == 200, r1.text
        assert r1.json()["claimed"] is True
        assert r1.json()["streak_count"] == 1

        r2 = await client.post("/streak/checkin", headers=headers)
        assert r2.status_code == 200, r2.text
        assert r2.json()["claimed"] is False
        assert r2.json()["already_claimed"] is True
        assert r2.json()["streak_count"] == 1

        me = await client.get("/streak/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["streak_count"] == 1
        assert me.json()["can_checkin_today"] is False

        assert await _balance(user["id"]) == before + reward_for_streak(1)
    finally:
        await _cleanup(user["id"])


async def test_checkin_consecutif_incremente_le_streak(client):
    """Branche CASE (dernier check-in = hier → +1) de l'UPDATE conditionnel."""
    user = await _make_user()
    try:
        headers = await _login(client, user["email"])
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET streak_count = 3, "
                    "last_checkin_date = CURRENT_DATE - 1 WHERE id = :u"
                ),
                {"u": user["id"]},
            )
            await db.commit()

        r = await client.post("/streak/checkin", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["claimed"] is True
        assert r.json()["streak_count"] == 4
    finally:
        await _cleanup(user["id"])


async def test_checkin_apres_trou_repart_a_un(client):
    """Branche ELSE (trou de plusieurs jours → 1) de l'UPDATE conditionnel."""
    user = await _make_user()
    try:
        headers = await _login(client, user["email"])
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET streak_count = 9, "
                    "last_checkin_date = CURRENT_DATE - 5 WHERE id = :u"
                ),
                {"u": user["id"]},
            )
            await db.commit()

        r = await client.post("/streak/checkin", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["claimed"] is True
        assert r.json()["streak_count"] == 1
    finally:
        await _cleanup(user["id"])


async def test_limit_checkin_declare():
    """Garde-fou : la limite existe et reste large pour un humain qui reclique."""
    assert LIMIT_CHECKIN == "5/minute"
