"""Pricing v2 (validé le 30/09/2026, option A).

  - valeur de retrait d'un Smyle gagné : 0,50 € (PAYOUT_RATE_CENTS = 50),
    reprise partout (équivalent euros des gains, dette encaissable) ;
  - maturation des gains : 30 jours ;
  - page Offres : Mythique à 10 % ;
  - migration 0099 : les gagnés de la bêta passent en promo (sauf trésorerie),
    solde inchangé, invariant de somme tenu, trace dans admin_journal ;
  - tableau de bord : Smyles retirables / Smyles bonus + phrase explicative ;
  - « Prêt à sortir » : Œuvres en ligne + contrôle des soldes (lecture seule).
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "watt-api" / "alembic" / "versions" / "0099_reclasse_gagnes_promo.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0099", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _user(**buckets) -> uuid.UUID:
    email = f"pytest-pv2-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    if buckets:
        a, g, p = buckets.get("a", 0), buckets.get("g", 0), buckets.get("p", 0)
        async with SessionLocal() as db:
            await db.execute(text(
                "UPDATE users SET smyles_achetes = :a, smyles_gagnes = :g, smyles_promo = :p, "
                "smyles_promo_gagnes = :pg, smyles_gagnes_bloque = :bl, credits_balance = :b "
                "WHERE id = :u"),
                {"a": a, "g": g, "p": p, "pg": buckets.get("pg", 0),
                 "bl": buckets.get("bl", 0), "b": a + g + p, "u": uid})
            await db.commit()
    return uid


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


# ─── constantes ───────────────────────────────────────────────────────────────

def test_valeur_de_retrait_50_centimes_et_maturation_30_jours():
    from app.schemas.user import UserRead
    from app.services.escrow import EARNINGS_MATURITY_DAYS
    from app.services.reserve import PAYOUT_RATE_CENTS

    assert PAYOUT_RATE_CENTS == 50
    assert EARNINGS_MATURITY_DAYS == 30
    fields = {k: v for k, v in {
        "id": uuid.uuid4(), "email": "a@b.example", "created_at": "2026-09-30T00:00:00Z",
        "credits_earned_total": 10,
    }.items()}
    u = UserRead.model_validate(fields)
    assert u.euro_equivalent_earned == 5.0  # 10 × 0,50 €


def test_page_offres_mythique_10_pct():
    src = (REPO_ROOT / "offres.html").read_text(encoding="utf-8")
    assert "commission: 10, slots: 'Emplacements illimités'" in src
    assert "commission: 5," not in src


def test_aucun_070_residuel_pour_la_valeur_de_retrait():
    """0,70 € reste le prix d'ACHAT moyen (pack de 50) — jamais la valeur de
    retrait. Les endroits qui valorisent des gains lisent PAYOUT_RATE_CENTS."""
    user_schema = (REPO_ROOT / "watt-api" / "app" / "schemas" / "user.py").read_text(encoding="utf-8")
    assert "credits_earned_total * 0.70" not in user_schema
    reserve = (REPO_ROOT / "watt-api" / "app" / "services" / "reserve.py").read_text(encoding="utf-8")
    assert "PAYOUT_RATE_CENTS = 50" in reserve


# ─── migration 0099 ───────────────────────────────────────────────────────────

async def test_migration_0099_reclasse_gagnes_en_promo():
    m = _migration()
    assert m.revision == "0099_reclasse_gagnes_promo"
    assert m.down_revision == "0098_admin_restauration"
    assert len(m.revision) <= 32

    createur = await _user(a=12, g=40, p=5, pg=2, bl=15)
    acheteur = await _user(a=30, g=0, p=7)
    params = {"action": m.ACTION, "motif": m.MOTIF}
    async with SessionLocal() as db:
        tresorerie = (await db.execute(text(
            "SELECT id FROM users WHERE is_treasury"))).scalar_one_or_none()
        if tresorerie is not None:
            # Une trésorerie avec des gagnés ne doit PAS être touchée.
            await db.execute(text(
                "UPDATE users SET smyles_gagnes = smyles_gagnes + 3, "
                "credits_balance = credits_balance + 3 WHERE id = :t"), {"t": tresorerie})
            tres_avant = (await db.execute(text(
                "SELECT smyles_gagnes, smyles_promo FROM users WHERE id = :t"),
                {"t": tresorerie})).first()
        try:
            await db.execute(text(m.SQL_JOURNAL_SYNTHESE), params)
            await db.execute(text(m.SQL_JOURNAL_COMPTES), params)
            await db.execute(text(m.SQL_RECLASSER))

            c = (await db.execute(text(
                "SELECT smyles_achetes a, smyles_gagnes g, smyles_promo p, smyles_promo_gagnes pg, "
                "smyles_gagnes_bloque bl, credits_balance b FROM users WHERE id = :u"),
                {"u": createur})).first()
            assert (c.a, c.g, c.p, c.pg, c.bl, c.b) == (12, 0, 45, 42, 0, 57)
            assert c.a + c.g + c.p == c.b  # invariant de somme

            ach = (await db.execute(text(
                "SELECT smyles_achetes a, smyles_gagnes g, smyles_promo p, credits_balance b "
                "FROM users WHERE id = :u"), {"u": acheteur})).first()
            assert (ach.a, ach.g, ach.p, ach.b) == (30, 0, 7, 37)  # rien à reclasser

            if tresorerie is not None:
                t = (await db.execute(text(
                    "SELECT smyles_gagnes, smyles_promo FROM users WHERE id = :t"),
                    {"t": tresorerie})).first()
                assert (t.smyles_gagnes, t.smyles_promo) == tuple(tres_avant)

            # Plus AUCUN gagné hors trésorerie ; aucun compte incohérent créé.
            reste = (await db.execute(text(
                "SELECT count(*) FROM users WHERE NOT is_treasury AND "
                "(smyles_gagnes > 0 OR smyles_gagnes_bloque > 0)"))).scalar_one()
            assert reste == 0

            # Trace : état d'avant du compte + ligne de synthèse.
            j = (await db.execute(text(
                "SELECT details FROM admin_journal WHERE action = :a AND cible_id = :c"),
                {"a": m.ACTION, "c": str(createur)})).scalar_one()
            assert j["avant"]["smyles_gagnes"] == 40
            assert j["avant"]["smyles_gagnes_bloque"] == 15
            synth = (await db.execute(text(
                "SELECT details FROM admin_journal WHERE action = :a AND cible_type = 'plateforme' "
                "ORDER BY created_at DESC LIMIT 1"), {"a": m.ACTION})).scalar_one()
            assert synth["comptes"] >= 1 and synth["smyles_reclasses"] >= 40

            # Idempotent : un second passage ne change plus rien.
            await db.execute(text(m.SQL_RECLASSER))
            c2 = (await db.execute(text(
                "SELECT smyles_promo FROM users WHERE id = :u"), {"u": createur})).scalar_one()
            assert c2 == 45
        finally:
            await db.rollback()  # la base de test partagée n'est pas modifiée
    await _cleanup(createur, acheteur)


def test_migration_0099_downgrade_no_op():
    m = _migration()
    assert m.downgrade() is None  # ne recrée jamais de dette en euros


# ─── tableau de bord créateur ─────────────────────────────────────────────────

async def test_creator_stats_portefeuille(client, test_user, auth_headers):
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET smyles_achetes = 5, smyles_gagnes = 7, smyles_promo = 3, "
            "smyles_promo_gagnes = 0, credits_balance = 15 WHERE id = :u"),
            {"u": test_user["id"]})
        await db.commit()
    r = await client.get("/me/creator-stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["portefeuille"] == {
        "retirables": 7, "bonus": 8, "valeur_retrait_cents": 50,
    }


def test_dashboard_affiche_retirables_et_bonus():
    js = (REPO_ROOT / "dashboard.js").read_text(encoding="utf-8")
    assert "Smyles retirables" in js and "Smyles bonus" in js
    assert ("1 Smyle gagné en vendant = 0,50 € quand les retraits s\\'ouvriront "
            "' +\n    '(à 1000 actifs, et au plus tard le 1er mai 2027). ") in js
    assert "Les Smyles bonus se dépensent sur WATT mais ne se retirent pas." in js


# ─── « Prêt à sortir » : deux contrôles ───────────────────────────────────────

async def test_pret_a_sortir_oeuvres_et_controle_des_soldes():
    from app.services.credits import count_bucket_inconsistencies
    from app.services.launch_readiness import _oeuvres_son_image_en_ligne, readiness

    uid = await _user()
    try:
        async with SessionLocal() as db:
            avant = await _oeuvres_son_image_en_ligne(db)
            son = Prompt(artist_id=uid, title="Son test", description="T", prompt_text="X" * 100,
                         price_credits=30, is_published=True)
            img = Prompt(artist_id=uid, title="Image test", description="T", prompt_text="un chat",
                         price_credits=40, is_published=True, product_type="image",
                         image_platform="chatgpt", image_model_version="gpt-4o",
                         preview_r2_key=f"previews/{uuid.uuid4().hex}.webp")
            seule = Prompt(artist_id=uid, title="Image seule", description="T", prompt_text="un chien",
                           price_credits=40, is_published=True, product_type="image",
                           image_platform="chatgpt", image_model_version="gpt-4o",
                           preview_r2_key=f"previews/{uuid.uuid4().hex}.webp")
            db.add_all([son, img, seule])
            await db.flush()
            img.linked_prompt_id, son.linked_prompt_id = son.id, img.id
            await db.commit()
        async with SessionLocal() as db:
            assert await _oeuvres_son_image_en_ligne(db) == avant + 1  # l'image seule ne compte pas
            d = await readiness(db)
            incoherents = await count_bucket_inconsistencies(db)
        cles = {c["cle"]: c for c in d["controles"]}
        assert cles["oeuvres_en_ligne"]["valeur"] == avant + 1
        assert cles["soldes_incoherents"]["valeur"] == incoherents
        assert cles["soldes_incoherents"]["attendu"] == 0
        assert d["chiffres"]["oeuvres_en_ligne"] == avant + 1
    finally:
        async with SessionLocal() as db:
            await db.execute(text("UPDATE prompts SET linked_prompt_id = NULL WHERE artist_id = :u"), {"u": uid})
            await db.execute(delete(Prompt).where(Prompt.artist_id == uid))
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.commit()
        await _cleanup(uid)


def test_page_pret_a_sortir_affiche_les_controles():
    src = (REPO_ROOT / "pret-a-sortir.html").read_text(encoding="utf-8")
    assert "controlesHtml(d.controles)" in src
