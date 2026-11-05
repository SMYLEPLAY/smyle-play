"""Lot O (03/11/2026) — correctifs de l'audit delta.

- un profil retiré de la vitrine par l'admin ne s'y remet pas seul ;
- rien ne s'achète chez un vendeur banni ;
- plafond anti-fraude des comptes récents (achat par carte) ;
- prix au montant libre jamais décroissant ;
- robots.txt et sitemap.xml ;
- remises ADN absentes de la page légale tant que les ADN sont fermés ;
- les liens partagés gardent leur code de parrainage (front).
"""
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text, update

from app.config import settings
from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import get_pack_by_id
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")
ROOT = Path(__file__).resolve().parents[2]


async def _user(**cols) -> tuple[uuid.UUID, str]:
    email = f"pytest-loto-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
        if cols:
            await db.execute(update(User).where(User.id == uid).values(**cols))
        await db.commit()
    return uid, email


async def _supprimer(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(text("DELETE FROM admin_journal WHERE cible_id = :c"), {"c": str(uid)})
            await db.execute(text("DELETE FROM prompts WHERE artist_id = :u"), {"u": uid})
            await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers_o(test_user: dict, auth_headers: dict):
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == test_user["id"]).values(is_admin=True))
        await db.commit()
    try:
        yield auth_headers
    finally:
        async with SessionLocal() as db:
            await db.execute(update(User).where(User.id == test_user["id"]).values(is_admin=False))
            await db.commit()


async def test_profil_retire_par_admin_ne_revient_pas_seul(client, admin_headers_o):
    uid, email = await _user(artist_name=f"Retire {uuid.uuid4().hex[:6]}", profile_public=True)
    try:
        r = await client.post(f"/admin/profils/{uid}/vitrine", json={"visible": False}, headers=admin_headers_o)
        assert r.status_code == 200
        tok = (await client.post("/auth/login", json={"email": email, "password": "12345678"})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        r = await client.post("/watt/me/profile/publish", headers=h)
        assert r.status_code == 403
        # L'admin le remet : il peut de nouveau publier.
        await client.post(f"/admin/profils/{uid}/vitrine", json={"visible": True}, headers=admin_headers_o)
        r = await client.post("/watt/me/profile/publish", headers=h)
        assert r.status_code == 200
    finally:
        await _supprimer(uid)


async def test_rien_ne_s_achete_chez_un_vendeur_banni():
    from app.services.unlocks import PromptNotPurchasable, _relire_sous_verrou

    vendeur, _ = await _user(artist_name="Vendeur banni", is_banned=True)
    try:
        async with SessionLocal() as db:
            p = Prompt(artist_id=vendeur, title="P banni", description="Tagline",
                       prompt_text="X" * 100, price_credits=15, is_published=True)
            db.add(p)
            await db.commit()
            await db.refresh(p)
            pid = p.id
        async with SessionLocal() as db:
            with pytest.raises(PromptNotPurchasable):
                await _relire_sous_verrou(db, pid)
        async with SessionLocal() as db:
            await db.execute(update(User).where(User.id == vendeur).values(is_banned=False))
            await db.commit()
        async with SessionLocal() as db:
            assert (await _relire_sous_verrou(db, pid)).id == pid
    finally:
        await _supprimer(vendeur)


async def test_plafond_24h_des_comptes_recents(monkeypatch):
    from app.services.stripe_payments import StripeRequestError, _verifier_plafond_compte_recent

    monkeypatch.setattr(settings, "ACHAT_PLAFOND_24H_CENTS", 30000)
    uid, _ = await _user()
    try:
        async with SessionLocal() as db:
            u = await db.get(User, uid)
            await _verifier_plafond_compte_recent(db, u, 29500)          # sous le plafond : OK
            await db.execute(text(
                "INSERT INTO stripe_payments (id, user_id, session_id, pack_id, credits, amount_cents, "
                "currency, status, mode_test, consent_immediate_at) VALUES (gen_random_uuid(), :u, :s, 'pack_2000', "
                "2000, 13000, 'eur', 'paye', true, now())"), {"u": uid, "s": "cs_test_" + uuid.uuid4().hex})
            await db.commit()
            with pytest.raises(StripeRequestError):
                await _verifier_plafond_compte_recent(db, u, 20000)       # 130 + 200 > 300 €
            # Un compte ancien n'est pas plafonné.
            await db.execute(text("UPDATE users SET created_at = now() - interval '90 days' WHERE id = :u"), {"u": uid})
            await db.commit()
            await db.refresh(u)
            await _verifier_plafond_compte_recent(db, u, 200000)
    finally:
        async with SessionLocal() as db:
            await db.execute(text("DELETE FROM stripe_payments WHERE user_id = :u"), {"u": uid})
            await db.commit()
        await _supprimer(uid)


def test_montant_libre_200_n_est_jamais_2000():
    assert get_pack_by_id("libre_200")["credits"] == 200
    assert get_pack_by_id("libre_200")["price_eur_cents"] == 1600
    assert get_pack_by_id("pack_200")["credits"] == 2000      # ancien identifiant conservé


def test_prix_jamais_decroissant():
    precedent = 0
    for n in range(100, 50001, 10):
        c = get_pack_by_id(f"libre_{n}")["price_eur_cents"]
        assert c >= precedent, n
        precedent = c


async def test_robots_et_sitemap(client):
    r = await client.get("/robots.txt")
    assert r.status_code == 200 and "Sitemap:" in r.text and "Disallow: /gestion" in r.text
    r = await client.get("/sitemap.xml")
    assert r.status_code == 200 and "<urlset" in r.text and "/comment-ca-marche</loc>" in r.text


async def test_remises_adn_masquees_quand_adn_ferme(client, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ADN", False)
    html = (await client.get("/legal")).text
    assert "s'il possède ton ADN" not in html and "SI_ADN" not in html
    assert "la remise que tu choisis" in html
    monkeypatch.setattr(settings, "SHOW_ADN", True)
    html = (await client.get("/legal")).text
    assert "s'il possède ton ADN" in html and "SI_ADN" not in html


def test_liens_partages_gardent_le_parrainage():
    js = (ROOT / "ui" / "hub" / "marketplace.js").read_text(encoding="utf-8")
    assert "history.replaceState(null, '', location.pathname + location.hash)" not in js
    art = (ROOT / "artiste.js").read_text(encoding="utf-8")
    assert art.count("window.WATT_LAUNCH.adn") >= 4   # cartes, chip, ADN de playlist
