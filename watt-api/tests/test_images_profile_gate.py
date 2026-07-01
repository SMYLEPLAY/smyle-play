"""
C1 — Gate "profil publié" avant publication d'une IMAGE.

Parité STRICTE avec test_tracks_profile_gate.py : on harmonise le monde
visuel sur les règles de la musique. Une image ne doit pouvoir être créée
QUE si l'utilisateur a publié son profil public (users.profile_public=True).
Le backend refuse sinon avec 409 CONFLICT + payload structuré
({"error": "profile_not_published", ...}) pour que le front réutilise la
même CTA de redirection que pour les sons.

Couvre POST /artist/me/images (multipart). Le gate s'exécute en TÊTE du
handler, avant toute validation fichier/Pydantic : un multipart minimal
mais complet (tous les Form() requis présents, sinon 422 en amont) suffit
à l'atteindre.
"""

from typing import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update

from app.database import SessionLocal
from app.models.user import User


# Champs Form requis par create_my_image — doivent TOUS être présents, sinon
# FastAPI renvoie 422 (résolution des paramètres) avant d'entrer dans le corps
# du handler où vit le gate. Valeurs valides mais sans importance ici : le gate
# 409 précède la validation métier (Pydantic / upload R2).
_MIN_FILE = {"file": ("g.png", b"\x89PNG\r\n\x1a\n", "image/png")}
_MIN_FORM = {
    "title": "Cover test",
    "image_platform": "chatgpt",
    "image_model_version": "gpt-image-1",
    "prompt_text": "a neon jungle at dusk",
    "price_credits": "5",
}


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


class TestImageCreateGate:
    """Gate profile_public côté POST /artist/me/images."""

    async def test_rejects_when_profile_not_published(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """Sans profil publié → 409 profile_not_published."""
        r = await client.post(
            "/artist/me/images",
            headers=auth_headers,
            files=_MIN_FILE,
            data=_MIN_FORM,
        )
        assert r.status_code == 409, r.text
        body = r.json()
        detail = body.get("detail", body)
        assert detail.get("error") == "profile_not_published"
        assert "publie" in detail.get("message", "").lower()
        assert detail.get("redirect") == "/u/me"

    async def test_rejects_without_auth(self, client: AsyncClient) -> None:
        """Sanity : sans token → 401, pas 409."""
        r = await client.post(
            "/artist/me/images",
            files=_MIN_FILE,
            data=_MIN_FORM,
        )
        assert r.status_code == 401

    async def test_allows_when_profile_published(
        self,
        client: AsyncClient,
        auth_headers: dict,
        published_user: dict,  # noqa: ARG002 — fixture-effect
    ) -> None:
        """Avec profil publié, la requête TRAVERSE le gate (pas de 409).

        On accepte ensuite n'importe quel code downstream (201 succès, ou
        503/500 si R2 non configuré dans l'env de test) : ce qui compte est
        qu'on NE reçoit PAS 409 — le gate a laissé passer.
        """
        r = await client.post(
            "/artist/me/images",
            headers=auth_headers,
            files=_MIN_FILE,
            data=_MIN_FORM,
        )
        assert r.status_code != 409, r.text
