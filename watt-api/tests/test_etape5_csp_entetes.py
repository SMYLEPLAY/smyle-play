"""Étape 5 (2026-10-02) — CSP qui bloque (interrupteur), rapports de
violation, Permissions-Policy, cookies durcis, inventaire des ressources."""
import logging
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core import securite

REPO = Path(__file__).resolve().parents[2]


# ── Interrupteur CSP_ENFORCE ───────────────────────────────────────────────

async def test_csp_report_only_par_defaut(client, monkeypatch):
    monkeypatch.setattr(settings, "CSP_ENFORCE", False)
    r = await client.get("/")
    ro = r.headers.get("content-security-policy-report-only", "")
    assert "default-src 'self'" in ro
    assert "report-uri /securite/csp-rapport" in ro
    assert "content-security-policy" not in r.headers


async def test_csp_bloquante_quand_allumee(client, monkeypatch):
    monkeypatch.setattr(settings, "CSP_ENFORCE", True)
    r = await client.get("/")
    csp = r.headers.get("content-security-policy", "")
    assert csp == securite.POLITIQUE_CSP
    assert "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
    assert "content-security-policy-report-only" not in r.headers


async def test_csp_jamais_sur_les_proxys_binaires(client, monkeypatch):
    monkeypatch.setattr(settings, "CSP_ENFORCE", True)
    r = await client.get("/watt/stream/x.mp3", follow_redirects=False)
    assert "content-security-policy" not in r.headers


# ── En-têtes de durcissement ───────────────────────────────────────────────

async def test_entetes_de_durcissement(client):
    r = await client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "max-age=63072000" in r.headers["strict-transport-security"]
    pp = r.headers["permissions-policy"]
    for item in ("camera=()", "microphone=()", "geolocation=()", "payment=()"):
        assert item in pp


async def test_health_porte_les_entetes(client):
    r = await client.get("/health")
    assert "permissions-policy" in r.headers


# ── Cookies ────────────────────────────────────────────────────────────────

def test_durcir_cookie():
    assert securite.durcir_cookie("a=1", https=True) == "a=1; HttpOnly; SameSite=Lax; Secure"
    assert securite.durcir_cookie("a=1", https=False) == "a=1; HttpOnly; SameSite=Lax"
    deja = "a=1; Path=/; Secure; HttpOnly; SameSite=Strict"
    assert securite.durcir_cookie(deja, https=True) == deja


async def test_middleware_durcit_les_cookies():
    mini = FastAPI()

    @mini.get("/c")
    async def c():
        r = JSONResponse({"ok": True})
        r.set_cookie("session", "x")
        r.set_cookie("pref", "y", samesite="strict")
        return r

    app = securite.SecurityHeadersMiddleware(mini)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/c", headers={"X-Forwarded-Proto": "https"})
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for ck in cookies:
        low = ck.lower()
        assert "httponly" in low and "secure" in low and "samesite" in low
    assert any("samesite=strict" in ck.lower() for ck in cookies)


# ── Rapports de violation ──────────────────────────────────────────────────

async def test_rapport_csp_journalise_sans_secret(client, caplog):
    rapport = {"csp-report": {
        "document-uri": "https://smyleplay.com/reset?token=SECRET-JETON#frag",
        "effective-directive": "script-src-elem",
        "blocked-uri": "https://evil.example/x.js?k=SECRET2",
    }}
    with caplog.at_level(logging.WARNING, logger="app.core.securite"):
        r = await client.post(
            "/securite/csp-rapport", json=rapport,
            headers={"Content-Type": "application/csp-report"},
        )
    assert r.status_code == 204
    assert "[csp] violation" in caplog.text
    assert "script-src-elem" in caplog.text
    assert "https://evil.example/x.js" in caplog.text
    assert "SECRET" not in caplog.text


@pytest.mark.parametrize("corps", [b"pas du json", b"[]", b'{"autre": 1}', b"x" * 20000])
async def test_rapport_csp_invalide_ignore(client, corps):
    r = await client.post(
        "/securite/csp-rapport", content=corps,
        headers={"Content-Type": "application/csp-report"},
    )
    assert r.status_code == 204


def test_adresse_sans_secret():
    f = securite._adresse_sans_secret
    assert f("https://a.fr/p?t=1#x") == "https://a.fr/p"
    assert f("inline") == "inline"
    assert f("data:image/png;base64,AAAA") == "data"
    assert f(None) == "-"
    assert "\n" not in f("https://a.fr/\nFAUX LOG")


# ── Inventaire : aucune ressource externe chargée par les pages ────────────
# Garde-fou pour le jour où CSP_ENFORCE sera allumé : si quelqu'un ajoute un
# script / une feuille de style / une police venant d'un autre site, ce test
# casse et rappelle d'ajuster POLITIQUE_CSP (sinon la page casserait en prod).

_CHARGEMENT_EXTERNE = re.compile(
    r"<(?:script|link|iframe|embed|object)\b[^>]*\b(?:src|href)\s*=\s*[\"']"
    r"(?:https?:)?//",
    re.IGNORECASE,
)
_IMPORT_CSS_EXTERNE = re.compile(r"@import\s+(?:url\()?[\"']?(?:https?:)?//", re.IGNORECASE)


def _fichiers_front() -> list[Path]:
    try:
        sortie = subprocess.run(
            ["git", "ls-files", "*.html", "*.css", "*.js"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.split()
    except Exception:
        pytest.skip("git indisponible")
    exclus = ("e2e/", "watt-api/_archive", "agents/", "node_modules/")
    return [REPO / p for p in sortie if not p.startswith(exclus)]


def test_aucune_ressource_externe_dans_les_pages():
    fautifs = []
    for chemin in _fichiers_front():
        try:
            texte = chemin.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _CHARGEMENT_EXTERNE.search(texte) or _IMPORT_CSS_EXTERNE.search(texte):
            fautifs.append(str(chemin.relative_to(REPO)))
    assert not fautifs, (
        "Ressource externe ajoutée : mettre à jour POLITIQUE_CSP "
        f"(app/core/securite.py) avant d'allumer CSP_ENFORCE → {fautifs}"
    )
