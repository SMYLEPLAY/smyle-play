"""Redénomination ×10 du Smyle (décision Tom du 9/10/2026) — migration 0100.

1. Constantes : packs 100/500/2000 pour 8/35/120 €, retrait 5 c/Smyle,
   bienvenue 30, parrainage 20, quêtes 30/100/250, et tout le reste ×10.
2. Partage entier exact sur les prix conseillés (10, 15, 30, 45 Smyles).
3. Migration sur une base PEUPLÉE : on se replace dans l'état d'avant (0099)
   à l'intérieur d'une transaction, on sème des données dans l'ancienne
   unité, on applique la migration, on vérifie les invariants, puis on
   redescend et on vérifie le retour à l'identique. Tout est annulé à la fin
   (ROLLBACK) : la base de test n'est pas modifiée.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import Settings
from app.database import SessionLocal

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0100_redenomination_x10.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("m0100", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── 1. Constantes ─────────────────────────────────────────────────────────────

def test_packs_et_valeur_de_retrait():
    from app.services.credits import CREDIT_PACKS, EUR_PER_CREDIT, get_pack_by_id
    from app.services.reserve import PAYOUT_RATE_CENTS

    assert [(p["id"], p["credits"], p["price_eur_cents"]) for p in CREDIT_PACKS] == [
        ("pack_100", 100, 800), ("pack_500", 500, 3500), ("pack_2000", 2000, 12000),
    ]
    # Anciens identifiants encore acceptés (onglet resté ouvert).
    assert get_pack_by_id("pack_10")["credits"] == 100
    assert get_pack_by_id("pack_200")["credits"] == 2000
    assert PAYOUT_RATE_CENTS == 5
    assert EUR_PER_CREDIT == pytest.approx(0.07)
    # La règle d'or tient toujours : le Smyle gagné ne se rachète jamais plus
    # cher que le prix net le plus bas (pack de 2000 : 120 € / 2000 = 6 c TTC).
    assert PAYOUT_RATE_CENTS * 2000 < 12000


def test_recompenses_et_mecaniques():
    from app.routers import the_plan
    from app.services.packs import MYSTERY_PACK_PRICE
    from app.services.referrals import REFERRAL_REWARD_CREDITS
    from app.services.streak import DAILY_REWARD, MILESTONE_REWARD
    from app.services.users import WELCOME_BONUS_CREDITS

    s = Settings()
    assert WELCOME_BONUS_CREDITS == 30
    assert REFERRAL_REWARD_CREDITS == 20
    assert [tuple(p) for p in s.QUETES_PARRAINAGE_PALIERS] == [(3, 30), (10, 100), (25, 250)]
    assert s.QUETES_PARRAINAGE_PLAFOND_24H == 30000
    assert (DAILY_REWARD, MILESTONE_REWARD) == (10, 30)
    assert MYSTERY_PACK_PRICE == 80
    assert (the_plan.PRICE, the_plan.PRICE_STRIKE) == (350, 700)


def test_bornes_de_prix():
    from app.schemas.marketplace import ADN_PRICE_MIN, PROMPT_PRICE_MAX, PROMPT_PRICE_MIN
    from app.schemas.visual_adn import VISUAL_ADN_PRICE_MAX, VISUAL_ADN_PRICE_MIN
    from app.services.resale import RESALE_PRICE_MAX

    assert (PROMPT_PRICE_MIN, PROMPT_PRICE_MAX) == (10, 150)
    assert ADN_PRICE_MIN == 300
    assert (VISUAL_ADN_PRICE_MIN, VISUAL_ADN_PRICE_MAX) == (300, 5000)
    assert RESALE_PRICE_MAX == 1_000_000


def test_le_formulaire_n_impose_plus_25_80_ni_3_500():
    """Le prix est libre entre 10 et 150 ; plus aucune borne 3–500 côté front."""
    racine = Path(__file__).resolve().parents[2]
    for nom in ("dashboard.html", "dashboard.js", "images-list.js"):
        src = (racine / nom).read_text(encoding="utf-8")
        assert "entre 3 et 500" not in src, nom
        assert "Min. 3 · Max. 500" not in src, nom
    html = (racine / "dashboard.html").read_text(encoding="utf-8")
    assert 'min="10" max="150" value="15"' in html
    assert "Les prix montent avec la rareté et le travail de création." in html


# ─── 2. Partage entier exact ──────────────────────────────────────────────────

@pytest.mark.parametrize("prix", [10, 15, 30, 45])
@pytest.mark.parametrize("part_artiste", [80, 88, 90])
def test_compute_split_prix_conseilles(prix, part_artiste):
    from app.services.credits import compute_split
    from app.services.tiers import COMMISSION_PLANCHER_PCT

    artiste, commission = compute_split(prix, part_artiste)
    assert artiste + commission == prix                      # rien ne se perd
    assert artiste == prix * part_artiste // 100             # arrondi à la plateforme
    # Commission jamais inférieure au taux affiché, ni au plancher de 10 %…
    assert commission * 100 >= prix * (100 - part_artiste)
    assert commission * 100 >= prix * COMMISSION_PLANCHER_PCT
    # … et jamais plus d'un Smyle au-dessus.
    assert commission * 100 - prix * (100 - part_artiste) < 100


def test_compute_split_standard_exact_sur_les_prix_conseilles():
    from app.services.credits import compute_split

    # Au taux standard (20 %), la commission est EXACTE sur 10, 15, 30 et 45.
    assert [compute_split(p) for p in (10, 15, 30, 45)] == [(8, 2), (12, 3), (24, 6), (36, 9)]


# ─── 3. Migration sur une base peuplée ────────────────────────────────────────

async def _exec(db, sql: str, params: dict | None = None):
    return await db.execute(text(sql), params or {})


async def _seed(db) -> dict:
    """Sème des données dans l'ANCIENNE unité (état 0099)."""
    ids = {k: uuid.uuid4() for k in (
        "officiel", "vendeur", "acheteur", "tx_vente", "tx_revente", "tx_bonus",
        "p_off25", "p_off30", "p_off80", "p_off12", "p_bas", "p_mid", "p_haut",
        "adn", "voix", "paiement", "notif",
    )}
    tag = uuid.uuid4().hex[:8]
    await _exec(db, "INSERT INTO users (id, email, is_official, credits_balance, smyles_achetes, "
                "smyles_gagnes, smyles_promo, smyles_gagnes_bloque, smyles_promo_gagnes, "
                "credits_earned_total) VALUES "
                "(:o, :eo, true, 0, 0, 0, 0, 0, 0, 0), "
                "(:v, :ev, false, 23, 5, 11, 7, 4, 3, 19), "
                "(:a, :ea, false, 9, 2, 0, 7, 0, 0, 0)",
                {"o": ids["officiel"], "v": ids["vendeur"], "a": ids["acheteur"],
                 "eo": f"x10-off-{tag}@t.example", "ev": f"x10-v-{tag}@t.example",
                 "ea": f"x10-a-{tag}@t.example"})
    recette = "X" * 120
    prompts = [
        ("p_off25", "officiel", 25), ("p_off30", "officiel", 30), ("p_off80", "officiel", 80),
        ("p_off12", "officiel", 12), ("p_bas", "vendeur", 3), ("p_mid", "vendeur", 9),
        ("p_haut", "vendeur", 40),
    ]
    for cle, art, prix in prompts:
        await _exec(db, "INSERT INTO prompts (id, artist_id, title, prompt_text, price_credits, "
                    "is_published) VALUES (:i, :a, :t, :x, :p, true)",
                    {"i": ids[cle], "a": ids[art], "t": f"Recette {cle}", "x": recette, "p": prix})
    await _exec(db, "INSERT INTO adns (id, artist_id, description, price_credits, adn_reserve_credits) "
                "VALUES (:i, :a, :d, 45, 40)",
                {"i": ids["adn"], "a": ids["vendeur"], "d": "D" * 210})
    await _exec(db, "INSERT INTO voices_for_sale (id, artist_id, name, style, sample_url, license, "
                "price_credits) VALUES (:i, :a, 'Voix', 'soul', 'https://x.invalid/s.mp3', "
                "'personnel', 120)", {"i": ids["voix"], "a": ids["vendeur"]})
    # Registre : une vente (split strict), une revente (parts promo en métadonnées), un bonus.
    await _exec(db, "INSERT INTO transactions (id, type, status, buyer_id, seller_id, credits_amount, "
                "platform_fee, artist_revenue, promo_paid, promo_non_retirable, metadata_json) VALUES "
                "(:t1, 'unlock', 'completed', :a, :v, 9, 2, 7, 5, 4, CAST(:m1 AS jsonb)), "
                "(:t2, 'resale', 'completed', :a, :v, 10, 2, 3, 6, 6, CAST(:m2 AS jsonb)), "
                "(:t3, 'bonus', 'completed', :a, NULL, 10, 0, 0, 0, 0, NULL)",
                {"t1": ids["tx_vente"], "t2": ids["tx_revente"], "t3": ids["tx_bonus"],
                 "a": ids["acheteur"], "v": ids["vendeur"],
                 "m1": json.dumps({"source": "unlock", "base_price": 9, "remise_oeuvre": 1}),
                 "m2": json.dumps({"source": "resale", "seller_cut": 5,
                                   "promo": {"vendeur": 4, "artiste": 2}})})
    await _exec(db, "INSERT INTO stripe_payments (id, session_id, pack_id, credits, amount_cents, "
                "consent_immediate_at, smyles_recovered, shortfall) VALUES "
                "(:i, :s, 'pack_50', 50, 3500, now(), 10, 5)",
                {"i": ids["paiement"], "s": f"cs_test_{tag}"})
    await _exec(db, "INSERT INTO notifications (id, user_id, type, metadata_json) VALUES "
                "(:i, :u, 'system', CAST(:m AS jsonb))",
                {"i": ids["notif"], "u": ids["vendeur"],
                 "m": json.dumps({"action": "sale", "amount": 9})})
    return ids


async def _etat(db, ids) -> dict:
    """Photo des valeurs semées (pour comparer avant / après)."""
    users = {
        str(r.id): tuple(r[1:]) for r in (await _exec(db,
            "SELECT id, credits_balance, smyles_achetes, smyles_gagnes, smyles_promo, "
            "smyles_gagnes_bloque, smyles_promo_gagnes, credits_earned_total FROM users "
            "WHERE id IN (:o, :v, :a)",
            {"o": ids["officiel"], "v": ids["vendeur"], "a": ids["acheteur"]})).all()
    }
    tx = {
        str(r.id): (r.credits_amount, r.platform_fee, r.artist_revenue, r.promo_paid,
                    r.promo_non_retirable, r.metadata_json)
        for r in (await _exec(db,
            "SELECT id, credits_amount, platform_fee, artist_revenue, promo_paid, "
            "promo_non_retirable, metadata_json FROM transactions WHERE id IN (:a, :b, :c)",
            {"a": ids["tx_vente"], "b": ids["tx_revente"], "c": ids["tx_bonus"]})).all()
    }
    prix = {
        str(r.id): r.price_credits for r in (await _exec(db,
            "SELECT id, price_credits FROM prompts WHERE artist_id IN (:o, :v)",
            {"o": ids["officiel"], "v": ids["vendeur"]})).all()
    }
    adn = tuple((await _exec(db, "SELECT price_credits, adn_reserve_credits FROM adns WHERE id = :i",
                             {"i": ids["adn"]})).one())
    voix = (await _exec(db, "SELECT price_credits FROM voices_for_sale WHERE id = :i",
                        {"i": ids["voix"]})).scalar_one()
    paiement = tuple((await _exec(db,
        "SELECT pack_id, credits, amount_cents, smyles_recovered, shortfall FROM stripe_payments "
        "WHERE id = :i", {"i": ids["paiement"]})).one())
    notif = (await _exec(db, "SELECT metadata_json FROM notifications WHERE id = :i",
                         {"i": ids["notif"]})).scalar_one()
    return {"users": users, "tx": tx, "prix": prix, "adn": adn, "voix": voix,
            "paiement": paiement, "notif": notif}


async def test_migration_0100_sur_base_peuplee():
    m = _migration()
    assert m.revision == "0100_redenomination_x10"
    assert m.down_revision == "0099_reclasse_gagnes_promo"
    assert len(m.revision) <= 32

    async with SessionLocal() as db:
        try:
            # Retour à l'état 0099 (dans la transaction), puis données d'avant.
            for sql in m.DOWNGRADE_SQL:
                await _exec(db, sql)
            ids = await _seed(db)
            avant = await _etat(db, ids)
            masse_avant = (await _exec(db, "SELECT COALESCE(sum(credits_balance),0) FROM users")).scalar_one()

            for sql in m.UPGRADE_SQL:
                await _exec(db, sql)
            apres = await _etat(db, ids)

            # Soldes : chaque compteur ×10, la somme des réserves = le solde.
            for uid, valeurs in avant["users"].items():
                assert apres["users"][uid] == tuple(v * 10 for v in valeurs)
                b, a, g, p, *_ = apres["users"][uid]
                assert a + g + p == b
            masse_apres = (await _exec(db, "SELECT COALESCE(sum(credits_balance),0) FROM users")).scalar_one()
            assert masse_apres == masse_avant * 10
            incoherents = (await _exec(db,
                "SELECT count(*) FROM users WHERE smyles_achetes + smyles_gagnes + smyles_promo "
                "<> credits_balance")).scalar_one()
            assert incoherents == 0

            # Registre : montants ×10, split strict des ventes, parts promo bornées.
            v = apres["tx"][str(ids["tx_vente"])]
            assert v[:5] == (90, 20, 70, 50, 40)
            assert v[1] + v[2] == v[0]
            assert v[5]["base_price"] == 90 and v[5]["remise_oeuvre"] == 10
            r = apres["tx"][str(ids["tx_revente"])]
            assert r[:5] == (100, 20, 30, 60, 60)
            assert r[5]["seller_cut"] == 50 and r[5]["promo"] == {"vendeur": 40, "artiste": 20}
            assert apres["tx"][str(ids["tx_bonus"])][0] == 100
            # Réconciliation registre ↔ soldes conservée (linéarité).
            for cle in ("tx_vente", "tx_revente", "tx_bonus"):
                assert apres["tx"][str(ids[cle])][0] == avant["tx"][str(ids[cle])][0] * 10
            # Le registre redevient immuable juste après.
            with pytest.raises(Exception):
                async with db.begin_nested():
                    await _exec(db, "UPDATE transactions SET credits_amount = 1 WHERE id = :i",
                                {"i": ids["tx_bonus"]})

            # Prix (tous comptes) : ancien ≤ 30 → 15, 31–60 → 30, > 60 → 45.
            pr = {k: apres["prix"][str(ids[k])] for k in (
                "p_off25", "p_off30", "p_off80", "p_off12", "p_bas", "p_mid", "p_haut")}
            assert pr == {"p_off25": 15, "p_off30": 15, "p_off80": 45, "p_off12": 15,
                          "p_bas": 15, "p_mid": 15, "p_haut": 30}
            assert apres["adn"] == (450, 400)
            assert apres["voix"] == 1200
            assert apres["paiement"] == ("pack_500", 500, 3500, 100, 50)   # euros inchangés
            assert apres["notif"]["amount"] == 90

            # Downgrade : retour EXACT à l'état d'avant (aucune activité entre-temps).
            for sql in m.DOWNGRADE_SQL:
                await _exec(db, sql)
            retour = await _etat(db, ids)
            assert retour == avant
        finally:
            await db.rollback()
