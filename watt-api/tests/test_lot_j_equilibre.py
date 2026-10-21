"""Lot J — équilibre de la plateforme (audit du 21/10/2026).

  - un nouveau créateur peut mettre une recette en vente SANS ADN ;
  - un titre court (2 caractères) est accepté ;
  - ElevenLabs Music et les nouveaux outils d'image sont acceptés ;
  - l'arrondi du partage va au créateur, la plateforme garde au moins 10 % ;
  - les ADN sont masqués par défaut au lancement (SHOW_ADN) ;
  - messages d'achat en français.
"""
import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal
from app.models.prompt import Prompt
from app.services.credits import compute_split
from app.services.reserve import PAYOUT_RATE_CENTS
from app.services.tiers import COMMISSION_PLANCHER_PCT

RECETTE = ("Lo-fi hip hop nocturne, piano feutré, basse ronde, batterie douce "
           "et pluie en fond, ambiance ville la nuit, 78 bpm, voix absente.")


def _payload(**extra):
    p = {
        "title": "Nuit",
        "prompt_text": RECETTE,
        "price_credits": 20,
        "prompt_platform": "suno",
        "prompt_model_version": "Suno v6",
        "prompt_vocal_gender": "instrumental",
        "is_published": True,
    }
    p.update(extra)
    return p


async def _nettoie(user_id):
    async with SessionLocal() as db:
        await db.execute(delete(Prompt).where(Prompt.artist_id == user_id))
        await db.commit()


# ── Publier une recette sans ADN ────────────────────────────────────────────

async def test_recette_sans_adn_et_titre_court(client, test_user, auth_headers):
    try:
        r = await client.post("/artist/me/prompts", headers=auth_headers, json=_payload())
        assert r.status_code == 201, r.text
        assert r.json()["title"] == "Nuit"
    finally:
        await _nettoie(test_user["id"])


async def test_reglages_suno_facultatifs(client, test_user, auth_headers):
    try:
        r = await client.post("/artist/me/prompts", headers=auth_headers,
                              json=_payload(title="Sans réglages"))
        assert r.status_code == 201, r.text
    finally:
        await _nettoie(test_user["id"])


async def test_elevenlabs_accepte(client, test_user, auth_headers):
    try:
        r = await client.post("/artist/me/prompts", headers=auth_headers,
                              json=_payload(title="Onze", prompt_platform="elevenlabs",
                                            prompt_model_version="Eleven Music v1"))
        assert r.status_code == 201, r.text
    finally:
        await _nettoie(test_user["id"])


async def test_titre_d_un_caractere_refuse(client, test_user, auth_headers):
    r = await client.post("/artist/me/prompts", headers=auth_headers, json=_payload(title="N"))
    assert r.status_code == 422


@pytest.mark.parametrize("outil", ["chatgpt", "ideogram", "leonardo", "firefly",
                                   "google", "recraft", "seedream", "grok"])
def test_nouveaux_outils_image(outil):
    from typing import get_args

    from app.routers.images import _VALID_PLATFORMS
    from app.schemas.image import ImagePlatform

    assert outil in get_args(ImagePlatform)
    assert outil in _VALID_PLATFORMS


# ── Partage : arrondi au créateur, plancher garanti ─────────────────────────

@pytest.mark.parametrize("part", [80, 88, 90])
def test_partage_arrondi_createur_plancher_garanti(part):
    for prix in range(1, 301):
        artiste, commission = compute_split(prix, part)
        assert artiste + commission == prix
        assert artiste >= prix * part // 100, (prix, part)
        # Plancher : la plateforme garde toujours ≥ 10 % (arrondi supérieur)…
        assert commission * 100 >= prix * COMMISSION_PLANCHER_PCT, (prix, part)
        # … donc un Smyle gagné ne se rachète jamais plus cher qu'il ne s'est
        # vendu (0,9 × 5 c ≤ 4,9 c net, règle d'or de l'économie).
        assert artiste * PAYOUT_RATE_CENTS <= prix * 4.9, (prix, part)


def test_avantages_visibles_aux_prix_conseilles():
    assert compute_split(20, 80) == (16, 4)
    assert compute_split(20, 90) == (18, 2)     # Pionnier : 10 % exact
    assert compute_split(45, 88) == (40, 5)     # Premium mieux payé qu'avant (39)


# ── Simplification et textes ────────────────────────────────────────────────

def test_adn_masques_par_defaut():
    assert settings.SHOW_ADN is False
    assert settings.launch_flags_dict()["adn"] is False


async def test_drapeau_adn_expose_au_front(client):
    r = await client.get("/ui/core/launch-flags.js")
    assert '"adn": false' in r.text


def test_messages_d_achat_en_francais():
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "app"
    for f in ("services/unlocks.py", "routers/unlocks.py", "routers/catalog.py",
              "services/marketplace.py"):
        src = (racine / f).read_text(encoding="utf-8")
        for anglais in ("must create an ADN", "cannot unlock their own",
                        "Failed to unlock", "Concurrent unlock conflict",
                        "not found or not published", "Insufficient credits"):
            assert anglais not in src, (f, anglais)
