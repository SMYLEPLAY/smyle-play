"""Lot 1 (pré-lancement) — 6 fonctionnalités cachées au lancement.

Offres ADN, messagerie, série quotidienne, trophées, beats, albums :
construites mais masquées par le MODE LANCEMENT, rallumables une par une par
variable d'environnement (même modèle que la revente).

Vérifie :
  - caché par défaut → 404 « Fonction indisponible pendant le lancement » ;
  - rallumé → la route répond normalement ;
  - « caché = inerte » : aucun Smyle crédité en arrière-plan (trophées, série) ;
  - un beat ne peut plus s'acheter par la route générique de déblocage ;
  - ce qui NE DOIT PAS être caché ne l'est pas : Œuvre son+image (links),
    playlists, téléchargement universel des exemplaires possédés ;
  - les données existantes sont intactes et réapparaissent au rallumage.
"""
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import AchievementAxis
from app.models.prompt import Prompt
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.achievements import check_and_grant_achievements
from app.services.unlocks import PromptNotPurchasable, unlock_prompt_atomic
from app.services.users import create_user

LAUNCH_404 = "Fonction indisponible pendant le lancement."

NOUVEAUX = {
    "offresAdn": "SHOW_OFFRES_ADN",
    "messagerie": "SHOW_MESSAGERIE",
    "serie": "SHOW_SERIE",
    "trophees": "SHOW_TROPHEES",
    "beats": "SHOW_BEATS",
    "albums": "SHOW_ALBUMS",
}

# (drapeau, méthode, chemin) — un point d'entrée représentatif par route gatée.
ROUTES = [
    ("SHOW_OFFRES_ADN", "get", "/adn-offers/me"),
    ("SHOW_MESSAGERIE", "get", "/messages/threads"),
    ("SHOW_SERIE", "get", "/streak/me"),
    ("SHOW_SERIE", "post", "/streak/checkin"),
    ("SHOW_TROPHEES", "get", "/achievements"),
    ("SHOW_TROPHEES", "get", "/me/achievements"),
    ("SHOW_BEATS", "post", "/artist/me/beats"),
    ("SHOW_BEATS", "post", f"/pack/{uuid.uuid4()}/buy"),
    ("SHOW_ALBUMS", "get", "/albums/me"),
    ("SHOW_ALBUMS", "get", f"/watt/albums/{uuid.uuid4()}"),
    ("SHOW_ALBUMS", "post", f"/unlocks/album-adn/{uuid.uuid4()}"),
    ("SHOW_ALBUMS", "get", "/catalog/albums-adn"),
    # Lot 2 : Collection (playlist + album, ex-« œuvre » C3) cachée avec les albums.
    ("SHOW_ALBUMS", "get", "/watt/oeuvre/un-slug"),
    ("SHOW_ALBUMS", "post", "/artist/me/oeuvre"),
]


def _is_launch_404(r) -> bool:
    return r.status_code == 404 and r.json().get("detail") == LAUNCH_404


# ─── 1. Configuration ─────────────────────────────────────────────────────────

def test_les_6_drapeaux_existent_et_sont_caches_par_defaut():
    flags = settings.launch_flags_dict()
    for cle in NOUVEAUX:
        assert cle in flags
        assert flags[cle] is False, f"{cle} doit être caché par défaut"


async def test_drapeaux_exposes_au_front(client):
    r = await client.get("/ui/core/launch-flags.js")
    assert r.status_code == 200
    for cle in NOUVEAUX:
        assert f'"{cle}": false' in r.text


# ─── 2. Routes : cachées par défaut, rallumables une par une ─────────────────

@pytest.mark.parametrize("flag, methode, chemin", ROUTES)
async def test_route_cachee_par_defaut(client, auth_headers, flag, methode, chemin):
    r = await getattr(client, methode)(chemin, headers=auth_headers)
    assert _is_launch_404(r), (chemin, r.status_code, r.text)


@pytest.mark.parametrize("flag, methode, chemin", ROUTES)
async def test_route_rallumee_par_son_drapeau(client, auth_headers, monkeypatch, flag, methode, chemin):
    monkeypatch.setattr(settings, flag, True)
    r = await getattr(client, methode)(chemin, headers=auth_headers)
    # Rallumée : la route répond (succès, validation, ressource absente…),
    # mais plus JAMAIS avec le 404 du mode lancement.
    assert not _is_launch_404(r), (chemin, r.status_code, r.text)


async def test_rallumage_global_par_fin_du_mode_lancement(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", False)
    for _flag, methode, chemin in ROUTES:
        r = await getattr(client, methode)(chemin, headers=auth_headers)
        assert not _is_launch_404(r), chemin


# ─── 3. Ce qui ne doit PAS être caché ─────────────────────────────────────────

@pytest.mark.parametrize(
    "methode, chemin",
    [
        ("get", f"/artist/me/prompts/{uuid.uuid4()}/linkable"),   # Œuvre son+image
        ("get", "/playlists/me"),                                  # playlists
        ("get", f"/beats/{uuid.uuid4()}/download"),               # téléchargement universel
        ("get", f"/products/{uuid.uuid4()}/download"),
    ],
)
async def test_non_caches(client, auth_headers, methode, chemin):
    r = await getattr(client, methode)(chemin, headers=auth_headers)
    assert not _is_launch_404(r), (chemin, r.status_code, r.text)


# ─── 4. Caché = INERTE ────────────────────────────────────────────────────────

async def _user(balance: int = 0) -> uuid.UUID:
    email = f"pytest-lot1-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET credits_balance = :b, smyles_achetes = :b, "
                 "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :u"),
            {"b": balance, "u": uid},
        )
        await db.commit()
    return uid


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _bonus_trophees(uid) -> int:
    async with SessionLocal() as db:
        n = (await db.execute(
            text("SELECT count(*) FROM transactions WHERE buyer_id = :u "
                 "AND metadata_json->>'reason' LIKE 'achievement:%'"),
            {"u": uid},
        )).scalar_one()
    return int(n)


async def _publier_image(uid) -> None:
    """Une image publiée = progression sur l'axe « image_creator » (palier 1 :
    5 Smyles de récompense)."""
    async with SessionLocal() as db:
        db.add(Prompt(
            artist_id=uid, title="Image de test", description="Tagline",
            prompt_text="X" * 120, price_credits=10, is_published=True,
            product_type="image", image_platform="midjourney",
            image_model_version="v6",
        ))
        await db.commit()


async def test_trophees_caches_ne_creditent_rien(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_TROPHEES", False)
    uid = await _user()
    try:
        await _publier_image(uid)
        async with SessionLocal() as db:
            out = await check_and_grant_achievements(
                db, user_id=uid, axis=AchievementAxis.IMAGE_CREATOR)
            await db.commit()
        assert out == []                          # rien débloqué
        assert await _bonus_trophees(uid) == 0     # rien crédité
    finally:
        await _cleanup(uid)


async def test_trophees_rallumes_rattrapent_les_paliers_atteints(monkeypatch):
    """Paliers cumulatifs : rallumés, la prochaine action débloque ce qui était
    atteint pendant la période cachée (comportement à connaître pour M1)."""
    uid = await _user()
    try:
        monkeypatch.setattr(settings, "SHOW_TROPHEES", False)
        await _publier_image(uid)                  # progression pendant « caché »
        monkeypatch.setattr(settings, "SHOW_TROPHEES", True)
        async with SessionLocal() as db:
            out = await check_and_grant_achievements(
                db, user_id=uid, axis=AchievementAxis.IMAGE_CREATOR)
            await db.commit()
        assert len(out) >= 1
        assert await _bonus_trophees(uid) >= 1
    finally:
        await _cleanup(uid)


async def test_serie_cachee_ne_credite_rien(client, test_user, auth_headers):
    async with SessionLocal() as db:
        avant = (await db.execute(text("SELECT credits_balance FROM users WHERE id = :u"),
                                  {"u": test_user["id"]})).scalar_one()
    r = await client.post("/streak/checkin", headers=auth_headers)
    assert _is_launch_404(r)
    async with SessionLocal() as db:
        apres = (await db.execute(text("SELECT credits_balance FROM users WHERE id = :u"),
                                  {"u": test_user["id"]})).scalar_one()
    assert apres == avant


async def _beat(artist) -> uuid.UUID:
    async with SessionLocal() as db:
        b = Prompt(artist_id=artist, title="Beat de test", description="Tagline",
                   prompt_text=None, price_credits=20, is_published=True,
                   product_type="beat", license_type="lease")
        db.add(b)
        await db.commit()
        await db.refresh(b)
        return b.id


async def test_beat_cache_non_achetable_par_la_route_generique(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_BEATS", False)
    artiste, acheteur = await _user(), await _user(1000)
    try:
        bid = await _beat(artiste)
        with pytest.raises(PromptNotPurchasable):
            async with SessionLocal() as db:
                await unlock_prompt_atomic(db, buyer_id=acheteur, prompt_id=bid)
        async with SessionLocal() as db:
            solde = (await db.execute(text("SELECT credits_balance FROM users WHERE id = :u"),
                                      {"u": acheteur})).scalar_one()
        assert solde == 1000                       # aucun débit
    finally:
        await _cleanup(artiste, acheteur)


async def test_beat_rallume_achetable(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_BEATS", True)
    artiste, acheteur = await _user(), await _user(1000)
    try:
        bid = await _beat(artiste)
        async with SessionLocal() as db:
            await unlock_prompt_atomic(db, buyer_id=acheteur, prompt_id=bid)
            await db.commit()
    finally:
        await _cleanup(artiste, acheteur)


# ─── 5. Données intactes, réapparaissent au rallumage ─────────────────────────

async def test_album_intact_et_de_retour_au_rallumage(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ALBUMS", True)
    r = await client.post("/albums", headers=auth_headers, json={"title": "Mon album"})
    assert r.status_code == 201, r.text
    album_id = r.json()["id"]

    monkeypatch.setattr(settings, "SHOW_ALBUMS", False)      # on cache
    r = await client.get(f"/albums/{album_id}", headers=auth_headers)
    assert _is_launch_404(r)
    async with SessionLocal() as db:                         # toujours en base
        n = (await db.execute(text("SELECT count(*) FROM albums WHERE id = :i"),
                              {"i": album_id})).scalar_one()
    assert n == 1

    monkeypatch.setattr(settings, "SHOW_ALBUMS", True)       # on rallume
    r = await client.get(f"/albums/{album_id}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["title"] == "Mon album"
