"""Export des données personnelles (RGPD art. 15/20 — droit d'accès/portabilité).

Lecture seule : rassemble tout ce que le compte possède (profil, contenus,
achats, transactions) dans un dictionnaire JSON-sérialisable. Aucune écriture.
Pendant à `account_deletion.py` (même inventaire d'entités).
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.transaction import Transaction
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.models.voice import Voice


def _val(v):
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, enum.Enum):
        return v.value
    return v


def _pick(obj, fields: list[str]) -> dict:
    """Sérialise une liste de champs d'un objet ORM, en tolérant les absents."""
    return {f: _val(getattr(obj, f, None)) for f in fields}


_PROFILE_FIELDS = [
    "id", "email", "artist_name", "bio", "genre", "city", "roles",
    "universe_description", "influences", "avatar_url", "cover_photo_url",
    "brand_color", "profile_bg_color", "profile_brand_color",
    "soundcloud", "instagram", "youtube", "tiktok", "spotify", "twitter_x",
    "profile_public", "is_official", "tier", "referral_code",
    "credits_balance", "smyles_achetes", "smyles_gagnes", "smyles_promo",
    "signup_ip", "accepted_terms_at", "created_at",
]


async def export_account_data(db: AsyncSession, user: User) -> dict:
    uid = user.id

    async def _all(model, where):
        return (await db.execute(select(model).where(where))).scalars().all()

    tracks = await _all(Track, Track.artist_id == uid)
    prompts = await _all(Prompt, Prompt.artist_id == uid)
    voices = await _all(Voice, Voice.artist_id == uid)
    adns = await _all(Adn, Adn.artist_id == uid)
    playlists = await _all(Playlist, Playlist.owner_id == uid)
    library = await _all(UnlockedPrompt, UnlockedPrompt.current_owner_id == uid)
    txs = await _all(
        Transaction,
        or_(Transaction.buyer_id == uid, Transaction.seller_id == uid),
    )

    return {
        "export_note": (
            "Export de tes données personnelles WATT (droit d'accès RGPD). "
            "Les transactions et exemplaires sont conservés pour l'intégrité "
            "comptable et les autres utilisateurs (cf. /legal#confidentialite)."
        ),
        "profile": _pick(user, _PROFILE_FIELDS),
        "tracks": [
            _pick(t, ["id", "title", "genre", "universe", "cover_url",
                      "is_deleted", "created_at"]) for t in tracks
        ],
        "prompts": [
            _pick(p, ["id", "title", "product_type", "price_credits",
                      "is_published", "is_deleted", "created_at"]) for p in prompts
        ],
        "voices": [
            _pick(v, ["id", "name", "is_published", "created_at"]) for v in voices
        ],
        "adns": [
            _pick(a, ["id", "title", "is_published", "created_at"]) for a in adns
        ],
        "playlists": [
            _pick(pl, ["id", "name", "visibility", "created_at"]) for pl in playlists
        ],
        "library_purchases": [
            _pick(u, ["id", "prompt_id", "original_artist_id",
                      "edition_number", "unlocked_at"]) for u in library
        ],
        "transactions": [
            _pick(tx, ["id", "type", "status", "credits_amount",
                       "platform_fee", "artist_revenue", "euro_amount_cents",
                       "created_at", "completed_at"]) for tx in txs
        ],
    }
