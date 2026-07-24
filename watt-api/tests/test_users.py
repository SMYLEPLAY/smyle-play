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


async def test_export_me_requires_auth_and_returns_profile(
    client: AsyncClient, test_user: dict, auth_headers: dict
):
    """RGPD export (Phase 3) : refus sans auth, JSON complet avec auth."""
    r0 = await client.get("/users/me/export")
    assert r0.status_code == 401, r0.text
    r = await client.get("/users/me/export", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert "attachment" in (r.headers.get("content-disposition") or "")
    j = r.json()
    for key in ("profile", "tracks", "prompts", "playlists", "transactions"):
        assert key in j, j.keys()
    assert j["profile"]["email"] == test_user["email"]


async def test_token_revoked_when_version_bumps(
    client: AsyncClient, test_user: dict, auth_headers: dict
):
    """Durcissement : un jeton devient invalide dès que token_version change
    (mécanisme utilisé par le reset de mot de passe)."""
    from sqlalchemy import update

    # Le jeton courant marche.
    r = await client.get("/users/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    # On incrémente token_version en base (comme le fait un reset).
    async with SessionLocal() as db:
        await db.execute(
            update(User).where(User.id == test_user["id"]).values(token_version=1)
        )
        await db.commit()
    # Le même jeton (tv=0) est désormais rejeté.
    r2 = await client.get("/users/me", headers=auth_headers)
    assert r2.status_code == 401, r2.text


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
