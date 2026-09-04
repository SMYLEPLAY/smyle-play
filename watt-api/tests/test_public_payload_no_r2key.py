"""
S-05 sécurité (2026-09-02) — `r2Key` retiré des payloads publics « compat
Flask » (audit A §B6, court terme).

La clé de stockage R2 d'un track n'a aucun consommateur front (grep
`r2Key` : 0 hors la réponse d'upload du dashboard) et désigne exactement
l'objet servi par le téléchargement gaté (`/beats/{id}/download`) : elle
n'a rien à faire dans `/watt/tracks-recent`, `/watt/artists/{slug}`,
`/watt/tracks-catalog`. `streamUrl` suffit à l'écoute. Postgres requis.
"""
import uuid

import pytest
from sqlalchemy import delete, text

from app.database import SessionLocal
from app.models.track import Track
from app.models.user import User
from app.routers.watt_compat import _track_to_flask_dict
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _walk(obj, path=""):
    """Génère (chemin, clé) pour chaque clé de dict rencontrée récursivement."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _assert_no_r2key(payload) -> None:
    leaks = [p for p, k in _walk(payload) if k in ("r2Key", "r2_key")]
    assert leaks == [], f"clé R2 exposée : {leaks[:5]}"


async def _seed_artist_with_track() -> tuple[uuid.UUID, uuid.UUID, str]:
    suffix = uuid.uuid4().hex[:10]
    email = f"pytest-r2key-{suffix}@smyleplay.example"
    name = f"R2Key Artist {suffix}"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET profile_public = TRUE, artist_name = :n WHERE id = :u"),
            {"n": name, "u": uid},
        )
        tr = Track(
            artist_id=uid, title=f"Track {suffix}",
            r2_key=f"tracks/secret-key-{suffix}.wav",
            audio_url=f"/watt/stream/tracks/secret-key-{suffix}.wav",
        )
        db.add(tr)
        await db.commit()
        await db.refresh(tr)
        track_id = tr.id
    from app.core.slug import slugify
    return uid, track_id, slugify(name)


async def _cleanup(uid: uuid.UUID) -> None:
    async with SessionLocal() as db:
        from app.models.dna import DNA
        await db.execute(delete(Track).where(Track.artist_id == uid))
        await db.execute(delete(DNA).where(DNA.artist_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_track_to_flask_dict_has_no_r2key():
    class _T:  # stub minimal (pas de DB)
        legacy_id = None
        id = uuid.uuid4()
        created_at = None
        title = "T"
        audio_url = "/watt/stream/tracks/a.wav"
        r2_key = "tracks/a.wav"
        plays = 0
        cover_url = None
        prompt_id = None
        color = None
        tags = None
        platform = None
        is_beat = False
        bpm = None
        beat_id = None
        pack_price_credits = None
        universe = None
        duration_seconds = None

    d = _track_to_flask_dict(_T())
    assert "r2Key" not in d
    assert d["streamUrl"] == "/watt/stream/tracks/a.wav"


async def test_tracks_recent_has_no_r2key(client):
    uid, track_id, slug = await _seed_artist_with_track()
    try:
        r = await client.get("/watt/tracks-recent", params={"limit": 50})
        assert r.status_code == 200, r.text
        body = r.json()
        _assert_no_r2key(body)
        tracks = body["tracks"]
        mine = [t for t in tracks if t.get("id") == str(track_id)]
        assert len(mine) == 1, "le track seedé doit apparaître dans tracks-recent"
        # L'écoute reste possible : streamUrl toujours servi.
        assert mine[0]["streamUrl"].startswith("/watt/stream/")

        r2 = await client.get(f"/watt/artists/{slug}")
        assert r2.status_code == 200, r2.text
        _assert_no_r2key(r2.json())

        r3 = await client.get("/watt/tracks-catalog")
        assert r3.status_code == 200, r3.text
        _assert_no_r2key(r3.json())
    finally:
        await _cleanup(uid)
