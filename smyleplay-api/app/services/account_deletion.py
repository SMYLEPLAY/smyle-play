"""
Suppression de compte RGPD (pack légal v1, 2026-06-10).

Stratégie : ANONYMISATION, pas d'effacement physique — pour préserver
l'intégrité de l'économie (les exemplaires achetés par d'autres restent
dans leur bibliothèque, les transactions restent cohérentes) tout en
retirant immédiatement toutes les données personnelles.

Effets immédiats :
  1. Tous les contenus de l'artiste sont retirés du public :
     prompts/beats soft-deleted + dépubliés (les acheteurs gardent l'accès,
     règle existante du soft-delete), tracks soft-deleted, voix et ADN
     dépubliés, playlists passées en privé.
  2. Le profil est anonymisé : email remplacé par un alias technique,
     mot de passe invalidé, identité affichée « Artiste supprimé »,
     tous les champs personnels vidés, profil dépublié.
  3. Déconnexion immédiate et définitive : l'auth résout le JWT par email
     (sub=email) — l'email anonymisé ne correspond plus à aucun token
     émis, et le hash « ! » ne peut matcher aucun mot de passe.

Ce qui est CONSERVÉ (anonymisé) : lignes de transactions et d'exemplaires —
nécessaires aux autres utilisateurs et aux obligations comptables
(documenté dans /legal#confidentialite).
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.models.voice import Voice


async def delete_account(db: AsyncSession, user: User) -> None:
    uid = user.id

    # 1. Retrait public de tous les contenus
    await db.execute(
        update(Prompt)
        .where(Prompt.artist_id == uid)
        .values(is_published=False, is_deleted=True)
    )
    await db.execute(
        update(Track).where(Track.artist_id == uid).values(is_deleted=True)
    )
    await db.execute(
        update(Voice).where(Voice.artist_id == uid).values(is_published=False)
    )
    await db.execute(
        update(Adn).where(Adn.artist_id == uid).values(is_published=False)
    )
    await db.execute(
        update(Playlist)
        .where(Playlist.owner_id == uid)
        .values(visibility="private")
    )

    # 2. Anonymisation du profil (tous les champs personnels)
    user.email = f"deleted-{uid}@deleted.watt"
    user.password_hash = "!"  # ne peut matcher aucun hash bcrypt valide
    user.artist_name = "Artiste supprimé"
    user.bio = None
    user.avatar_url = None
    user.cover_photo_url = None
    user.universe_description = None
    user.influences = None
    user.genre = None
    user.city = None
    user.soundcloud = None
    user.instagram = None
    user.youtube = None
    user.tiktok = None
    user.spotify = None
    user.twitter_x = None
    user.brand_color = None
    user.profile_bg_color = None
    user.profile_brand_color = None
    user.roles = None
    user.profile_public = False

    await db.commit()
