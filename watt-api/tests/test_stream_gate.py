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


# S-05 (2026-09-02) — liste blanche d'extensions audio (_AUDIO_MIME_BY_EXT) :
# toute clé dont l'extension n'est pas un format audio connu → 404, quel que
# soit le préfixe. Évalué avant la config R2 → 404 déterministe en test.

async def test_stream_refuse_extension_non_audio(client: AsyncClient):
    for key in (
        "PLAYLISTS/x/cover.png",
        "tracks/a.json",
        "tracks/a.webp",
        "voices/x.jpg",
        "originals/secret.PNG",
    ):
        r = await client.get(f"/watt/stream/{key}", follow_redirects=False)
        assert r.status_code == 404, (key, r.text)


async def test_stream_key_sans_extension_refusee(client: AsyncClient):
    for key in ("tracks/sans-extension", "tracks", "tracks/a.", "."):
        r = await client.get(f"/watt/stream/{key}", follow_redirects=False)
        assert r.status_code == 404, (key, r.text)


async def test_stream_extension_audio_passe_la_liste_blanche(client: AsyncClient):
    """Une clé audio légitime dépasse la garde d'extension : sans R2 configuré
    en test on obtient 503 (config), jamais le 404 de la liste blanche."""
    from app.services.r2 import is_configured
    for key in ("tracks/mon-son-0123abcd4567.wav", "tracks/a.MP3", "voices/v.webm",
                "tracks/Mon Son.m4a"):
        r = await client.get(f"/watt/stream/{key}", follow_redirects=False)
        if is_configured():
            # Objet inexistant sur un vrai bucket → 404 « introuvable » (R2),
            # pas la garde : on ne peut pas distinguer ici, on tolère.
            assert r.status_code in (200, 404), (key, r.status_code)
        else:
            assert r.status_code == 503, (key, r.text)
