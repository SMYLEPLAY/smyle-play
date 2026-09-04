"""F3-1 — funnel creator-led : whitelist d'événements + attribution créateur.

Garde-fou principal : la liste blanche du front (ui/core/telemetry.js) et
celle du backend (app/services/analytics.py) doivent rester alignées. Un
événement émis mais non whitelisté côté serveur est silencieusement jeté —
la donnée est alors perdue SANS erreur visible, ce qui est le pire cas.
"""

import re
from pathlib import Path

from app.services.analytics import ALLOWED_EVENTS

REPO_ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_JS = REPO_ROOT / "ui" / "core" / "telemetry.js"

# Événements du funnel creator-led (F3-1) : sans eux, la beta ne mesure rien.
FUNNEL_CREATOR_LED = {
    "creator_visit",
    "share_click",
    "listen_30s",
    "unlock_click",
    "adn_reuse",
    "trade",
    "review",
    "topup_click",
}


def _js_allowed() -> set[str]:
    src = TELEMETRY_JS.read_text(encoding="utf-8")
    m = re.search(r"var ALLOWED = \[(.*?)\];", src, re.S)
    assert m, "tableau ALLOWED introuvable dans telemetry.js"
    return set(re.findall(r"'([a-z0-9_]+)'", m.group(1)))


def test_funnel_creator_led_whiteliste_backend():
    manquants = FUNNEL_CREATOR_LED - ALLOWED_EVENTS
    assert not manquants, f"événements non whitelistés côté serveur : {manquants}"


def test_front_et_backend_alignes():
    js = _js_allowed()
    orphelins = js - ALLOWED_EVENTS
    assert not orphelins, (
        f"le front émet des événements que le serveur jette : {orphelins}"
    )


def test_front_emet_bien_le_funnel_creator_led():
    manquants = FUNNEL_CREATOR_LED - _js_allowed()
    assert not manquants, f"événements absents du front : {manquants}"


def test_attribution_presente_dans_le_front():
    src = TELEMETRY_JS.read_text(encoding="utf-8")
    # Premier touche, TTL, capture depuis /u/<slug>, /@<slug> et ?ref=
    assert "smyle_attrib" in src
    assert "ATTRIB_TTL_MS" in src
    assert "_creatorFromPath" in src
    assert "attribution:" in src, "accesseur public SmyleTrack.attribution manquant"


def test_pas_de_pii_ajoutee_par_l_attribution():
    """L'attribution ne doit transporter QUE le slug public + la source."""
    src = TELEMETRY_JS.read_text(encoding="utf-8")
    m = re.search(r"function _captureAttrib\(\).*?\n  \}", src, re.S)
    assert m, "_captureAttrib introuvable"
    corps = m.group(0)
    for interdit in ("email", "userAgent", "navigator.userAgent", "ip"):
        assert interdit not in corps, f"donnée interdite dans l'attribution : {interdit}"
