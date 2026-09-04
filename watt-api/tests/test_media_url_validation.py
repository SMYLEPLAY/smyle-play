"""
S-03 sécurité (2026-09-02) — validateur d'URL média `validate_media_url`.

Les `audio_url` / `cover_url` des tracks et les `avatar_url` /
`cover_photo_url` des profils finissent dans des attributs `src="…"`
construits en innerHTML sur l'accueil non connecté (audit A §B1). Ces tests
verrouillent la barrière serveur : sortie d'attribut (`"`), schémas
`javascript:` / `data:`, chemins relatifs hors proxy → 422 ; les valeurs
légitimes émises par le dashboard (`/watt/stream/<clé>`, `/watt/images/<clé>`,
anciennes URL R2 `https://pub-….r2.dev/…`) passent toujours.

Partie 1 : tests de schéma purs (DB-free, style test_track_color_schema.py).
Partie 2 : bout de chaîne HTTP (`POST /tracks/` → 422), Postgres requis.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import update

from app.database import SessionLocal
from app.models.user import User
from app.schemas.track import TrackCreate, TrackUpdate, validate_media_url
from app.schemas.user import UserUpdate


def _track(**kw) -> TrackCreate:
    return TrackCreate(title="T", full_prompt="x" * 10, **kw)


# ── Partie 1 — schémas (DB-free) ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "piege",
    [
        'https://x/a.mp3" onerror="alert(1)',   # sortie d'attribut
        "javascript:alert(1)",                  # schéma exécutable
        "data:text/html,<script>alert(1)</script>",
        "/etc/passwd",                          # relatif hors proxy
        "/x\" onload=\"alert(1)",
        "/static/x.wav",                        # relatif hors /watt/(stream|images)
        "ftp://x/a.mp3",                        # schéma non http(s)
        "/watt/stream/a\nb.wav",                # caractère de contrôle (le strip ne s'applique qu'aux bords)
        "https://x/a\tb.mp3",
        "https://x/a`b.mp3",                    # backtick
        "https://x/a\\b.mp3",                   # antislash
        "<script>",
        "a.mp3",                                # ni relatif proxy ni absolu
    ],
)
def test_track_audio_url_rejects_attribute_breakout(piege: str) -> None:
    with pytest.raises(ValidationError):
        _track(audio_url=piege)
    with pytest.raises(ValidationError):
        _track(cover_url=piege)


@pytest.mark.parametrize(
    "legit",
    [
        "/watt/stream/tracks/a-b.wav",                    # POST /watt/upload
        "/watt/stream/tracks/mon-son-0123abcd4567.mp3",
        "/watt/stream/tracks/Mon Son.wav",                # ancienne clé avec espace
        "/watt/images/images/track-cover/abc123.jpg",     # POST /watt/upload-image
        "/watt/images/PLAYLISTS/u1/uid-cover.png",
        "https://pub-x.r2.dev/A%20B/x.wav",               # anciennes lignes DB (R2 public)
        "https://pub-abc123.r2.dev/tracks/son.mp3",
        "http://localhost:8000/watt/stream/tracks/a.wav",
    ],
)
def test_track_audio_url_accepts_proxy_and_https(legit: str) -> None:
    assert _track(audio_url=legit).audio_url == legit
    assert _track(cover_url=legit).cover_url == legit
    assert TrackUpdate(cover_url=legit).cover_url == legit


def test_media_url_empty_becomes_none() -> None:
    assert validate_media_url(None) is None
    assert validate_media_url("") is None
    assert validate_media_url("   ") is None
    assert _track(audio_url="").audio_url is None
    assert _track().audio_url is None


def test_track_update_cover_url_rejects_breakout() -> None:
    with pytest.raises(ValidationError):
        TrackUpdate(cover_url='/x" onload="alert(1)')
    with pytest.raises(ValidationError):
        TrackUpdate(cover_url="javascript:alert(1)")


def test_user_avatar_relative_url_rejects_quotes() -> None:
    with pytest.raises(ValidationError):
        UserUpdate(avatar_url='/x" onload="alert(1)')
    with pytest.raises(ValidationError):
        UserUpdate(cover_photo_url='/x" onload="alert(1)')
    with pytest.raises(ValidationError):
        UserUpdate(avatar_url="/x")  # relatif hors proxy : plus accepté
    ok = UserUpdate(avatar_url="/watt/images/images/avatars/a.jpg")
    assert ok.avatar_url == "/watt/images/images/avatars/a.jpg"
    ok2 = UserUpdate(cover_photo_url="https://pub-x.r2.dev/images/banners/b.jpg")
    assert ok2.cover_photo_url == "https://pub-x.r2.dev/images/banners/b.jpg"
    assert UserUpdate(avatar_url="").avatar_url is None


def test_user_artist_name_rejects_html() -> None:
    with pytest.raises(ValidationError):
        UserUpdate(artist_name='x"><img src=x onerror=alert(1)>')
    with pytest.raises(ValidationError):
        UserUpdate(artist_name="<svg/onload=alert(1)>")
    with pytest.raises(ValidationError):
        UserUpdate(artist_name="Smyle\x00")
    with pytest.raises(ValidationError):
        UserUpdate(artist_name="Smy`le")
    # Noms légitimes : accents, &, tirets ; l'apostrophe ASCII est
    # normalisée en apostrophe typographique (inoffensive en JS inline).
    assert UserUpdate(artist_name="Smyle & Co — Léa").artist_name == "Smyle & Co — Léa"
    assert UserUpdate(artist_name="L'Impératrice").artist_name == "L’Impératrice"


@pytest.mark.parametrize("value", ["suno", "udio", "riffusion", "stable_audio", "autre"])
def test_track_platform_accepts_dashboard_values(value: str) -> None:
    # Valeurs du <select id="dashTrackPlatform"> / cp_platform (dashboard.html/js).
    assert _track(platform=value).platform == value
    assert TrackUpdate(platform=value).platform == value


def test_track_platform_normalizes_and_rejects_unknown() -> None:
    assert _track(platform="").platform is None       # select non renseigné
    assert _track(platform=None).platform is None
    assert _track(platform=" Suno ").platform == "suno"
    with pytest.raises(ValidationError):
        _track(platform="<svg/onload=alert()>")        # injection #11 (20 chars)
    with pytest.raises(ValidationError):
        _track(platform="midjourney")                  # plateforme image ≠ audio
    with pytest.raises(ValidationError):
        TrackUpdate(platform="x")


# ── Partie 2 — bout de chaîne HTTP (Postgres) ────────────────────────────────

async def test_post_tracks_with_trapped_audio_url_is_422(client, test_user, auth_headers):
    """`POST /tracks/` avec une audio_url piégée → 422 (jamais persistée)."""
    async with SessionLocal() as db:
        await db.execute(
            update(User).where(User.id == test_user["id"]).values(profile_public=True)
        )
        await db.commit()

    r = await client.post(
        "/tracks/",
        json={
            "title": "Piège",
            "full_prompt": "deep house 128bpm",
            "audio_url": 'https://x/a.mp3" onerror="alert(1)',
        },
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text

    r2 = await client.post(
        "/tracks/",
        json={
            "title": "Piège 2",
            "full_prompt": "deep house 128bpm",
            "audio_url": "/watt/stream/tracks/ok.wav",
            "platform": "<svg/onload=alert()>",
        },
        headers=auth_headers,
    )
    assert r2.status_code == 422, r2.text

    # Cas légitime (ce que le dashboard envoie après POST /watt/upload) → 201.
    r3 = await client.post(
        "/tracks/",
        json={
            "title": "Légitime",
            "full_prompt": "deep house 128bpm",
            "audio_url": "/watt/stream/tracks/legitime-0123abcd4567.wav",
            "r2_key": "tracks/legitime-0123abcd4567.wav",
            "cover_url": "/watt/images/images/track-cover/abc.jpg",
            "platform": "suno",
        },
        headers=auth_headers,
    )
    assert r3.status_code == 201, r3.text
    body = r3.json()
    assert body["track"]["audio_url"] == "/watt/stream/tracks/legitime-0123abcd4567.wav"
    assert body["track"]["platform"] == "suno"
