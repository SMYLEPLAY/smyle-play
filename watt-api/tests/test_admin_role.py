"""K-01 (2026-09-04) — rôle d'administration distinct du compte vitrine.

Avant : la seule garde admin était `is_official`, porté par le seul compte
« Smyle » (mot de passe aléatoire, inconnu) — donc aucune action
d'administration n'était réalisable. On vérifie ici que `is_admin` ouvre les
gardes, que `is_official` continue de les ouvrir (aucune régression), et
qu'un membre ordinaire reste en 403.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update

from app.auth.dependencies import is_admin_user
from app.database import SessionLocal
from app.models.user import User

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Endpoint représentatif de la garde d'administration (routers/users.py).
ADMIN_ENDPOINT = "/users/eco-cockpit"


async def _set_flags(user_id, **values) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers(client: AsyncClient, test_user: dict, auth_headers: dict):
    """Le user de test devient admin par `is_admin` (jamais `is_official`)."""
    await _set_flags(test_user["id"], is_admin=True)
    try:
        yield auth_headers
    finally:
        await _set_flags(test_user["id"], is_admin=False)


# ── La règle elle-même ─────────────────────────────────────────────────────

async def test_is_admin_user_accepte_les_deux_flags():
    normal = User(email="a@b.c", is_official=False, is_admin=False)
    admin = User(email="a@b.c", is_official=False, is_admin=True)
    officiel = User(email="a@b.c", is_official=True, is_admin=False)
    assert is_admin_user(normal) is False
    assert is_admin_user(admin) is True
    assert is_admin_user(officiel) is True


# ── Bout en bout ───────────────────────────────────────────────────────────

async def test_utilisateur_normal_403(client: AsyncClient, auth_headers: dict):
    r = await client.get(ADMIN_ENDPOINT, headers=auth_headers)
    assert r.status_code == 403, r.text


async def test_admin_passe(client: AsyncClient, admin_headers: dict):
    r = await client.get(ADMIN_ENDPOINT, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "solvabilite" in r.json()


async def test_is_official_inchange(
    client: AsyncClient, test_user: dict, auth_headers: dict
):
    """Aucune régression : le compte vitrine garde son accès, et is_admin
    reste FALSE (les deux flags sont indépendants)."""
    await _set_flags(test_user["id"], is_official=True)
    try:
        r = await client.get(ADMIN_ENDPOINT, headers=auth_headers)
        assert r.status_code == 200, r.text
        async with SessionLocal() as db:
            u = await db.get(User, test_user["id"])
            assert u.is_official is True
            assert u.is_admin is False
    finally:
        await _set_flags(test_user["id"], is_official=False)


async def test_defaut_non_admin(test_user: dict):
    """Un compte fraîchement créé n'a AUCUN droit d'administration."""
    async with SessionLocal() as db:
        u = await db.get(User, test_user["id"])
    assert u.is_admin is False
    assert u.is_official is False
    assert is_admin_user(u) is False


async def test_grant_credits_gate_sur_admin(
    client: AsyncClient, test_user: dict, auth_headers: dict
):
    """POST /credits/grant : 403 pour un membre, ouvert à un admin (K-01)."""
    payload = {"credits": 1, "reason": f"test-k01-{uuid.uuid4().hex[:8]}"}
    r = await client.post("/credits/grant", json=payload, headers=auth_headers)
    assert r.status_code == 403, r.text

    await _set_flags(test_user["id"], is_admin=True)
    try:
        r = await client.post("/credits/grant", json=payload, headers=auth_headers)
        assert r.status_code == 201, r.text
    finally:
        await _set_flags(test_user["id"], is_admin=False)
