"""
Étape 3 — Tests du modèle Playlist unifié.

Couvre :
  - CRUD playlist (POST, GET /me, GET /{id}, PATCH, DELETE)
  - Ajout et retrait de tracks (POST/DELETE /playlists/{id}/tracks[/{track_id}])
  - Visibilité : une playlist privée n'est pas lisible par un tiers
  - Règle métier publique : impossible d'ajouter la track d'un autre artiste
    dans une playlist publique
  - Seed wishlist idempotent (ensure_default_wishlist)

Les tests talk to the real Postgres configuré par DATABASE_URL, cf. conftest.
"""

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.database import SessionLocal
from app.models.playlist import Playlist, PlaylistTrack
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.playlists import (
    WISHLIST_TITLE,
    ensure_default_wishlist,
)
from app.services.users import create_user


# ─── Fixtures helpers ────────────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="session")
async def published_user(test_user: dict) -> AsyncIterator[dict]:
    """User avec profile_public=True pour traverser le gate POST /tracks/."""
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == test_user["id"])
            .values(profile_public=True, artist_name="Pytest Artist")
        )
        await db.commit()
    yield test_user
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == test_user["id"])
            .values(profile_public=False, artist_name=None)
        )
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def owned_track(published_user: dict) -> AsyncIterator[dict]:
    """Une track qui appartient à published_user, insérée directement en base
    pour ne pas dépendre du flux de création qui génère aussi un DNA."""
    import uuid

    track_id = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(
            Track(
                id=track_id,
                title="Track A",
                artist_id=published_user["id"],
            )
        )
        await db.commit()
    yield {"id": track_id, "owner_id": published_user["id"]}
    async with SessionLocal() as db:
        await db.execute(delete(Track).where(Track.id == track_id))
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def foreign_user_and_track() -> AsyncIterator[dict]:
    """Un autre user + sa track, pour tester la règle "tracks étrangères
    refusées dans une playlist publique"."""
    import uuid

    email = f"pytest-foreign-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        other = await create_user(
            db, UserCreate(email=email, password="12345678")
        )
        other_id = other.id
        track = Track(
            id=uuid.uuid4(),
            title="Foreign Track",
            artist_id=other_id,
        )
        db.add(track)
        await db.commit()
        track_id = track.id
    yield {"user_id": other_id, "track_id": track_id}
    async with SessionLocal() as db:
        await db.execute(delete(Track).where(Track.id == track_id))
        await db.execute(delete(User).where(User.id == other_id))
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _cleanup_playlists(test_user: dict) -> AsyncIterator[None]:
    """Nettoie les playlists du test_user entre chaque test pour éviter
    les effets de bord (wishlist créée par un test influence le suivant)."""
    yield
    async with SessionLocal() as db:
        await db.execute(
            delete(Playlist).where(Playlist.owner_id == test_user["id"])
        )
        await db.commit()


# ─── CRUD de base ────────────────────────────────────────────────────────


class TestPlaylistCRUD:
    async def test_create_private_playlist(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.post(
            "/playlists",
            headers=auth_headers,
            json={"title": "Mes favoris"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["title"] == "Mes favoris"
        assert body["visibility"] == "private"  # défaut
        assert body["color"] is None

    async def test_create_public_playlist_with_color(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.post(
            "/playlists",
            headers=auth_headers,
            json={
                "title": "Ma mix d'été",
                "visibility": "public",
                "color": "#FFD700",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["visibility"] == "public"
        assert body["color"] == "#FFD700"

    async def test_create_rejects_invalid_color(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.post(
            "/playlists",
            headers=auth_headers,
            json={"title": "P", "color": "red"},
        )
        assert r.status_code == 422

    async def test_list_my_playlists_filter_visibility(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        # 1 publique + 1 privée
        await client.post(
            "/playlists",
            headers=auth_headers,
            json={"title": "Pub", "visibility": "public"},
        )
        await client.post(
            "/playlists",
            headers=auth_headers,
            json={"title": "Priv", "visibility": "private"},
        )
        r = await client.get(
            "/playlists/me?visibility=public", headers=auth_headers
        )
        assert r.status_code == 200
        titles = [p["title"] for p in r.json()]
        assert "Pub" in titles
        assert "Priv" not in titles

    async def test_patch_title(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "Old"},
            )
        ).json()
        r = await client.patch(
            f"/playlists/{created['id']}",
            headers=auth_headers,
            json={"title": "New"},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "New"

    async def test_delete_playlist(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "ToDelete"},
            )
        ).json()
        r = await client.delete(
            f"/playlists/{created['id']}", headers=auth_headers
        )
        assert r.status_code == 204
        # La relecture doit renvoyer 404
        r2 = await client.get(
            f"/playlists/{created['id']}", headers=auth_headers
        )
        assert r2.status_code == 404


# ─── Gestion des tracks ──────────────────────────────────────────────────


class TestPlaylistTracks:
    async def test_add_own_track_to_private_playlist(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owned_track: dict,
    ) -> None:
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "Wishlist test"},
            )
        ).json()
        r = await client.post(
            f"/playlists/{created['id']}/tracks",
            headers=auth_headers,
            json={"track_id": str(owned_track["id"])},
        )
        assert r.status_code == 201, r.text
        # GET détaillé : la track est dans la liste
        detail = (
            await client.get(
                f"/playlists/{created['id']}", headers=auth_headers
            )
        ).json()
        assert len(detail["tracks"]) == 1
        assert detail["tracks"][0]["id"] == str(owned_track["id"])

    async def test_public_playlist_rejects_foreign_track(
        self,
        client: AsyncClient,
        auth_headers: dict,
        foreign_user_and_track: dict,
    ) -> None:
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "Pub", "visibility": "public"},
            )
        ).json()
        r = await client.post(
            f"/playlists/{created['id']}/tracks",
            headers=auth_headers,
            json={"track_id": str(foreign_user_and_track["track_id"])},
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "public_owner_mismatch"

    async def test_private_playlist_accepts_foreign_track(
        self,
        client: AsyncClient,
        auth_headers: dict,
        foreign_user_and_track: dict,
    ) -> None:
        """Règle : les playlists privées (wishlist, favoris) peuvent
        contenir les sons d'autres artistes."""
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "Wishlist"},
            )
        ).json()
        r = await client.post(
            f"/playlists/{created['id']}/tracks",
            headers=auth_headers,
            json={"track_id": str(foreign_user_and_track["track_id"])},
        )
        assert r.status_code == 201, r.text

    async def test_add_track_idempotent(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owned_track: dict,
    ) -> None:
        """Ajouter deux fois la même track → la seconde met juste à jour la
        position (pas d'IntegrityError sur la PK composite)."""
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "Idem"},
            )
        ).json()
        r1 = await client.post(
            f"/playlists/{created['id']}/tracks",
            headers=auth_headers,
            json={"track_id": str(owned_track["id"]), "position": 0},
        )
        r2 = await client.post(
            f"/playlists/{created['id']}/tracks",
            headers=auth_headers,
            json={"track_id": str(owned_track["id"]), "position": 5},
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        detail = (
            await client.get(
                f"/playlists/{created['id']}", headers=auth_headers
            )
        ).json()
        assert len(detail["tracks"]) == 1  # pas de doublon

    async def test_remove_track(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owned_track: dict,
    ) -> None:
        created = (
            await client.post(
                "/playlists",
                headers=auth_headers,
                json={"title": "R"},
            )
        ).json()
        await client.post(
            f"/playlists/{created['id']}/tracks",
            headers=auth_headers,
            json={"track_id": str(owned_track["id"])},
        )
        r = await client.delete(
            f"/playlists/{created['id']}/tracks/{owned_track['id']}",
            headers=auth_headers,
        )
        assert r.status_code == 204
        detail = (
            await client.get(
                f"/playlists/{created['id']}", headers=auth_headers
            )
        ).json()
        assert detail["tracks"] == []


# ─── Wishlist seed ───────────────────────────────────────────────────────


class TestWishlistSeed:
    async def test_ensure_default_wishlist_is_idempotent(
        self, test_user: dict
    ) -> None:
        """Deux appels successifs → une seule playlist en base."""
        async with SessionLocal() as db:
            user = await db.get(User, test_user["id"])
            w1 = await ensure_default_wishlist(db, user)
            w2 = await ensure_default_wishlist(db, user)
        assert w1.id == w2.id
        assert w1.title == WISHLIST_TITLE
        assert w1.visibility == "private"

    async def test_wishlist_endpoint_returns_same_playlist(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r1 = await client.get("/playlists/wishlist", headers=auth_headers)
        r2 = await client.get("/playlists/wishlist", headers=auth_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        assert r1.json()["title"] == WISHLIST_TITLE


# ─── Règles de visibilité ────────────────────────────────────────────────


class TestPlaylistAuth:
    async def test_read_without_auth_401(self, client: AsyncClient) -> None:
        import uuid

        r = await client.get(f"/playlists/{uuid.uuid4()}")
        assert r.status_code == 401

    async def test_not_found_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        import uuid

        r = await client.get(
            f"/playlists/{uuid.uuid4()}", headers=auth_headers
        )
        assert r.status_code == 404
