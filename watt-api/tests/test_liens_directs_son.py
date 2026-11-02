"""
Liens directs (02/11) — /watt/tracks-recent?track=<id> renvoie UN son précis.

Sert au lien partageable /sons?son=<id> : la page ouvre la fiche du son même
s'il n'est pas dans les 100 derniers. Mêmes filtres de visibilité que la
liste (profil public, son ni supprimé ni masqué) et même enrichissement
(image liée / Œuvre).

REQUIRES : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.track import Track

from tests.test_tracks_recent_binarite import (
    _cleanup,
    _mk_artist,
    _mk_son_image_track,
)


async def test_track_par_uuid_renvoie_ce_son_seul(client):
    artist = await _mk_artist()
    son_id, img_id, tr_id = await _mk_son_image_track(artist)
    try:
        r = await client.get(f"/watt/tracks-recent?track={tr_id}")
        assert r.status_code == 200, r.text
        tracks = r.json()["tracks"]
        assert len(tracks) == 1
        assert tracks[0]["trackUuid"] == str(tr_id)
        # Même enrichissement que la liste : l'Œuvre liée est exposée.
        assert tracks[0]["linkedImage"]["id"] == str(img_id)
    finally:
        await _cleanup(artist, [tr_id])


async def test_track_par_legacy_id(client):
    artist = await _mk_artist()
    legacy = f"sl-test-{uuid.uuid4().hex[:10]}"
    async with SessionLocal() as db:
        tr = Track(artist_id=artist, title="Legacy", legacy_id=legacy)
        db.add(tr)
        await db.commit()
        tr_id = tr.id
    try:
        r = await client.get(f"/watt/tracks-recent?track={legacy}")
        assert r.status_code == 200, r.text
        tracks = r.json()["tracks"]
        assert [t["id"] for t in tracks] == [legacy]
    finally:
        await _cleanup(artist, [tr_id])


async def test_track_introuvable_ou_profil_prive_ne_fuite_pas(client):
    # Id inconnu → liste vide, pas d'erreur.
    r = await client.get(f"/watt/tracks-recent?track={uuid.uuid4()}")
    assert r.status_code == 200
    assert r.json()["tracks"] == []

    # Son d'un artiste au profil privé → invisible, même par lien direct.
    artist = await _mk_artist()
    _son_id, _img_id, tr_id = await _mk_son_image_track(artist)
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET profile_public = FALSE WHERE id = :u"), {"u": artist})
        await db.commit()
    try:
        r = await client.get(f"/watt/tracks-recent?track={tr_id}")
        assert r.status_code == 200
        assert r.json()["tracks"] == []
    finally:
        await _cleanup(artist, [tr_id])
