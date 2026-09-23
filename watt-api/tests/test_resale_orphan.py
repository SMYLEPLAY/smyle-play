"""Revente — royaltie de l'artiste d'origine DISPARU (Brique 1, décision Tom 23/09).

Règle (brique ON) : la royaltie orpheline de 30 % va au VENDEUR, qui touche
80 % ; la société reste plafonnée à 20 %, jamais 50 %.

« Disparu » couvre DEUX cas :
  - `original_artist_id` NULL (ligne absente) ;
  - compte SUPPRIMÉ : la suppression RGPD anonymise sans effacer, donc
    `original_artist_id` reste renseigné — c'est le cas réel. Sans traitement,
    la royaltie partirait sur un compte mort (irrécupérable, et comptée dans la
    dette encaissable).

Brique OFF : comportement historique STRICTEMENT inchangé (aucun changement
d'argent en prod avant l'activation coordonnée).

Chaque cas vérifie : split exact, conservation (débit acheteur == vendeur +
artiste + société), invariant de somme A1.4 sur tous les comptes touchés.
"""
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.account_deletion import delete_account
from app.services.resale import buy_resale_atomic, list_prompt_for_resale
from app.services.treasury import treasury_balance
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import create_user

PRIX_REVENTE = 100


async def _user(balance: int) -> uuid.UUID:
    email = f"pytest-orph-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, smyles_achetes = :b, "
                "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :u"
            ),
            {"b": balance, "u": uid},
        )
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _bk(uid) -> dict:
    async with SessionLocal() as db:
        r = (await db.execute(
            text(
                "SELECT credits_balance b, smyles_achetes a, smyles_gagnes g, "
                "smyles_promo p FROM users WHERE id = :u"
            ),
            {"u": uid},
        )).first()
    return {"b": int(r.b), "a": int(r.a), "g": int(r.g), "p": int(r.p)}


async def _tresor() -> int:
    async with SessionLocal() as db:
        return (await treasury_balance(db))["total"]


async def _revente_preparee():
    """artiste publie ; revendeur achete puis met en vente ; renvoie les ids."""
    artiste, revendeur, acheteur = await _user(0), await _user(1000), await _user(1000)
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artiste, title=f"P {uuid.uuid4().hex[:8]}",
            description="Tagline", prompt_text="X" * 100,
            price_credits=50, is_published=True,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        pid = p.id
    async with SessionLocal() as db:
        res = await unlock_prompt_atomic(db, buyer_id=revendeur, prompt_id=pid)
        await db.commit()
        up_id = res.unlocked_prompt.id
    async with SessionLocal() as db:
        await list_prompt_for_resale(
            db, owner_id=revendeur, prompt_id=pid, price=PRIX_REVENTE
        )
        await db.commit()
    return artiste, revendeur, acheteur, up_id


async def _acheter(acheteur, up_id) -> dict:
    async with SessionLocal() as db:
        out = await buy_resale_atomic(db, buyer_id=acheteur, unlocked_prompt_id=up_id)
        await db.commit()
    return out


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.execute(
            text(
                "UPDATE users SET credits_balance = 0, smyles_achetes = 0, "
                "smyles_gagnes = 0, smyles_promo = 0 WHERE is_treasury = TRUE"
            )
        )
        await db.commit()


def _invariant(*bks):
    for x in bks:
        assert x["a"] + x["g"] + x["p"] == x["b"]


async def _scenario(flag_on: bool, disparition: str | None, monkeypatch):
    """Exécute une revente et renvoie les deltas mesurés.

    disparition : None (artiste présent), "null" (original_artist_id NULL),
    "supprime" (compte supprimé via le vrai parcours RGPD)."""
    monkeypatch.setattr(settings, "FEATURE_MARKET_SMYLES", flag_on)
    artiste, revendeur, acheteur, up_id = await _revente_preparee()
    try:
        if disparition == "null":
            async with SessionLocal() as db:
                await db.execute(
                    text("UPDATE unlocked_prompts SET original_artist_id = NULL WHERE id = :i"),
                    {"i": up_id},
                )
                await db.commit()
        elif disparition == "supprime":
            async with SessionLocal() as db:
                await delete_account(db, await db.get(User, artiste))
                await db.commit()

        av = {u: await _bk(u) for u in (artiste, revendeur, acheteur)}
        t_av = await _tresor()
        out = await _acheter(acheteur, up_id)
        ap = {u: await _bk(u) for u in (artiste, revendeur, acheteur)}
        t_ap = await _tresor()

        d = {
            "acheteur": av[acheteur]["b"] - ap[acheteur]["b"],
            "vendeur": ap[revendeur]["g"] - av[revendeur]["g"],
            "artiste": ap[artiste]["g"] - av[artiste]["g"],
            "tresorerie": t_ap - t_av,
            "platform_fee": int(out["platform_fee"]),
        }
        _invariant(*ap.values())
        return d
    finally:
        await _cleanup(artiste, revendeur, acheteur)


# --- Artiste PRÉSENT : 30 / 20 / 50, quel que soit le flag -------------------

async def test_artiste_present_flag_on_split_inchange(monkeypatch):
    d = await _scenario(True, None, monkeypatch)
    assert (d["artiste"], d["platform_fee"], d["vendeur"]) == (30, 20, 50)
    assert d["tresorerie"] == 20
    assert d["acheteur"] == d["artiste"] + d["platform_fee"] + d["vendeur"]


async def test_artiste_present_flag_off_split_inchange(monkeypatch):
    d = await _scenario(False, None, monkeypatch)
    assert (d["artiste"], d["platform_fee"], d["vendeur"]) == (30, 20, 50)
    assert d["tresorerie"] == 0  # brique OFF : rien n'est encaissé


# --- Orphelin (original_artist_id NULL) ---------------------------------------

async def test_orphelin_null_flag_on_royaltie_au_vendeur(monkeypatch):
    d = await _scenario(True, "null", monkeypatch)
    assert (d["artiste"], d["platform_fee"], d["vendeur"]) == (0, 20, 80)
    assert d["tresorerie"] == 20          # société plafonnée à 20 %, pas 50 %
    assert d["acheteur"] == PRIX_REVENTE == d["vendeur"] + d["platform_fee"]


async def test_orphelin_null_flag_off_comportement_historique(monkeypatch):
    d = await _scenario(False, "null", monkeypatch)
    assert (d["artiste"], d["platform_fee"], d["vendeur"]) == (0, 50, 50)
    assert d["tresorerie"] == 0


# --- Compte SUPPRIMÉ (cas réel : anonymisation, id conservé) ------------------

async def test_artiste_supprime_flag_on_royaltie_au_vendeur(monkeypatch):
    """Le compte mort ne reçoit plus rien ; le vendeur touche 80 %."""
    d = await _scenario(True, "supprime", monkeypatch)
    assert d["artiste"] == 0              # plus rien sur le compte mort
    assert (d["platform_fee"], d["vendeur"]) == (20, 80)
    assert d["tresorerie"] == 20
    assert d["acheteur"] == d["vendeur"] + d["platform_fee"]


async def test_artiste_supprime_flag_off_comportement_historique(monkeypatch):
    """Brique OFF : comportement prod actuel documenté — la royaltie part
    encore sur le compte supprimé (c'est ce que la brique corrige)."""
    d = await _scenario(False, "supprime", monkeypatch)
    assert (d["artiste"], d["platform_fee"], d["vendeur"]) == (30, 20, 50)
