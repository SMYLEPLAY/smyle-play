"""Compte trésorerie société (Brique 1, migration 0089).

Vérifie : le compte existe et est bien un REGISTRE (non public, non connectable,
distinct du vitrine « Smyle ») ; il est unique ; il se résout par drapeau et non
par UUID ; et surtout il est EXCLU des agrégats de circulation tout en étant
exposé sur sa propre ligne.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.services.credits import credit_bucket
from app.services.dashboard import eco_cockpit_data
from app.services.treasury import TREASURY_EMAIL, treasury_balance, treasury_user_id


async def test_compte_tresorerie_seede_et_non_connectable():
    async with SessionLocal() as db:
        r = (await db.execute(
            text(
                "SELECT id, email, profile_public, is_official, is_treasury, "
                "password_hash, credits_balance, smyles_achetes, smyles_gagnes, "
                "smyles_promo FROM users WHERE is_treasury = TRUE"
            )
        )).all()
    assert len(r) == 1, "il doit exister exactement un compte tresorerie"
    t = r[0]
    assert t.email == TREASURY_EMAIL
    assert t.profile_public is False      # jamais liste / affiche
    assert t.is_official is False         # distinct du profil vitrine « Smyle »
    assert t.password_hash is None        # aucune connexion possible
    # Seede a zero -> invariant A1.4 satisfait des le depart.
    assert t.credits_balance == 0
    assert (t.smyles_achetes, t.smyles_gagnes, t.smyles_promo) == (0, 0, 0)


async def test_resolution_par_drapeau_pas_par_uuid():
    """L'UUID differe par environnement : la resolution doit passer par le
    drapeau is_treasury."""
    async with SessionLocal() as db:
        tid = await treasury_user_id(db)
        row = (await db.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": TREASURY_EMAIL}
        )).first()
    assert tid is not None
    assert tid == row.id


async def test_un_seul_compte_tresorerie_possible():
    """L'index unique partiel interdit un second compte tresorerie."""
    with pytest.raises(IntegrityError):
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO users (id, email, is_treasury) "
                    "VALUES (:id, :e, TRUE)"
                ),
                {"id": uuid.uuid4(), "e": f"t2-{uuid.uuid4().hex[:8]}@smyleplay.example"},
            )
            await db.commit()


async def test_tresorerie_exclue_de_la_circulation_et_exposee_a_part():
    """Garde-fou : crediter la tresorerie ne doit PAS gonfler les Smyles
    « en circulation » (sinon la commission se ferait passer pour des Smyles
    achetes en euros), mais doit apparaitre sur sa ligne dediee."""
    async with SessionLocal() as db:
        tid = await treasury_user_id(db)
        avant = await eco_cockpit_data(db)
        tresor_avant = await treasury_balance(db)
    assert tid is not None
    try:
        async with SessionLocal() as db:
            # Commission encaissee -> bucket NON retirable.
            await credit_bucket(db, tid, 500, bucket="achetes")
            await db.commit()

        async with SessionLocal() as db:
            apres = await eco_cockpit_data(db)
            tresor_apres = await treasury_balance(db)

        # Circulation INCHANGEE (la tresorerie en est exclue).
        assert apres["smyles_en_circulation"] == avant["smyles_en_circulation"]
        assert apres["comptes"] == avant["comptes"]
        # Ligne tresorerie : +500, en achetes, et surtout RIEN en gagnes.
        assert tresor_apres["total"] == tresor_avant["total"] + 500
        assert tresor_apres["achetes"] == tresor_avant["achetes"] + 500
        assert tresor_apres["gagnes"] == 0
        # Invariant A1.4 tenu sur le compte societe.
        assert (
            tresor_apres["achetes"] + tresor_apres["gagnes"] + tresor_apres["promo"]
            == tresor_apres["total"]
        )
    finally:
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET credits_balance = 0, smyles_achetes = 0, "
                    "smyles_gagnes = 0, smyles_promo = 0 WHERE is_treasury = TRUE"
                )
            )
            await db.commit()
