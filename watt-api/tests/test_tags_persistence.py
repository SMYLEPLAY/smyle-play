"""
E2E — persistance des tags/moods d'un son (création → /tracks/me → PATCH).

Contexte (2026-06-09) : un bug a été remonté côté dashboard — « les tags ne
sont pas persistés à l'édition ». La cause réelle était frontend (le crayon
lisait le localStorage au lieu de l'API). Le correctif fait que le crayon
s'appuie désormais sur GET /tracks/me comme SOURCE DE VÉRITÉ.

Ce test verrouille donc le contrat backend dont dépend ce correctif :
  1. POST /tracks/ avec tags → les tags sont persistés (et non NULL).
  2. GET /tracks/me renvoie bien le champ `tags` (ce que lit le crayon).
  3. PATCH /tracks/{id} { tags } met à jour les tags.
  4. Les tags modifiés sont bien re-servis par /tracks/me (persistance).
  5. PATCH { tags: null } efface les tags.

Si quelqu'un retire `tags` de TrackRead, du PATCH, ou de la création, ce
test devient rouge AVANT la prod — exactement ce qui manquait jusqu'ici.

DB requise (DATABASE_URL → Postgres), comme tout le dossier tests/.
"""

from typing import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.database import SessionLocal
from app.models.track import Track
from app.models.user import User


@pytest_asyncio.fixture(loop_scope="session")
async def published_user(test_user: dict) -> AsyncIterator[dict]:
    """User dont le profil est public (pré-requis pour publier un son)."""
    async with SessionLocal() as db:
        await db.execute(
            update(User).where(User.id == test_user["id"]).values(profile_public=True)
        )
        await db.commit()
    yield test_user
    async with SessionLocal() as db:
        await db.execute(
            update(User).where(User.id == test_user["id"]).values(profile_public=False)
        )
        await db.commit()


async def _create_track(client: AsyncClient, auth_headers: dict, tags) -> dict:
    r = await client.post(
        "/tracks/",
        headers=auth_headers,
        json={
            "title": "Tag persistence test",
            "full_prompt": "deep house 128 bpm dark nocturne",
            "tags": tags,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["track"]


async def _get_my_track(client: AsyncClient, auth_headers: dict, track_id: str) -> dict:
    r = await client.get("/tracks/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    by_id = {t["id"]: t for t in r.json()}
    assert track_id in by_id, "le son créé doit apparaître dans /tracks/me"
    return by_id[track_id]


async def test_tags_persist_through_create_and_patch(
    client: AsyncClient,
    auth_headers: dict,
    published_user: dict,  # noqa: ARG001 — effet de fixture (profil public)
) -> None:
    track = await _create_track(client, auth_headers, tags="chill, dark")
    track_id = track["id"]
    try:
        # 1. Création : tags persistés dès le POST.
        assert track["tags"] == "chill, dark"

        # 2. /tracks/me (source de vérité du crayon) renvoie bien les tags.
        mine = await _get_my_track(client, auth_headers, track_id)
        assert mine["tags"] == "chill, dark"

        # 3. PATCH des tags (le flux d'édition qui était signalé cassé).
        r = await client.patch(
            f"/tracks/{track_id}",
            headers=auth_headers,
            json={"tags": "festif, vocal"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["tags"] == "festif, vocal"

        # 4. Persistance confirmée par un nouveau GET /tracks/me.
        mine = await _get_my_track(client, auth_headers, track_id)
        assert mine["tags"] == "festif, vocal"

        # 5. On peut aussi effacer les tags (None).
        r = await client.patch(
            f"/tracks/{track_id}",
            headers=auth_headers,
            json={"tags": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["tags"] is None
        mine = await _get_my_track(client, auth_headers, track_id)
        assert mine["tags"] is None
    finally:
        # Nettoyage : supprime le son (CASCADE sur dna) pour ne pas bloquer
        # le teardown du user et ne pas polluer la base CI.
        async with SessionLocal() as db:
            await db.execute(delete(Track).where(Track.id == track_id))
            await db.commit()


async def test_patch_tags_requires_ownership(
    client: AsyncClient,
    auth_headers: dict,
    published_user: dict,  # noqa: ARG001
) -> None:
    """PATCH sur un track inexistant/non possédé → 404 (anti-énumération)."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = await client.patch(
        f"/tracks/{fake_id}",
        headers=auth_headers,
        json={"tags": "x"},
    )
    assert r.status_code == 404, r.text
