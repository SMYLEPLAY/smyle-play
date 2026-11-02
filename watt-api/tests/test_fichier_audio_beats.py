"""
Décision du 02/11/2026 — un SON donne la recette, un BEAT donne le fichier.

  - son acheté après la bascule → téléchargement refusé (403, message clair),
    bibliothèque `fichier_inclus = False`, fiche publique `fichier_inclus = False` ;
  - beat (morceau publié comme beat) → téléchargement autorisé (le contrôle
    d'accès passe ; 503 = stockage absent en test), `fichier_inclus = True` ;
  - exemplaire acheté AVANT la bascule (fichier_inclus posé par la migration
    0111) → fichier toujours servi (droits acquis) ;
  - le créateur garde accès à son propre fichier.

REQUIRES : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.services.fichier_audio import MESSAGE_RECETTE_SEULE

from tests.test_lot_a_securite import _cleanup, _login, _prompt, _track, _user
from tests.test_parcours_v1 import _acheter, _bibliotheque


async def _produit(artist_id, *, beat: bool):
    rec = await _prompt(artist_id, price_credits=15)
    key = f"tracks/{artist_id}/son-{uuid.uuid4().hex[:8]}.wav"
    await _track(artist_id, prompt_id=rec, r2_key=key,
                 audio_url=f"/watt/stream/{key}", is_beat=beat, bpm=(140 if beat else None))
    return rec


async def _scenario(client, *, beat: bool):
    a, acheteur = await _user(), await _user(balance=500)
    rec = await _produit(a["id"], beat=beat)
    hb = await _login(client, acheteur["email"])
    await _acheter(client, hb, rec)
    h = await _login(client, a["email"])
    return a, acheteur, rec, h, hb


async def test_son_achete_donne_la_recette_pas_le_fichier(client):
    a, acheteur, rec, h, hb = await _scenario(client, beat=False)
    try:
        r = await client.get(f"/products/{rec}/download", headers=hb)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == MESSAGE_RECETTE_SEULE
        lib = await _bibliotheque(client, hb)
        assert lib[str(rec)]["fichier_inclus"] is False
        assert lib[str(rec)]["prompt_text"] == "X" * 100   # la recette, elle, est là
        fiche = (await client.get(f"/catalog/prompts/{rec}")).json()
        assert fiche["fichier_inclus"] is False
        # Le créateur, lui, garde son fichier (contrôle passé → stockage).
        r = await client.get(f"/products/{rec}/download", headers=h)
        assert r.status_code == 503, r.text
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_beat_achete_donne_le_fichier(client):
    a, acheteur, rec, h, hb = await _scenario(client, beat=True)
    try:
        r = await client.get(f"/products/{rec}/download", headers=hb)
        assert r.status_code == 503, r.text   # accès accordé, stockage absent en test
        lib = await _bibliotheque(client, hb)
        assert lib[str(rec)]["fichier_inclus"] is True
        fiche = (await client.get(f"/catalog/prompts/{rec}")).json()
        assert fiche["fichier_inclus"] is True
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_achat_avant_la_bascule_garde_son_fichier(client):
    a, acheteur, rec, h, hb = await _scenario(client, beat=False)
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE unlocked_prompts SET fichier_inclus = TRUE "
            "WHERE prompt_id = :p AND current_owner_id = :u"),
            {"p": str(rec), "u": str(acheteur["id"])})
        await db.commit()
    try:
        r = await client.get(f"/products/{rec}/download", headers=hb)
        assert r.status_code == 503, r.text
        lib = await _bibliotheque(client, hb)
        assert lib[str(rec)]["fichier_inclus"] is True
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_nouvel_exemplaire_nait_sans_fichier(client):
    a, acheteur, rec, h, hb = await _scenario(client, beat=False)
    try:
        async with SessionLocal() as db:
            v = (await db.execute(text(
                "SELECT fichier_inclus FROM unlocked_prompts "
                "WHERE prompt_id = :p AND current_owner_id = :u"),
                {"p": str(rec), "u": str(acheteur["id"])})).scalar_one()
        assert v is False
    finally:
        await _cleanup(a["id"], acheteur["id"])


async def test_beat_achete_garde_son_fichier_si_le_createur_le_repasse_en_son(client):
    a, acheteur, rec, h, hb = await _scenario(client, beat=True)
    try:
        async with SessionLocal() as db:
            v = (await db.execute(text(
                "SELECT fichier_inclus FROM unlocked_prompts "
                "WHERE prompt_id = :p AND current_owner_id = :u"),
                {"p": str(rec), "u": str(acheteur["id"])})).scalar_one()
            assert v is True   # droit figé à l'achat
            await db.execute(text(
                "UPDATE tracks SET is_beat = FALSE WHERE prompt_id = :p"), {"p": str(rec)})
            await db.commit()
        r = await client.get(f"/products/{rec}/download", headers=hb)
        assert r.status_code == 503, r.text   # toujours servi (stockage absent en test)
    finally:
        await _cleanup(a["id"], acheteur["id"])
