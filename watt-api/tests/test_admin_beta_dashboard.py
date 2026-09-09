"""B3 (2026-09-08) — tableau de bord de bêta : `GET /admin/beta`.

Le test qui compte est le scénario de bout en bout : deux comptes, une
publication, une vente, un crédit administratif — puis on vérifie que CHAQUE
chiffre du tableau correspond exactement à ce qui vient de se passer.

Les assertions portent sur des DELTAS (avant → après) et non sur des valeurs
absolues : la base de test est partagée par toute la suite, et d'autres tests
y laissent des comptes et des transactions. Un delta exact est une garantie
plus forte qu'un total, pas plus faible : il isole notre scénario.

On vérifie aussi la garde 403, l'absence de donnée sensible dans les listes
d'activité, et le comportement à dénominateur nul (pas de division par zéro).
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.beta_dashboard import _conversion, _pct
from app.services.credits import compute_split
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import WELCOME_BONUS_CREDITS, create_user

PRIX = 25  # prix du prompt vendu dans le scénario


# ── Helpers ────────────────────────────────────────────────────────────────

async def _set_flags(user_id, **values) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()


async def _make_user(pseudo: str) -> uuid.UUID:
    """Crée un compte SANS toucher au solde par UPDATE brut.

    `create_user` accorde le bonus de bienvenue via le ledger
    (transaction BONUS) : c'est ce qu'on veut mesurer. Patcher
    `credits_balance` à la main créerait des Smyles hors ledger et casserait
    la réconciliation — exactement le défaut que ce tableau doit détecter.
    """
    email = f"pytest-b3-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET artist_name = :n WHERE id = :u"),
            {"n": pseudo, "u": uid},
        )
        # Pré-attribue tous les trophées : sinon le hook achievements du
        # unlock accorde des BONUS qui pollueraient les montants mesurés.
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _cleanup(*user_ids) -> None:
    async with SessionLocal() as db:
        for uid in user_ids:
            await db.execute(delete(UserAchievement).where(
                UserAchievement.user_id == uid))
            await db.execute(delete(Prompt).where(Prompt.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def admin_headers(test_user: dict, auth_headers: dict):
    await _set_flags(test_user["id"], is_admin=True)
    try:
        yield auth_headers
    finally:
        await _set_flags(test_user["id"], is_admin=False)


async def _beta(client: AsyncClient, headers: dict, **params) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = await client.get(f"/admin/beta?{qs}" if qs else "/admin/beta", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ── Garde ──────────────────────────────────────────────────────────────────

async def test_non_admin_403(client: AsyncClient, auth_headers: dict):
    r = await client.get("/admin/beta", headers=auth_headers)
    assert r.status_code == 403, r.text


async def test_anonyme_401(client: AsyncClient):
    r = await client.get("/admin/beta")
    assert r.status_code in (401, 403), r.text


# ── Scénario de bout en bout ───────────────────────────────────────────────

async def test_scenario_deux_comptes_une_vente_un_credit_admin(
    client: AsyncClient, admin_headers: dict
):
    avant = await _beta(client, admin_headers, days=365, limit=20)

    vendeur_pseudo = f"VENDEUR-{uuid.uuid4().hex[:6]}"
    acheteur_pseudo = f"ACHETEUR-{uuid.uuid4().hex[:6]}"
    vendeur = await _make_user(vendeur_pseudo)
    acheteur = await _make_user(acheteur_pseudo)
    titre = f"Prompt B3 {uuid.uuid4().hex[:8]}"

    try:
        # 1. Le vendeur publie.
        async with SessionLocal() as db:
            p = Prompt(
                artist_id=vendeur,
                title=titre,
                description="Tagline",
                prompt_text="X" * 100,
                price_credits=PRIX,
                is_published=True,
            )
            db.add(p)
            await db.commit()
            await db.refresh(p)
            prompt_id = p.id

        # 2. Crédit administratif à l'acheteur (passe par le ledger).
        r = await client.post(
            f"/admin/users/{acheteur}/credits",
            json={"credits": 100, "reason": "beta B3"},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text

        # 3. La vente.
        async with SessionLocal() as db:
            res = await unlock_prompt_atomic(
                db, buyer_id=acheteur, prompt_id=prompt_id
            )
            await db.commit()
            paye = res.paid
        assert paye == PRIX
        part_artiste, commission = compute_split(PRIX)
        assert part_artiste + commission == PRIX

        apres = await _beta(client, admin_headers, days=365, limit=20)

        # ── Comptes ────────────────────────────────────────────────────
        ca, cb = apres["comptes"], avant["comptes"]
        assert ca["total"] == cb["total"] + 2                     # 2 inscriptions
        assert ca["nouveaux_sur_la_fenetre"] == cb["nouveaux_sur_la_fenetre"] + 2
        assert ca["ont_publie"] == cb["ont_publie"] + 1           # le vendeur
        assert ca["ont_achete_au_moins_une_fois"] == \
            cb["ont_achete_au_moins_une_fois"] + 1
        assert ca["ont_vendu_au_moins_une_fois"] == \
            cb["ont_vendu_au_moins_une_fois"] + 1

        # ── Publications ───────────────────────────────────────────────
        assert apres["publications"]["total"] == avant["publications"]["total"] + 1

        # ── Ventes ─────────────────────────────────────────────────────
        va, vb = apres["ventes"], avant["ventes"]
        assert va["total"] == vb["total"] + 1
        assert va["smyles_echanges"] == vb["smyles_echanges"] + PRIX
        assert va["commission_plateforme"] == vb["commission_plateforme"] + commission
        assert va["part_reversee_aux_createurs"] == \
            vb["part_reversee_aux_createurs"] + part_artiste
        assert va["sur_la_fenetre"]["nombre"] == vb["sur_la_fenetre"]["nombre"] + 1
        assert va["sur_la_fenetre"]["smyles"] == vb["sur_la_fenetre"]["smyles"] + PRIX

        # Qui a acheté quoi, quand, à qui, pour combien.
        vente = va["dernieres"][0]
        assert vente["acheteur"] == acheteur_pseudo
        assert vente["vendeur"] == vendeur_pseudo
        assert vente["objet_type"] == "prompt"
        assert vente["objet_titre"] == titre
        assert vente["montant_smyles"] == PRIX
        assert vente["part_createur"] == part_artiste
        assert vente["commission"] == commission
        assert vente["nature"] == "unlock"
        assert vente["date"]

        # ── Masse de Smyles ────────────────────────────────────────────
        ma, mb = apres["masse_smyles"], avant["masse_smyles"]
        assert ma["crees"]["bonus_bienvenue_et_recompenses"] == \
            mb["crees"]["bonus_bienvenue_et_recompenses"] + 2 * WELCOME_BONUS_CREDITS
        assert ma["crees"]["credits_administratifs"] == \
            mb["crees"]["credits_administratifs"] + 100
        assert ma["crees"]["total"] == mb["crees"]["total"] + 2 * WELCOME_BONUS_CREDITS + 100
        assert ma["depenses_par_les_acheteurs"] == \
            mb["depenses_par_les_acheteurs"] + PRIX
        assert ma["redistribues_aux_createurs"] == \
            mb["redistribues_aux_createurs"] + part_artiste
        assert ma["detruits_en_commission"] == mb["detruits_en_commission"] + commission

        # Circulation : +10 +10 +100 −commission (la part artiste ne fait que
        # changer de poche, elle ne crée ni ne détruit rien).
        attendu_delta = 2 * WELCOME_BONUS_CREDITS + 100 - commission
        assert ma["en_circulation"]["total"] == \
            mb["en_circulation"]["total"] + attendu_delta
        assert ma["en_circulation"]["promo"] == \
            mb["en_circulation"]["promo"] + 2 * WELCOME_BONUS_CREDITS + 100 - PRIX
        assert ma["en_circulation"]["gagnes"] == \
            mb["en_circulation"]["gagnes"] + part_artiste

        # Réconciliation : notre scénario est parfaitement équilibré, donc
        # l'écart global ne bouge pas d'un Smyle.
        ra, rb = ma["reconciliation"], mb["reconciliation"]
        assert ra["attendu"] == rb["attendu"] + attendu_delta
        assert ra["constate"] == rb["constate"] + attendu_delta
        assert ra["ecart"] == rb["ecart"]
        assert ra["comptes_aux_sous_soldes_incoherents"] == 0

        # ── Créateurs ──────────────────────────────────────────────────
        ligne = next(c for c in apres["createurs"] if c["pseudo"] == vendeur_pseudo)
        assert ligne["publications"] == 1
        assert ligne["ventes_realisees"] == 1
        assert ligne["smyles_gagnes"] == part_artiste
        assert ligne["palier"] == "standard"

        # ── Ce qu'on ne sait pas mesurer, on le dit ────────────────────
        conv = apres["conversion_fiche_vers_deblocage"]
        assert conv["mesurable"] is False
        assert conv["taux_pct"] is None
        assert "product_view" in conv["pourquoi"]

        # ── Aucune donnée sensible dans les listes d'activité ───────────
        sensible = repr(apres["ventes"]["dernieres"]) + repr(apres["createurs"])
        assert "@" not in sensible
        assert "password" not in sensible and "signup_ip" not in sensible
    finally:
        await _cleanup(vendeur, acheteur)


# ── Bornes / dénominateurs nuls ────────────────────────────────────────────

async def test_pct_ne_divise_jamais_par_zero():
    """Sur une base vide, un dénominateur nul renvoie None — pas 0 %, qui se
    lirait comme un échec mesuré, et pas une ZeroDivisionError."""
    assert _pct(0, 0) is None
    assert _pct(5, 0) is None
    assert _pct(1, 4) == 25.0


async def test_conversion_sans_donnee_de_vue_est_declaree_non_mesurable():
    d = _conversion(vues=0, clics=0, acheteurs=0)
    assert d["mesurable"] is False
    assert d["taux_pct"] is None
    assert d["pourquoi"] and d["pour_l_obtenir"]
    # Si un jour le front émet `product_view`, le taux devient calculable et
    # arrive avec son avertissement (numérateur comptable / dénominateur
    # télémétrique).
    d2 = _conversion(vues=10, clics=4, acheteurs=3)
    assert d2["mesurable"] is True and d2["taux_pct"] == 30.0
    assert d2["avertissement"]


async def test_bornes_et_forme(client: AsyncClient, admin_headers: dict):
    """Les bornes sont refusées par FastAPI, et la forme est stable."""
    for qs in ("days=0", "days=999", "limit=0", "limit=101"):
        r = await client.get(f"/admin/beta?{qs}", headers=admin_headers)
        assert r.status_code == 422, r.text

    d = await _beta(client, admin_headers, days=1, limit=1)
    assert set(d) == {
        "genere_le", "fenetre_jours", "source", "comptes", "publications",
        "ventes", "masse_smyles", "createurs", "conversion_fiche_vers_deblocage",
    }
    assert d["fenetre_jours"] == 1
    assert len(d["ventes"]["dernieres"]) <= 1
    assert len(d["createurs"]) <= 1
    assert isinstance(d["masse_smyles"]["reconciliation"]["reconcilie"], bool)
    panier = d["ventes"]["panier_moyen_smyles"]
    assert panier is None or isinstance(panier, (int, float))


# ── /admin/funnel ne ment plus ─────────────────────────────────────────────

async def test_funnel_lit_les_inscriptions_dans_users_pas_la_telemetrie(
    client: AsyncClient, admin_headers: dict
):
    """Avant B3, la marche « Inscrits » comptait un événement `signup` que le
    front n'émet nulle part : elle valait 0 quoi qu'il arrive. Une inscription
    réelle doit maintenant la faire bouger de +1, sans aucune télémétrie."""
    r = await client.get("/admin/funnel?days=365", headers=admin_headers)
    assert r.status_code == 200, r.text
    avant = r.json()

    uid = await _make_user(f"FUNNEL-{uuid.uuid4().hex[:6]}")
    try:
        r = await client.get("/admin/funnel?days=365", headers=admin_headers)
        apres = r.json()
        marches_a = {s["key"]: s for s in apres["funnel"]}
        marches_b = {s["key"]: s for s in avant["funnel"]}
        assert marches_a["signups"]["count"] == marches_b["signups"]["count"] + 1
        assert marches_a["signups"]["source"] == "comptable"
        assert marches_a["buyers"]["source"] == "comptable"
        assert marches_a["visitors"]["source"] == "telemetrie"
        assert marches_a["returning"]["source"] == "telemetrie"
        assert apres["avertissements"]
    finally:
        await _cleanup(uid)
