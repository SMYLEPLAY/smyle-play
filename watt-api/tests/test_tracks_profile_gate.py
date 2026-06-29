"""
Étape 1 — Gate "profil publié" avant publication d'un son.

Un son ne doit pouvoir être publié QUE si l'utilisateur a au préalable
publié son profil public (users.profile_public = True). Le backend doit
refuser avec 409 CONFLICT et un payload structuré
({"error": "profile_not_published", ...}) pour que le frontend puisse
afficher une CTA de redirection.

Ces tests couvrent le endpoint FastAPI POST /tracks/. Le miroir Flask
sur POST /api/watt/tracks est couvert par les tests Flask.
"""

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update

from app.database import SessionLocal
from app.models.user import User


@pytest_asyncio.fixture(loop_scope="session")
async def published_user(test_user: dict) -> AsyncIterator[dict]:
    """Un user dont le profil est marqué public en base."""
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == test_user["id"])
            .values(profile_public=True)
        )
        await db.commit()
    yield test_user
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == test_user["id"])
            .values(profile_public=False)
        )
        await db.commit()


class TestTrackCreateGate:
    """Gate profile_public côté FastAPI POST /tracks/."""

    async def test_rejects_when_profile_not_published(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """Sans profil publié, POST /tracks/ → 409 profile_not_published."""
        r = await client.post(
            "/tracks/",
            headers=auth_headers,
            json={"title": "Mon son", "full_prompt": "deep house 128 bpm"},
        )
        assert r.status_code == 409, r.text
        body = r.json()
        # FastAPI emballe le payload dans "detail"
        detail = body.get("detail", body)
        assert detail.get("error") == "profile_not_published"
        assert "publie" in detail.get("message", "").lower()
        assert detail.get("redirect") == "/u/me"

    async def test_rejects_without_auth(self, client: AsyncClient) -> None:
        """Sanity : sans token, 401 — pas 409."""
        r = await client.post(
            "/tracks/",
            json={"title": "Mon son", "full_prompt": "deep house 128 bpm"},
        )
        assert r.status_code == 401

    async def test_allows_when_profile_published(
        self,
        client: AsyncClient,
        auth_headers: dict,
        published_user: dict,  # noqa: ARG002 — fixture-effect
    ) -> None:
        """Avec profil publié, POST /tracks/ traverse le gate (201 ou 500).

        On accepte 201 (succès) ou 500 (échec downstream dans
        create_track_with_dna — hors scope de ce test). Ce qui compte ici
        c'est qu'on NE reçoit PAS 409.
        """
        r = await client.post(
            "/tracks/",
            headers=auth_headers,
            json={"title": "Mon son", "full_prompt": "deep house 128 bpm"},
        )
        assert r.status_code != 409, r.text
