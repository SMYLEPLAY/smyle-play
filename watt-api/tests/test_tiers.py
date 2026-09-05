"""Paliers créateur (C6) — config commission/emplacements + split tier-aware."""
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import artist_pct_for_user, compute_split
from app.services.tiers import (
    UserTier,
    artist_pct_for_tier,
    commission_pct_for_tier,
    is_featured_tier,
    listing_slots_for_tier,
    normalize_tier,
    tier_public_info,
)
from app.services.users import create_user


# --- Config pure (sans DB) -------------------------------------------------

def test_commission_bareme():
    assert commission_pct_for_tier(UserTier.STANDARD) == 20
    assert commission_pct_for_tier(UserTier.PREMIUM) == 12
    assert commission_pct_for_tier(UserTier.MYTHIQUE) == 5


def test_artist_pct_complement():
    assert artist_pct_for_tier("standard") == 80
    assert artist_pct_for_tier("premium") == 88
    assert artist_pct_for_tier("mythique") == 95


def test_listing_slots():
    assert listing_slots_for_tier("standard") == 10
    assert listing_slots_for_tier("premium") == 50
    assert listing_slots_for_tier("mythique") is None  # illimité


def test_featured_flag():
    assert is_featured_tier("standard") is False
    assert is_featured_tier("premium") is True
    assert is_featured_tier("mythique") is True


def test_normalize_tier_robuste():
    # NULL / vide / casse / inconnu → Standard (jamais de crash)
    assert normalize_tier(None) is UserTier.STANDARD
    assert normalize_tier("") is UserTier.STANDARD
    assert normalize_tier("PREMIUM") is UserTier.PREMIUM
    assert normalize_tier("  Mythique ") is UserTier.MYTHIQUE
    assert normalize_tier("inconnu") is UserTier.STANDARD


def test_tier_public_info_shape():
    info = tier_public_info("premium")
    assert info == {
        "tier": "premium",
        "label": "Premium",
        "commission_pct": 12,
        "artist_pct": 88,
        "listing_slots": 50,
        "featured": True,
    }


def test_split_par_palier():
    # 100 crédits : Standard 80/20, Premium 88/12, Mythique 95/5.
    assert compute_split(100, artist_pct_for_tier("standard")) == (80, 20)
    assert compute_split(100, artist_pct_for_tier("premium")) == (88, 12)
    assert compute_split(100, artist_pct_for_tier("mythique")) == (95, 5)


# --- Helper DB : palier du vendeur --------------------------------------

async def test_artist_pct_for_user_lit_le_palier():
    email = f"pytest-tier-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        # Défaut = standard → 80%
        async with SessionLocal() as db:
            assert await artist_pct_for_user(db, uid) == 80
        # Promotion premium → 88%
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE users SET tier = 'premium' WHERE id = :id"),
                {"id": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            assert await artist_pct_for_user(db, uid) == 88
        # Mythique → 95%
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE users SET tier = 'mythique' WHERE id = :id"),
                {"id": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            assert await artist_pct_for_user(db, uid) == 95
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


# =============================================================================
# K-07 (2026-09-04, tâche B-M8) — la commission suit le palier du vendeur
# PARTOUT, pas seulement sur unlock_prompt_atomic.
#
# Avant : voices, packs (mystère + produit), œuvre, ADN visuel et les ADN
# playlist/album appelaient compute_split(montant) sans palier → 20 % en dur,
# alors que la page Offres promet 12 % (Premium) et 5 % (Mythique).
# Un test par service : vendeur `premium` → 88 % du montant payé.
# =============================================================================


from app.models.transaction import Transaction, TransactionType  # noqa: E402

PREMIUM_PCT = 88


async def _make_seller_premium() -> uuid.UUID:
    email = f"pytest-k07s-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET tier = 'premium', credits_balance = 0, "
                 "artist_name = 'K07 Seller' WHERE id = :u"),
            {"u": uid},
        )
        await db.commit()
    return uid


async def _make_buyer(balance: int = 5000) -> uuid.UUID:
    email = f"pytest-k07b-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET credits_balance = :b WHERE id = :u"),
            {"b": balance, "u": uid},
        )
        await db.commit()
    return uid


# ── Fabriques de produit + exécution de la vente, par service ──────────────

async def _sell_voice(seller, buyer):
    from app.models.voice import Voice
    from app.services.voices import unlock_voice_atomic
    async with SessionLocal() as db:
        v = Voice(
            artist_id=seller,
            name="K07 Voice",
            style="calme",
            genres=[],
            sample_url="https://example.invalid/s.mp3",
            license="personnel",
            price_credits=100,
            is_published=True,
        )
        db.add(v)
        await db.commit()
        await db.refresh(v)
        vid = v.id
    async with SessionLocal() as db:
        await unlock_voice_atomic(db, buyer_id=buyer, voice_id=vid)
        await db.commit()


async def _sell_visual_adn(seller, buyer):
    from app.models.visual_adn import VisualAdn
    from app.services.visual_adn import unlock_visual_adn_atomic
    async with SessionLocal() as db:
        v = VisualAdn(
            artist_id=seller,
            description="D" * 220,
            price_credits=100,
            is_published=True,
        )
        db.add(v)
        await db.commit()
        await db.refresh(v)
        vid = v.id
    async with SessionLocal() as db:
        await unlock_visual_adn_atomic(db, buyer_id=buyer, visual_adn_id=vid)
        await db.commit()


async def _sell_playlist_adn(seller, buyer):
    from app.models.playlist import Playlist
    from app.services.unlocks import unlock_playlist_adn_atomic
    async with SessionLocal() as db:
        p = Playlist(
            owner_id=seller,
            title=f"K07 PL {uuid.uuid4().hex[:6]}",
            visibility="public",
            adn_for_sale=True,
            adn_price=100,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        pid = p.id
    async with SessionLocal() as db:
        await unlock_playlist_adn_atomic(db, buyer_id=buyer, playlist_id=pid)
        await db.commit()


async def _sell_album_adn(seller, buyer):
    from app.models.album import Album
    from app.services.unlocks import unlock_album_adn_atomic
    async with SessionLocal() as db:
        a = Album(
            owner_id=seller,
            title=f"K07 AL {uuid.uuid4().hex[:6]}",
            visibility="public",
            adn_for_sale=True,
            adn_price=100,
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        aid = a.id
    async with SessionLocal() as db:
        await unlock_album_adn_atomic(db, buyer_id=buyer, album_id=aid)
        await db.commit()


async def _make_prompt(seller, *, kind: str = "recipe", price: int = 100):
    from app.models.prompt import Prompt
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=seller,
            title=f"K07 {kind} {uuid.uuid4().hex[:6]}",
            description="x",
            prompt_text="Y" * 120,
            price_credits=price,
            is_published=True,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _sell_pack_produit(seller, buyer):
    from app.models.track import Track
    from app.services.pack_purchase import buy_pack_atomic
    recipe = await _make_prompt(seller, kind="recipe")
    beat = await _make_prompt(seller, kind="beat")
    async with SessionLocal() as db:
        t = Track(
            title=f"K07 Track {uuid.uuid4().hex[:6]}",
            artist_id=seller,
            prompt_id=recipe,
            beat_id=beat,
            pack_price_credits=100,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        tid = t.id
    async with SessionLocal() as db:
        await buy_pack_atomic(db, buyer_id=buyer, track_id=tid)
        await db.commit()


async def _sell_pack_mystere(seller, buyer):
    from app.services.packs import open_mystery_pack_atomic
    # Le pool est constitué des prompts pack_eligible d'AUTRUI. Supply illimité
    # → pas de top-up « prix fort » qui brouillerait l'assertion.
    await _make_prompt(seller, kind="pool", price=100)
    async with SessionLocal() as db:
        await open_mystery_pack_atomic(db, buyer)
        await db.commit()


async def _sell_oeuvre(seller, buyer):
    from app.models.album import Album
    from app.models.playlist import Playlist
    from app.services.oeuvre_purchase import buy_oeuvre_atomic
    slug = f"k07-oeuvre-{uuid.uuid4().hex[:8]}"
    async with SessionLocal() as db:
        db.add(Playlist(
            owner_id=seller, title="K07 face son", visibility="public",
            adn_for_sale=True, adn_price=100, oeuvre_slug=slug,
        ))
        db.add(Album(
            owner_id=seller, title="K07 face image", visibility="public",
            adn_for_sale=True, adn_price=100, oeuvre_slug=slug,
        ))
        await db.commit()
    async with SessionLocal() as db:
        await buy_oeuvre_atomic(db, buyer_id=buyer, slug=slug)
        await db.commit()


_SERVICES = {
    # nom du cas → (module concerné, fabrique+vente)
    "voices": _sell_voice,
    "visual_adn": _sell_visual_adn,
    "unlocks.playlist_adn": _sell_playlist_adn,
    "unlocks.album_adn": _sell_album_adn,
    "pack_purchase": _sell_pack_produit,
    "packs.mystery": _sell_pack_mystere,
    "oeuvre_purchase": _sell_oeuvre,
}


@pytest.mark.parametrize("service", sorted(_SERVICES))
async def test_commission_suit_le_palier_du_vendeur(service):
    """Vendeur Premium : 88 % pour l'artiste, 12 % pour la plateforme.

    On lit la transaction UNLOCK émise par le service : `artist_revenue` doit
    valoir `credits_amount * 88 // 100` (compute_split laisse l'arrondi à la
    plateforme) et la somme doit être conservée.
    """
    seller = await _make_seller_premium()
    buyer = await _make_buyer()
    try:
        await _SERVICES[service](seller, buyer)

        async with SessionLocal() as db:
            rows = (await db.execute(
                select(Transaction).where(
                    Transaction.buyer_id == buyer,
                    Transaction.seller_id == seller,
                    Transaction.type == TransactionType.UNLOCK,
                )
            )).scalars().all()
        assert rows, f"{service} : aucune transaction de vente émise"
        for tx in rows:
            amount = int(tx.credits_amount)
            assert int(tx.artist_revenue) == amount * PREMIUM_PCT // 100, (
                f"{service} : palier vendeur ignoré "
                f"({tx.artist_revenue} sur {amount})"
            )
            assert int(tx.artist_revenue) + int(tx.platform_fee) == amount
    finally:
        async with SessionLocal() as db:
            await db.execute(text("SET session_replication_role = 'replica'"))
            await db.execute(delete(Transaction).where(
                (Transaction.buyer_id.in_([buyer, seller]))
                | (Transaction.seller_id.in_([buyer, seller]))
            ))
            await db.execute(text("SET session_replication_role = 'origin'"))
            await db.execute(delete(User).where(User.id.in_([buyer, seller])))
            await db.commit()
