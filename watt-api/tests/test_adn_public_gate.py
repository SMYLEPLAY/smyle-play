"""
S-04 sécurité (2026-09-02) — gate du génome ADN sur les surfaces publiques
(audit A §B5).

`/watt/adns`, `/watt/adns/{slug}` et `/catalog/adns*` servaient
`description` (le génome vendu), `usageGuide` et `exampleOutputs` sans
authentification, alors que la page artiste applique depuis le 2026-05-13
un gate strict (longueur + booléens). Ces tests vérifient que le contenu
payant ne sort plus que par `/me/library/adns` (possession vérifiée).
Postgres requis (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, text

from app.database import SessionLocal
from app.models.adn import Adn
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_GENOME = "GENOME-SECRET-" + "X" * 240
_GUIDE = "GUIDE-SECRET how to use it"
_EXAMPLES = "EXAMPLES-SECRET premium outputs"
_CAMEL_LEAK = {"description", "usageGuide", "exampleOutputs"}
_SNAKE_LEAK = {"description", "usage_guide", "example_outputs"}


async def _seed_artist_with_adn() -> tuple[uuid.UUID, uuid.UUID, str]:
    """Crée un artiste publié + un ADN publié ; renvoie (user_id, adn_id, slug)."""
    suffix = uuid.uuid4().hex[:10]
    email = f"pytest-adn-{suffix}@smyleplay.example"
    artist_name = f"Gate Artist {suffix}"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        user_id = user.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET artist_name = :n, profile_public = true WHERE id = :u"),
            {"n": artist_name, "u": user_id},
        )
        adn = Adn(
            artist_id=user_id,
            description=_GENOME,
            usage_guide=_GUIDE,
            example_outputs=_EXAMPLES,
            price_credits=50,
            is_published=True,
        )
        db.add(adn)
        await db.commit()
        await db.refresh(adn)
        adn_id = adn.id
    from app.core.slug import slugify
    return user_id, adn_id, slugify(artist_name)


async def _cleanup(user_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Adn).where(Adn.artist_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def _assert_no_leak(item: dict, leak_keys: set[str]) -> None:
    assert not (set(item) & leak_keys), f"génome exposé : {set(item) & leak_keys}"
    blob = str(item)
    assert "SECRET" not in blob, blob


async def test_watt_adns_list_has_no_genome(client):
    user_id, adn_id, _ = await _seed_artist_with_adn()
    try:
        r = await client.get("/watt/adns")
        assert r.status_code == 200, r.text
        adns = r.json()["adns"]
        mine = [a for a in adns if a["id"] == str(adn_id)]
        assert len(mine) == 1
        for item in adns:
            _assert_no_leak(item, _CAMEL_LEAK)
            assert "characterCount" in item
            assert "hasUsageGuide" in item and "hasExampleOutputs" in item
        assert mine[0]["characterCount"] == len(_GENOME)
        assert mine[0]["hasUsageGuide"] is True
        assert mine[0]["hasExampleOutputs"] is True
        assert mine[0]["priceCredits"] == 50
    finally:
        await _cleanup(user_id)


async def test_watt_adn_detail_has_no_genome(client):
    user_id, adn_id, slug = await _seed_artist_with_adn()
    try:
        r = await client.get(f"/watt/adns/{slug}")
        assert r.status_code == 200, r.text
        adn = r.json()["adn"]
        assert adn["id"] == str(adn_id)
        _assert_no_leak(adn, _CAMEL_LEAK)
        assert adn["characterCount"] == len(_GENOME)
        assert adn["hasUsageGuide"] is True and adn["hasExampleOutputs"] is True
        # La page artiste applique le même gate (source unique _adn_public_teaser).
        r2 = await client.get(f"/watt/artists/{slug}")
        assert r2.status_code == 200, r2.text
        body = r2.text
        assert "GENOME-SECRET" not in body and "GUIDE-SECRET" not in body
        assert "EXAMPLES-SECRET" not in body
    finally:
        await _cleanup(user_id)


async def test_catalog_adns_has_no_genome(client):
    user_id, adn_id, _ = await _seed_artist_with_adn()
    try:
        r = await client.get("/catalog/adns", params={"artist_id": str(user_id)})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert [i["id"] for i in items] == [str(adn_id)]
        for item in items:
            _assert_no_leak(item, _SNAKE_LEAK)
        assert items[0]["description_length"] == len(_GENOME)
        assert items[0]["has_usage_guide"] is True
        assert items[0]["has_example_outputs"] is True

        r = await client.get(f"/catalog/adns/{adn_id}")
        assert r.status_code == 200, r.text
        _assert_no_leak(r.json(), _SNAKE_LEAK)
        assert r.json()["description_length"] == len(_GENOME)
    finally:
        await _cleanup(user_id)
