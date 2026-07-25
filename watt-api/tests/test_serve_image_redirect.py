"""HOTFIX covers (2026-07-25) — serve_image redirige vers l'objet R2 public.

Le proxy boto3 backend a fait disparaître les covers plusieurs fois ; on
redirige désormais les clés images PUBLIQUES vers le domaine public r2.dev.
La gate anti-originals doit rester active.
"""
from httpx import AsyncClient


async def test_serve_image_redirects_cover_to_public(client: AsyncClient):
    r = await client.get(
        "/watt/images/images/track-cover/abc123.png",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    loc = r.headers.get("location", "")
    assert loc.endswith("/images/track-cover/abc123.png"), loc
    assert loc.startswith("https://"), loc


async def test_serve_image_blocks_originals(client: AsyncClient):
    # L'original payant ne doit JAMAIS être servi/redirigé par ce proxy.
    r = await client.get(
        "/watt/images/images/originals/some-uid/x.png",
        follow_redirects=False,
    )
    assert r.status_code == 404, r.text


async def test_serve_image_blocks_non_images_prefix(client: AsyncClient):
    r = await client.get("/watt/images/audio/secret.wav", follow_redirects=False)
    assert r.status_code == 404, r.text
