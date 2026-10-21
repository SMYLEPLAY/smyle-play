"""Lot K — l'acheteur amené par le créateur paie 10 % de commission.

  - code du vendeur dans le lien (?ref=CODE transmis en `via`) → 10 % ;
  - acheteur inscrit par le parrainage du vendeur → 10 %, sans `via` ;
  - code d'un AUTRE créateur → commission normale (20 %) ;
  - tableau de croissance admin : créateurs qui publient, inscrits amenés.
"""
import uuid

from sqlalchemy import delete, select, text

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.referral import Referral
from app.models.track import Track
from app.models.transaction import Transaction, TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.croissance import tableau
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import create_user

RECETTE = "R" * 120


async def _compte(nom: str, solde: int = 0) -> tuple[uuid.UUID, str]:
    email = f"pytest-lotk-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid, code = u.id, u.referral_code
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET credits_balance = :b, smyles_achetes = :b, smyles_gagnes = 0, "
            "smyles_promo = 0, artist_name = :n WHERE id = :u"), {"b": solde, "n": nom, "u": uid})
        await db.commit()
    return uid, code


async def _recette(vendeur: uuid.UUID, prix: int = 20) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=vendeur, title="Lien créateur", prompt_text=RECETTE,
                   price_credits=prix, is_published=True, prompt_platform="suno",
                   prompt_model_version="Suno v6", prompt_vocal_gender="instrumental")
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _achat(acheteur, recette, via=None) -> Transaction:
    async with SessionLocal() as db:
        await unlock_prompt_atomic(db, buyer_id=acheteur, prompt_id=recette, via=via)
        await db.commit()
    async with SessionLocal() as db:
        return (await db.execute(select(Transaction).where(
            Transaction.buyer_id == acheteur, Transaction.type == TransactionType.UNLOCK,
        ))).scalars().one()


async def _nettoie(*ids):
    async with SessionLocal() as db:
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(delete(Transaction).where(
            Transaction.buyer_id.in_(ids) | Transaction.seller_id.in_(ids)))
        await db.execute(delete(UnlockedPrompt).where(UnlockedPrompt.current_owner_id.in_(ids)))
        await db.execute(text("SET session_replication_role = 'origin'"))
        await db.execute(delete(Referral).where(
            Referral.referrer_id.in_(ids) | Referral.referred_id.in_(ids)))
        await db.execute(delete(Prompt).where(Prompt.artist_id.in_(ids)))
        await db.execute(delete(Track).where(Track.artist_id.in_(ids)))
        await db.execute(delete(User).where(User.id.in_(ids)))
        await db.commit()


async def test_code_du_vendeur_dans_le_lien():
    vendeur, code = await _compte("LK Vendeur")
    acheteur, _ = await _compte("LK Acheteur", 500)
    try:
        tx = await _achat(acheteur, await _recette(vendeur), via=code.lower())
        assert (tx.artist_revenue, tx.platform_fee) == (18, 2)
        assert tx.metadata_json.get("via_createur") is True
    finally:
        await _nettoie(vendeur, acheteur)


async def test_code_d_un_autre_createur_ne_change_rien():
    vendeur, _ = await _compte("LK Vendeur2")
    autre, code_autre = await _compte("LK Autre")
    acheteur, _ = await _compte("LK Acheteur2", 500)
    try:
        tx = await _achat(acheteur, await _recette(vendeur), via=code_autre)
        assert (tx.artist_revenue, tx.platform_fee) == (16, 4)
        assert "via_createur" not in (tx.metadata_json or {})
    finally:
        await _nettoie(vendeur, autre, acheteur)


async def test_filleul_du_vendeur_sans_lien():
    vendeur, _ = await _compte("LK Parrain")
    acheteur, _ = await _compte("LK Filleul", 500)
    try:
        async with SessionLocal() as db:
            db.add(Referral(referrer_id=vendeur, referred_id=acheteur))
            await db.commit()
        tx = await _achat(acheteur, await _recette(vendeur))
        assert (tx.artist_revenue, tx.platform_fee) == (18, 2)
    finally:
        await _nettoie(vendeur, acheteur)


async def test_tableau_de_croissance():
    createur, _ = await _compte("LK Créateur")
    filleul, _ = await _compte("LK Inscrit")
    try:
        async with SessionLocal() as db:
            db.add(Track(artist_id=createur, title="Son", r2_key=f"tracks/{createur}/x.mp3"))
            db.add(Referral(referrer_id=createur, referred_id=filleul))
            await db.commit()
        async with SessionLocal() as db:
            t = await tableau(db)
        ligne = next(c for c in t["createurs"] if c["pseudo"] == "LK Créateur")
        assert ligne["oeuvres"] == 1 and ligne["inscrits"] == 1
        assert t["createursPubliants"] >= 1 and t["createursQuiAmenent"] >= 1
    finally:
        await _nettoie(createur, filleul)


async def test_route_croissance_reservee_admin(client, auth_headers):
    r = await client.get("/admin/croissance", headers=auth_headers)
    assert r.status_code in (401, 403)
