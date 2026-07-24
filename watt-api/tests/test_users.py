"""
Tests inscription — bonus de bienvenue (marathon ②, 2026-06-11).

Décision Tom (handoff 0bis.6) : chaque nouveau compte reçoit 10 Smyles
à l'inscription (prérequis pour tester le circuit d'achat C2).
Nécessite Postgres réel (voir conftest).
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.models.user import User

WELCOME_BONUS = 10


async def test_register_grants_welcome_bonus(client: AsyncClient):
    email = f"pytest-welcome-{uuid.uuid4().hex[:10]}@smyleplay.example"
    try:
        r = await client.post(
            "/auth/register",
            json={"email": email, "password": "12345678",
                  "accept_terms": True, "age_confirmed": True},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["credits_balance"] == WELCOME_BONUS, body
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.email == email))
            await db.commit()


async def test_register_requires_terms_and_age(client: AsyncClient):
    """Inscription encadrée (Phase 3) : refus si CGU/âge non acceptés."""
    email = f"pytest-noterms-{uuid.uuid4().hex[:10]}@smyleplay.example"
    # Sans les champs → 400
    r = await client.post("/auth/register",
                          json={"email": email, "password": "12345678"})
    assert r.status_code == 400, r.text
    # age_confirmed manquant → 400
    r = await client.post("/auth/register",
                          json={"email": email, "password": "12345678",
                                "accept_terms": True})
    assert r.status_code == 400, r.text
    # aucun compte ne doit avoir été créé
    async with SessionLocal() as db:
        n = (await db.execute(
            delete(User).where(User.email == email)
        )).rowcount
    assert n == 0
