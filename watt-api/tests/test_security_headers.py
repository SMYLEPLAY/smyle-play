"""F-02 (2026-09-02) — en-têtes de sécurité HTTP, dont la CSP en Report-Only.

Le middleware ASGI `_SecurityHeadersMiddleware` (app/main.py) pose les en-têtes
sur toutes les réponses SAUF les proxys binaires (`/watt/images`, `/watt/stream`,
`/images`) dont la réponse ne doit pas être modifiée (streaming R2).

La CSP est en `Content-Security-Policy-Report-Only` : aucun blocage, mais tout
script externe injecté, <object>, <base> ou framing tiers est signalé dans la
console. La bascule en enforcement est un ticket séparé.
"""
from httpx import AsyncClient

CSP_HEADER = "content-security-policy-report-only"


async def test_accueil_porte_la_csp_report_only(client: AsyncClient):
    r = await client.get("/")
    assert r.status_code == 200, r.text

    csp = r.headers.get(CSP_HEADER)
    assert csp, "en-tête Content-Security-Policy-Report-Only absent sur /"
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp
    # Report-Only uniquement : pas de CSP bloquante tant que la semaine
    # d'observation n'est pas passée (plan de finition F-02).
    assert "content-security-policy" not in r.headers


async def test_accueil_garde_les_en_tetes_existants(client: AsyncClient):
    r = await client.get("/")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "max-age=" in r.headers.get("strict-transport-security", "")


async def test_health_porte_la_csp(client: AsyncClient):
    """Les réponses JSON de l'API passent aussi par le middleware."""
    r = await client.get("/health")
    assert CSP_HEADER in r.headers


async def test_proxy_stream_sans_csp(client: AsyncClient):
    """Préfixe binaire sauté : aucun en-tête de sécurité ajouté (la réponse
    streaming R2 est transmise telle quelle)."""
    r = await client.get("/watt/stream/x.mp3", follow_redirects=False)
    # 503 (R2 non configuré en test) ou 404 : peu importe, l'en-tête est absent.
    assert r.status_code != 200
    assert CSP_HEADER not in r.headers
    assert "x-content-type-options" not in r.headers
