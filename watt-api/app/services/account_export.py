"""Export des données personnelles (RGPD art. 15/20 — droit d'accès/portabilité).

Lecture seule : rassemble TOUTES les données rattachées au compte dans un
dictionnaire JSON-sérialisable (fichier téléchargeable depuis le compte).
Pendant à `account_deletion.py` (même inventaire de tables) — Lot D :
profil, consentements, transactions, achats, ventes, œuvres, messages,
signalements faits, abonnements, notifications, parrainages, échanges,
paiements par carte, trophées, activité, likes, téléchargements, décisions
de modération concernant le compte.

Ne figurent PAS : le mot de passe (seulement son empreinte, jamais exportée),
les jetons techniques (connexion, réinitialisation), les données d'autres
personnes au-delà de leur pseudo public.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def _val(v):
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, dict):
        return {k: _val(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_val(x) for x in v]
    return v


def _pick(obj, fields: list[str]) -> dict:
    """Sérialise une liste de champs d'un objet ORM, en tolérant les absents."""
    return {f: _val(getattr(obj, f, None)) for f in fields}


_PROFILE_FIELDS = [
    "id", "email", "email_verified", "artist_name", "bio", "genre", "city", "roles",
    "universe_description", "influences", "avatar_url", "cover_photo_url",
    "brand_color", "profile_bg_color", "profile_brand_color",
    "soundcloud", "instagram", "youtube", "tiktok", "spotify", "twitter_x",
    "language", "profile_public", "is_official", "tier", "referral_code",
    "credits_balance", "credits_earned_total", "smyles_achetes", "smyles_gagnes",
    "smyles_gagnes_bloque", "smyles_promo", "smyles_promo_gagnes",
    "is_pioneer", "pioneer_rank", "pioneer_awarded_at",
    "streak_count", "last_checkin_date", "onboarding_done_at",
    "is_banned", "banned_at", "ban_reason",
    "achat_carte_bloque_at", "achat_carte_bloque_motif",
    "signup_ip", "created_at", "updated_at",
]


async def _rows(db: AsyncSession, sql: str, **params) -> list[dict]:
    res = await db.execute(text(sql), params)
    return [{k: _val(v) for k, v in r._mapping.items()} for r in res.all()]


async def export_account_data(db: AsyncSession, user: User) -> dict:
    u = {"u": user.id}

    def q(sql: str, **extra):
        return _rows(db, sql, **u, **extra)

    transactions = await q(
        "SELECT id, type, status, buyer_id, seller_id, credits_amount, platform_fee, "
        "artist_revenue, promo_paid, promo_non_retirable, euro_amount_cents, metadata_json, "
        "created_at, completed_at FROM transactions "
        "WHERE buyer_id = :u OR seller_id = :u ORDER BY created_at")
    for t in transactions:
        # Les métadonnées d'un crédit admin portent l'email de l'admin : on ne
        # transmet pas les données d'un tiers.
        if isinstance(t.get("metadata_json"), dict):
            t["metadata_json"] = {k: v for k, v in t["metadata_json"].items() if "email" not in k}
        t["sens"] = "achat_ou_debit" if t["buyer_id"] == str(user.id) else "vente_ou_credit"

    return {
        "export_note": (
            "Export de tes données personnelles WATT (droit d'accès et de "
            "portabilité, RGPD art. 15 et 20). Les transactions et exemplaires "
            "sont conservés après une suppression de compte, sous forme "
            "anonymisée, pour la comptabilité et les autres utilisateurs "
            "(cf. /legal#confidentialite)."
        ),
        "format_version": 2,
        "profile": _pick(user, _PROFILE_FIELDS),
        "consentements": {
            "cgu": {
                "version_acceptee": user.accepted_terms_version,
                "acceptee_le": _val(user.accepted_terms_at),
            },
            "mesure_audience": (
                "Ton choix (accepter / refuser) est enregistré uniquement dans ton "
                "navigateur. La mesure n'est jamais rattachée à ton compte : "
                "aucune donnée de mesure ne figure donc ici."
            ),
            "paiements_execution_immediate": await q(
                "SELECT id, consent_immediate_at, created_at FROM stripe_payments "
                "WHERE user_id = :u AND consent_immediate_at IS NOT NULL ORDER BY created_at"),
        },
        "transactions": transactions,
        "achats": {
            "exemplaires": await q(
                "SELECT up.id, up.prompt_id, p.title, up.original_artist_id, up.edition_number, "
                "up.resale_price, up.unlocked_at FROM unlocked_prompts up "
                "LEFT JOIN prompts p ON p.id = up.prompt_id "
                "WHERE up.current_owner_id = :u ORDER BY up.unlocked_at"),
            "adn": await q("SELECT adn_id, owned_at FROM owned_adns WHERE user_id = :u"),
            "adn_visuels": await q(
                "SELECT visual_adn_id, owned_at FROM owned_visual_adns WHERE user_id = :u"),
            "voix": await q(
                "SELECT voice_id, edition_number, owned_at FROM owned_voices WHERE user_id = :u"),
            "adn_playlists": await q(
                "SELECT playlist_id, owned_at FROM owned_playlist_adns WHERE user_id = :u"),
            "adn_albums": await q(
                "SELECT album_id, owned_at FROM owned_album_adns WHERE user_id = :u"),
        },
        "ventes": {
            "transactions": [t for t in transactions if t["seller_id"] == str(user.id)],
            "exemplaires_vendus": await q(
                "SELECT up.prompt_id, p.title, up.edition_number, up.unlocked_at "
                "FROM unlocked_prompts up JOIN prompts p ON p.id = up.prompt_id "
                "WHERE p.artist_id = :u AND up.current_owner_id <> :u ORDER BY up.unlocked_at"),
        },
        "oeuvres": {
            "sons": await q(
                "SELECT id, title, universe, tags, bpm, duration_seconds, audio_url, r2_key, "
                "cover_url, color, prompt_id, beat_id, plays, is_deleted, hidden_at, "
                "taken_down_at, created_at FROM tracks WHERE artist_id = :u ORDER BY created_at"),
            "recettes_et_images": await q(
                "SELECT id, product_type, title, description, prompt_text, lyrics, negative_prompt, "
                "price_credits, max_supply, license_type, universe, is_published, is_deleted, "
                "taken_down_at, created_at, updated_at FROM prompts WHERE artist_id = :u "
                "ORDER BY created_at"),
            "adn": await q(
                "SELECT id, description, usage_guide, example_outputs, ai_reference, price_credits, "
                "is_published, is_deleted, taken_down_at, created_at FROM adns WHERE artist_id = :u"),
            "adn_visuels": await q(
                "SELECT id, description, usage_guide, example_outputs, style, palette, price_credits, "
                "is_published, is_deleted, taken_down_at, created_at FROM visual_adns "
                "WHERE artist_id = :u"),
            "voix": await q(
                "SELECT id, name, style, genres, license, price_credits, sample_url, preview_url, "
                "is_published, is_deleted, taken_down_at, created_at FROM voices_for_sale "
                "WHERE artist_id = :u"),
            "playlists": await q(
                "SELECT p.id, p.title, p.visibility, p.color, p.seed_prompt, p.dna_description, "
                "p.adn_for_sale, p.adn_price, p.oeuvre_slug, p.taken_down_at, p.created_at, "
                "(SELECT array_agg(pt.track_id ORDER BY pt.position) FROM playlist_tracks pt "
                " WHERE pt.playlist_id = p.id) AS sons FROM playlists p WHERE p.owner_id = :u"),
            "albums": await q(
                "SELECT id, title, visibility, seed_prompt, dna_description, adn_style, adn_palette, "
                "adn_for_sale, adn_price, oeuvre_slug, universe, taken_down_at, created_at "
                "FROM albums WHERE owner_id = :u"),
        },
        "messages": await q(
            "SELECT m.id, m.thread_id, CASE WHEN m.sender_id = :u THEN 'envoye' ELSE 'recu' END "
            "AS sens, CASE WHEN m.sender_id = :u THEN NULL ELSE su.artist_name END AS de, "
            "m.content, m.read_at, m.created_at FROM messages m "
            "JOIN message_threads t ON t.id = m.thread_id "
            "LEFT JOIN users su ON su.id = m.sender_id "
            "WHERE t.participant_a = :u OR t.participant_b = :u ORDER BY m.created_at"),
        "signalements_faits": await q(
            "SELECT id, target_type, target_id, reason, detail, status, created_at, resolved_at "
            "FROM content_reports WHERE reporter_id = :u OR lower(reporter_email) = lower(:e) "
            "ORDER BY created_at", e=user.email or ""),
        "abonnements": {
            "je_suis": await q(
                "SELECT f.followee_id AS compte_id, x.artist_name AS pseudo, f.created_at "
                "FROM user_follows f LEFT JOIN users x ON x.id = f.followee_id "
                "WHERE f.follower_id = :u ORDER BY f.created_at"),
            "me_suivent": await q(
                "SELECT x.artist_name AS pseudo, f.created_at FROM user_follows f "
                "LEFT JOIN users x ON x.id = f.follower_id WHERE f.followee_id = :u "
                "ORDER BY f.created_at"),
        },
        "notifications": await q(
            "SELECT id, type, target_type, target_id, metadata_json, read_at, created_at "
            "FROM notifications WHERE user_id = :u ORDER BY created_at"),
        "parrainages": await q(
            "SELECT id, CASE WHEN referrer_id = :u THEN 'parrain' ELSE 'filleul' END AS role, "
            "status, reward_credits, created_at, rewarded_at FROM referrals "
            "WHERE referrer_id = :u OR referred_id = :u"),
        "echanges": await q(
            "SELECT id, CASE WHEN sender_id = :u THEN 'envoye' ELSE 'recu' END AS sens, "
            "offered_prompt_id, requested_prompt_id, credit_supplement, target_type, target_id, "
            "amount_credits, status, message, created_at, resolved_at FROM trade_offers "
            "WHERE sender_id = :u OR receiver_id = :u ORDER BY created_at"),
        "paiements_carte": await q(
            "SELECT id, pack_id, credits, amount_cents, currency, status, smyles_recovered, "
            "shortfall, created_at FROM stripe_payments WHERE user_id = :u ORDER BY created_at"),
        "trophees": await q(
            "SELECT achievement_id, unlocked_at, reward_forfeited FROM user_achievements "
            "WHERE user_id = :u"),
        "activite_jours": await q(
            "SELECT day, listened FROM user_activity_days WHERE user_id = :u ORDER BY day"),
        "likes": await q("SELECT prompt_id, created_at FROM prompt_likes WHERE user_id = :u"),
        "telechargements": await q(
            "SELECT product_id, kind, created_at FROM download_events WHERE user_id = :u "
            "ORDER BY created_at"),
        "decisions_de_moderation": await q(
            "SELECT action, cible_type, motif, created_at FROM admin_journal "
            "WHERE cible_id = :ut ORDER BY created_at", ut=str(user.id)),
    }
