"""
Shared pytest fixtures.

These tests talk to the real Postgres configured by DATABASE_URL.
Run them with:

    docker-compose exec api pytest -q

Each fixture creates a unique user and cleans up on exit so tests
don't leak data between runs.

Configuration: voir pytest.ini — `asyncio_mode = auto` et
`asyncio_default_fixture_loop_scope = session` pour que tous les tests
partagent le même event loop (sinon SessionLocal de app.database ne
peut pas être réutilisé entre tests : InterfaceError asyncpg).
"""

import uuid
from typing import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.main import app
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def test_user() -> AsyncIterator[dict]:
    email = f"pytest-{uuid.uuid4().hex[:12]}@smyleplay.example"
    password = "12345678"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password=password))
        user_id = user.id
    try:
        yield {"id": user_id, "email": email, "password": password}
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def auth_headers(client: AsyncClient, test_user: dict) -> dict:
    r = await client.post(
        "/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
