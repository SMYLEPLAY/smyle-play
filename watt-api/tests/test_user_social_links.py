"""
S-03 sécurité (2026-09-02) — liens sociaux du profil (`UserUpdate`).

Audit A §B4 : les 6 champs sociaux étaient stockés tels quels et posés en
`href` sur la page publique /u/<slug> (`javascript:` accepté). Règle serveur
`validate_social_link` :
  - instagram / tiktok / twitter_x : `@pseudo` ou `pseudo` → stocké nu ;
  - soundcloud / youtube / spotify : URL http(s) uniquement ;
  - `domaine.tld/…` sans schéma → préfixé `https://` ;
  - `javascript:`, `data:`, guillemets, chevrons, contrôle → 422.

Partie 1 : schéma pur (DB-free). Partie 2 : `PATCH /users/me` (Postgres).
"""
import pytest
from pydantic import ValidationError

from app.schemas.user import UserUpdate, validate_social_link

_SOCIAL_FIELDS = ("soundcloud", "instagram", "youtube", "tiktok", "spotify", "twitter_x")


# ── Partie 1 — schéma (DB-free) ──────────────────────────────────────────────

@pytest.mark.parametrize("field", _SOCIAL_FIELDS)
@pytest.mark.parametrize(
    "piege",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        'https://soundcloud.com/x" onclick="alert(1)',
        "https://x.com/<script>",
        "https://x.com/a'b",
        "https://x.com/a`b",
        "https://x.com/a\nb",
        "ftp://x.com/a",
    ],
)
def test_social_rejects_javascript_scheme(field: str, piege: str) -> None:
    with pytest.raises(ValidationError):
        UserUpdate(**{field: piege})


def test_social_handle_normalized() -> None:
    assert UserUpdate(instagram="@toto").instagram == "toto"
    assert UserUpdate(instagram="toto").instagram == "toto"
    assert UserUpdate(tiktok="@ma.chaine_1").tiktok == "ma.chaine_1"
    assert UserUpdate(twitter_x="  @x_user  ").twitter_x == "x_user"
    # Pas de notion de pseudo nu pour soundcloud/youtube/spotify → 422.
    for field in ("soundcloud", "youtube", "spotify"):
        with pytest.raises(ValidationError):
            UserUpdate(**{field: "@toto"})
        with pytest.raises(ValidationError):
            UserUpdate(**{field: "toto"})


@pytest.mark.parametrize("field", _SOCIAL_FIELDS)
def test_social_accepts_https(field: str) -> None:
    url = "https://example.com/artiste/toto?x=1"
    assert UserUpdate(**{field: url}).model_dump()[field] == url
    assert UserUpdate(**{field: "http://example.com/toto"}).model_dump()[field] == "http://example.com/toto"
    # Vide → None (l'utilisateur retire son lien), comme avant.
    assert UserUpdate(**{field: ""}).model_dump()[field] is None
    assert UserUpdate(**{field: "   "}).model_dump()[field] is None


def test_social_bare_domain_gets_https() -> None:
    assert UserUpdate(soundcloud="soundcloud.com/toto").soundcloud == "https://soundcloud.com/toto"
    assert UserUpdate(instagram="instagram.com/toto").instagram == "https://instagram.com/toto"
    assert UserUpdate(youtube="www.youtube.com/@toto").youtube == "https://www.youtube.com/@toto"


def test_validate_social_link_length_bound() -> None:
    long_url = "https://example.com/" + "a" * 500
    with pytest.raises(ValueError):
        validate_social_link(long_url, allow_handle=False)
    assert validate_social_link(None, allow_handle=False) is None
    assert validate_social_link("", allow_handle=True) is None


def test_genre_city_unchanged() -> None:
    # empty_string_to_none reste en place pour genre / city.
    u = UserUpdate(genre="  ", city=" Paris ")
    assert u.genre is None
    assert u.city == "Paris"


# ── Partie 2 — PATCH /users/me (Postgres) ────────────────────────────────────

async def test_patch_users_me_social_links(client, test_user, auth_headers):
    r = await client.patch(
        "/users/me", json={"soundcloud": "javascript:alert(1)"}, headers=auth_headers
    )
    assert r.status_code == 422, r.text

    r = await client.patch("/users/me", json={"instagram": "@toto"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["instagram"] == "toto"

    r = await client.patch(
        "/users/me",
        json={"soundcloud": "https://soundcloud.com/toto", "youtube": ""},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["soundcloud"] == "https://soundcloud.com/toto"
    assert r.json()["youtube"] is None

    r = await client.patch(
        "/users/me", json={"artist_name": 'x"><img src=x onerror=alert(1)>'}, headers=auth_headers
    )
    assert r.status_code == 422, r.text

    r = await client.patch(
        "/users/me", json={"avatar_url": '/x" onload="alert(1)'}, headers=auth_headers
    )
    assert r.status_code == 422, r.text

    r = await client.patch(
        "/users/me",
        json={"avatar_url": "/watt/images/images/avatars/a.jpg"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"] == "/watt/images/images/avatars/a.jpg"
