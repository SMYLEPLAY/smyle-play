"""
Fin binarité (D2) — gate du proxy public /watt/images/{key}.

Contexte : la route compat `watt_compat.serve_image` est enregistrée AVANT
`images.stream_image_preview` dans main.py, donc c'est ELLE qui répond sur
/watt/images/{key}. Avant le fix, elle servait n'importe quelle clé R2 —
y compris les ORIGINAUX gatés (`images/originals/…`), censés passer
exclusivement par GET /images/{id}/download (vérification de possession).

Ces tests verrouillent le gate : un original n'est JAMAIS servi par le
proxy public, en 404 indistinct (anti-énumération), et le gate s'exécute
AVANT tout accès R2 (déterministe même sans R2 configuré en CI).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
async def test_original_key_is_never_served(client: AsyncClient):
    """Une clé images/originals/… → 404, même si l'objet R2 existe."""
    r = await client.get("/watt/images/images/originals/deadbeef.png")
    assert r.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
async def test_original_404_is_indistinct(client: AsyncClient):
    """Le 404 ne révèle ni l'existence de la clé ni la raison du refus."""
    r = await client.get("/watt/images/images/originals/deadbeef.png")
    body = r.json()
    assert body.get("detail") == "Not found"
    assert "originals" not in str(body)


@pytest.mark.asyncio(loop_scope="session")
async def test_non_original_keys_pass_the_gate(client: AsyncClient):
    """
    Les clés publiques (avatars, covers, previews) ne sont PAS bloquées par
    le gate : la requête atteint la couche R2. Sans R2 configuré (CI) c'est
    un 503 explicite, avec R2 c'est le 404 « objet R2 inexistant » — dans
    les deux cas le detail diffère du 404 indistinct du gate.
    """
    r = await client.get("/watt/images/images/avatar/deadbeef.webp")
    assert r.status_code in (404, 503)
    if r.status_code == 404:
        assert r.json().get("detail") != "Not found"
