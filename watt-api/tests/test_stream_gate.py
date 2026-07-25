"""Phase 0 sécurité (2026-07-25) — le proxy audio /watt/stream ne doit JAMAIS
servir une clé image (contournement paywall image via le proxy audio)."""
from httpx import AsyncClient


async def test_stream_refuse_images_originals(client: AsyncClient):
    r = await client.get(
        "/watt/stream/images/originals/some-uid.png", follow_redirects=False
    )
    assert r.status_code == 404, r.text


async def test_stream_refuse_images_previews(client: AsyncClient):
    r = await client.get(
        "/watt/stream/images/previews/some-uid.jpg", follow_redirects=False
    )
    assert r.status_code == 404, r.text
