"""P0-b « Sortie Flask » — tests du router pages + launch-flags + allowlist statique.

Tests DB-free : on construit une mini-app FastAPI avec uniquement le router
pages + le mount statique (aucune fixture Postgres nécessaire). La parité
visée est celle de flask_app.py (cf. app/routers/pages.py, docstring).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers.pages import launch_flags_js_body, mount_static, router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    mount_static(app)
    return TestClient(app, follow_redirects=False)


# ── launch-flags.js ────────────────────────────────────────────────────────

def test_launch_flags_body_masque_par_defaut(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_PALIERS", False)
    body = launch_flags_js_body()
    assert body.startswith("window.WATT_LAUNCH = ")
    assert '"paliers": false' in body


def test_launch_flags_body_rallume_par_show(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_PALIERS", True)
    assert '"paliers": true' in launch_flags_js_body()


def test_launch_flags_expose_achat_smyles_masque_par_defaut(monkeypatch):
    """S-11 (annexe A §M5) — l'achat de Smyles est un item de mode lancement.

    Sans ce drapeau, le clic sur le badge solde ouvrait une grille tarifaire
    puis échouait en 403 (`POST /credits/grant` est réservé à `is_official`) :
    une promesse d'achat que rien ne pouvait honorer. Le front lit la clé
    `achatSmyles` — si elle disparaissait du JS servi, le repli statique
    (« tout masqué ») prendrait le relais, mais silencieusement.
    """
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", False)
    assert '"achatSmyles": false' in launch_flags_js_body()
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    assert '"achatSmyles": true' in launch_flags_js_body()


def test_launch_flags_expose_euros_masque_par_defaut(monkeypatch):
    """K-08 (annexe B §5) — le front lit `euros` pour masquer la grille
    « Repere SMYLES » et les previews « ≈ X€ ». Si la cle disparaissait du JS
    servi, le repli statique (« tout masque ») prendrait le relais en silence.
    """
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_EUROS", False)
    assert '"euros": false' in launch_flags_js_body()
    monkeypatch.setattr(settings, "SHOW_EUROS", True)
    assert '"euros": true' in launch_flags_js_body()


def test_tarifs_gate_euros(monkeypatch):
    """/tarifs suit `euros`, pas `paliers` : ouvrir les paliers (commission,
    mise en avant) n'ouvre pas pour autant un mur de paiement inactif."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_PALIERS", True)
    monkeypatch.setattr(settings, "SHOW_EUROS", False)
    r = _client().get("/tarifs")
    assert r.status_code == 302
    assert r.headers["location"] == "/"

    monkeypatch.setattr(settings, "SHOW_EUROS", True)
    assert _client().get("/tarifs").status_code == 200


def test_launch_flags_endpoint_no_cache():
    r = _client().get("/ui/core/launch-flags.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert r.text.startswith("window.WATT_LAUNCH = ")


# ── Pages ──────────────────────────────────────────────────────────────────

def test_index_et_shells():
    c = _client()
    for path in ("/", "/sons", "/beats", "/artistes"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert "text/html" in r.headers["content-type"], path


def test_watt_redirige_accueil_301():
    r = _client().get("/watt")
    assert r.status_code == 301
    assert r.headers["location"] == "/"


def test_profil_u_et_arobase():
    c = _client()
    assert c.get("/u/tom").status_code == 200
    assert c.get("/@tom").status_code == 200


def test_oeuvre_page_servie():
    # L-03 (reprise PR #489) : la route de page /oeuvre/<slug> avait disparu
    # à la sortie de Flask (P0-b) → 404 sur LA page qu'un créateur partage.
    # Slug inconnu ⇒ page brute (aucune méta injectée), mais toujours 200.
    r = _client().get("/oeuvre/slug-inexistant-l03")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_comment_ca_marche_servie():
    # K-03 : /comment-ca-marche est linké par l'onboarding
    # (ui/core/onboarding.js) mais aucune route de page ne le servait —
    # le mount statique ne résout que /comment-ca-marche.html → 404.
    r = _client().get("/comment-ca-marche")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_alias_artiste_301_vers_u():
    r = _client().get("/artiste/tom")
    assert r.status_code == 301
    assert r.headers["location"] == "/u/tom"


def test_offres_gate_paliers(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_PALIERS", False)
    r = _client().get("/offres")
    assert r.status_code == 302 and r.headers["location"] == "/"
    monkeypatch.setattr(settings, "SHOW_PALIERS", True)
    assert _client().get("/offres").status_code == 200


def test_voix_gate(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_VOIX", False)
    r = _client().get("/voix")
    assert r.status_code == 302 and r.headers["location"] == "/"


# ── Statiques : allowlist ──────────────────────────────────────────────────

def test_assets_front_servis():
    c = _client()
    assert c.get("/style.css").status_code == 200
    assert c.get("/dashboard.js").status_code == 200


def test_sources_et_dotfiles_bloques():
    c = _client()
    # Flask exposait ces fichiers ; FastAPI doit répondre 404.
    for path in ("/flask_app.py", "/models.py", "/main.py", "/.env",
                 "/requirements.txt", "/railway.toml", "/Procfile"):
        assert c.get(path).status_code == 404, path
