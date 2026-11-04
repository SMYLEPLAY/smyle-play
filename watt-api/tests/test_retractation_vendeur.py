"""Rétractation en ligne (art. L221-21 / D221-5 du Code de la consommation)
et statut du vendeur (art. L111-7 II).

1. Le lien « Renoncer au contrat ici » est dans le pied de page de toutes les
   pages et mène à /retractation (page servie, bouton « Confirmer la
   rétractation »).
2. Une déclaration complète est enregistrée (avec ou sans compte) ; une
   déclaration incomplète est refusée.
3. La liste des déclarations est réservée à l'admin.
4. Le statut « vend à titre professionnel » s'enregistre depuis /users/me ;
   un `null` ne l'efface pas.
5. Migration 0111 : identifiant de révision ≤ 32 caractères (alembic_version).
"""
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.database import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

REPO = Path(__file__).resolve().parents[2]
VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


async def test_pied_de_page_renoncer_au_contrat():
    js = (REPO / "ui" / "core" / "legal-footer.js").read_text()
    assert "Renoncer au contrat ici" in js
    assert 'href="/retractation"' in js


async def test_page_retractation_servie(client: AsyncClient):
    r = await client.get("/retractation")
    assert r.status_code == 200
    assert "Confirmer la rétractation" in r.text
    assert "ui/core/legal-footer.js" in r.text


async def test_declaration_enregistree(client: AsyncClient):
    nom = f"Test Retractation {uuid.uuid4().hex[:6]}"
    r = await client.post("/retractation", json={
        "nom_prenom": nom,
        "contrat": "500 Smyles achetés le 03/11",
        "email": "Pytest-Retract@Smyleplay.Example",
    })
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["nom_prenom"] == nom
    assert j["email"] == "pytest-retract@smyleplay.example"
    assert j["recue_le"] and j["recue_le_texte"] and j["reference"]
    async with SessionLocal() as db:
        rows = (await db.execute(
            text("SELECT contrat, statut FROM retractations WHERE nom_prenom = :n"),
            {"n": nom},
        )).all()
        assert len(rows) == 1
        assert rows[0].contrat == "500 Smyles achetés le 03/11"
        assert rows[0].statut == "recue"
        await db.execute(text("DELETE FROM retractations WHERE nom_prenom = :n"), {"n": nom})
        await db.commit()


@pytest.mark.parametrize("corps", [
    {"nom_prenom": "A", "contrat": "achat", "email": "a@b.example"},          # nom trop court
    {"nom_prenom": "Ana Test", "contrat": "achat"},                            # email absent
    {"nom_prenom": "Ana Test", "contrat": "achat", "email": "pas-un-email"},   # email invalide
    {"nom_prenom": "Ana Test", "contrat": "achat", "email": "a@b.example", "x": 1},  # champ inconnu
])
async def test_declaration_incomplete_refusee(client: AsyncClient, corps):
    r = await client.post("/retractation", json=corps)
    assert r.status_code == 422, r.text


async def test_liste_reservee_admin(client: AsyncClient, auth_headers):
    assert (await client.get("/admin/retractations")).status_code in (401, 403)
    assert (await client.get("/admin/retractations", headers=auth_headers)).status_code == 403


async def test_statut_vendeur_pro(client: AsyncClient, auth_headers):
    r = await client.get("/users/me", headers=auth_headers)
    assert r.status_code == 200 and r.json()["vendeur_pro"] is False
    r = await client.patch("/users/me", headers=auth_headers, json={"vendeur_pro": True})
    assert r.status_code == 200, r.text
    assert r.json()["vendeur_pro"] is True
    # `null` = pas de changement (colonne NOT NULL).
    r = await client.patch("/users/me", headers=auth_headers, json={"vendeur_pro": None})
    assert r.status_code == 200, r.text
    assert r.json()["vendeur_pro"] is True
    r = await client.patch("/users/me", headers=auth_headers, json={"vendeur_pro": False})
    assert r.json()["vendeur_pro"] is False


async def test_migration_0111_identifiant_court():
    src = (VERSIONS / "0111_retractation_vendeur_pro.py").read_text()
    assert 'revision = "0111_retractation_vendeur_pro"' in src
    assert len("0111_retractation_vendeur_pro") <= 32
    assert 'down_revision = "0110_preuve_achat_carte"' in src
