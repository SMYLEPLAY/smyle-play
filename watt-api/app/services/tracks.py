from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dna import DNA
from app.models.track import Track
from app.models.user import User
from app.schemas.track import TrackCreate
from app.services.media_ownership import (
    MediaOwnershipError,
    assert_track_media_owned,
    media_url_owned_or_external,
)


class BeatLinkInvalid(Exception):
    """beat_id fourni au PATCH track invalide : inexistant, pas un beat,
    supprimé, ou appartenant à un autre artiste. → 422 côté router."""


class PromptLinkInvalid(Exception):
    """prompt_id fourni (création ou PATCH d'un son) invalide : recette
    inexistante, supprimée, ou appartenant à un autre artiste. → 422."""


__all__ = [
    "BeatLinkInvalid",
    "MediaOwnershipError",
    "PromptLinkInvalid",
    "create_track_with_dna",
    "delete_track",
    "get_user_tracks",
    "patch_track",
    "soft_delete_track",
    "visible_track_clause",
]


def visible_track_clause():
    """Lot A (E3) — condition « son visible publiquement » : ni supprimé par
    son créateur, ni retiré par la modération. À poser sur TOUTE liste ou
    page publique qui lit `tracks`."""
    return and_(Track.is_deleted.is_(False), Track.taken_down_at.is_(None))


async def _assert_prompt_owned(
    db: AsyncSession, *, user: User, prompt_id, current_prompt_id=None
) -> None:
    """Lot A (E2) — un son ne peut porter que la recette de SON créateur.

    Recette inexistante / supprimée / d'un autre artiste → PromptLinkInvalid.
    Seule tolérance : renvoyer inchangée la recette déjà liée (anciens
    éditeurs du tableau de bord qui renvoient tous les champs), à condition
    qu'elle soit bien à ce compte.
    """
    from app.models.prompt import Prompt

    p = (await db.execute(
        select(Prompt).where(Prompt.id == prompt_id)
    )).scalar_one_or_none()
    if p is None or p.artist_id != user.id:
        raise PromptLinkInvalid("Recette introuvable ou pas à toi.")
    if p.is_deleted and prompt_id != current_prompt_id:
        raise PromptLinkInvalid("Recette introuvable ou pas à toi.")


async def create_track_with_dna(
    db: AsyncSession,
    user: User,
    data: TrackCreate,
) -> tuple[Track, DNA]:
    """Atomic creation: NO DNA = NO TRACK.

    Track and DNA are inserted in the same transaction.
    If anything fails, both are rolled back.

    Sprint 1 (2026-05-04) : `cover_url` et `prompt_id` sont passés tels
    quels depuis le payload TrackCreate. Le workflow dashboard typique :
      1. POST /tracks (avec cover_url, sans prompt_id)
      2. POST /artist/me/prompts (crée le prompt, récupère prompt.id)
      3. PATCH /tracks/{id} { prompt_id } pour lier
    Mais on accepte aussi le cas POST direct avec prompt_id (si le
    prompt préexiste) pour réduire le nombre de round-trips.
    """
    # Lot A (C1) — les fichiers désignés (clé R2, URL audio, pochette) doivent
    # venir d'envois de CE compte ; (E2) la recette liée doit être la sienne.
    assert_track_media_owned(
        user.id,
        r2_key=data.r2_key,
        audio_url=data.audio_url,
        cover_url=data.cover_url,
    )
    if data.prompt_id is not None:
        await _assert_prompt_owned(db, user=user, prompt_id=data.prompt_id)

    # Étape 2 — la couleur est optionnelle : si l'artiste n'en a pas choisi,
    # on la laisse à NULL et le front retombera sur sa brandColor.
    track = Track(
        title=data.title,
        artist_id=user.id,
        color=data.color,
        # Sprint 1 PR2 — fields ajoutés pour la migration POST Flask→FastAPI
        audio_url=data.audio_url,
        duration_seconds=data.duration_seconds,
        r2_key=data.r2_key,
        cover_url=data.cover_url,
        prompt_id=data.prompt_id,
        # Tags/moods (migration 0038) — étaient silencieusement perdus à la
        # création : le schéma TrackCreate les accepte et le front les envoie,
        # mais ils n'étaient pas reportés dans le Track → tags=NULL → la
        # recherche par mood (Track.tags ILIKE) ne retrouvait jamais le son.
        tags=data.tags,
        # Plateforme/IA d'origine (migration 0048) — même problème : le
        # <select> dashTrackPlatform était choisi mais jamais persisté.
        # Affiché sur la carte ID avant achat.
        platform=data.platform,
        # C2 — drapeau beat (placement /beats) + BPM optionnel.
        is_beat=bool(getattr(data, "is_beat", False)),
        bpm=getattr(data, "bpm", None),
    )
    db.add(track)
    await db.flush()  # get track.id from the DB

    dna = DNA(
        track_id=track.id,
        artist_id=user.id,
        full_prompt=data.full_prompt,
    )
    db.add(dna)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(track)
    await db.refresh(dna)
    return track, dna


async def patch_track(
    db: AsyncSession,
    *,
    track_id,
    user: User,
    payload,
) -> Track | None:
    """
    PATCH partiel d'un track. Utilisé par le workflow dashboard pour
    lier un prompt_id après coup (track créé d'abord, puis prompt créé,
    puis liaison).

    Renvoie None si track introuvable ou pas owner (le router transforme
    en 404). Sinon retourne le track mis à jour.
    """
    result = await db.execute(
        select(Track).where(
            Track.id == track_id,
            Track.artist_id == user.id,
        )
    )
    track = result.scalar_one_or_none()
    if track is None:
        return None

    # exclude_unset=True pour éviter d'écraser avec None les champs non
    # envoyés. Le caller envoie uniquement ce qu'il veut changer.
    data = payload.model_dump(exclude_unset=True)

    # Lot A (E2) — la recette liée doit appartenir au créateur du son.
    if data.get("prompt_id") is not None:
        await _assert_prompt_owned(
            db, user=user, prompt_id=data["prompt_id"],
            current_prompt_id=track.prompt_id,
        )

    # Lot A (C1) — nouvelle pochette : fichier envoyé par ce compte (ou URL
    # externe). La pochette déjà posée peut être renvoyée telle quelle.
    new_cover = data.get("cover_url")
    if (
        new_cover is not None
        and new_cover != track.cover_url
        and not media_url_owned_or_external(new_cover, user.id)
    ):
        raise MediaOwnershipError("Image non reconnue pour ce compte.")

    # C1 (2026-06-10) — liaison beat : on ne lie JAMAIS un beat qui
    # n'appartient pas à l'artiste courant (sinon n'importe qui pourrait
    # vampiriser le beat d'un autre en pointant son track dessus).
    if data.get("beat_id") is not None:
        from app.models.prompt import Prompt

        beat = (await db.execute(
            select(Prompt).where(
                Prompt.id == data["beat_id"],
                Prompt.product_type == "beat",
                Prompt.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
        if beat is None or beat.artist_id != user.id:
            raise BeatLinkInvalid(
                "beat_id invalide : beat introuvable ou pas à toi."
            )

    for field, value in data.items():
        setattr(track, field, value)

    await db.commit()
    await db.refresh(track)
    return track


async def soft_delete_track(db: AsyncSession, track: Track) -> None:
    """
    Lot A (C1) — suppression DOUCE d'un son par son créateur. Ne commit pas.

    - `is_deleted=True` : le son disparaît des listes publiques, du profil et
      du tableau de bord. La ligne et le fichier audio sont CONSERVÉS
      (aucune purge du stockage) : l'opération reste réversible.
    - Recette liée (prompt_id / beat_id) : si elle appartient au créateur et
      n'est portée par AUCUN autre de ses sons visibles, elle est retirée de
      la vente (`is_published=False`, pas supprimée). Ceux qui l'ont déjà
      achetée la gardent dans leur bibliothèque.
    - Œuvre (son + image) : le lien est défait des deux côtés et l'image
      redevient visible et vendable seule (jamais de produit fantôme).
    """
    from app.models.prompt import Prompt
    from app.services.links import detach_partner_on_removal

    track.is_deleted = True

    # Image posée directement sur ce morceau (0093) → redevient autonome.
    imgs = (await db.execute(
        select(Prompt).where(Prompt.linked_track_id == track.id)
    )).scalars().all()
    for img in imgs:
        img.linked_track_id = None
        img.bundle_exclusive = False

    for pid in {track.prompt_id, track.beat_id} - {None}:
        autre = (await db.execute(
            select(Track.id).where(
                or_(Track.prompt_id == pid, Track.beat_id == pid),
                Track.id != track.id,
                Track.artist_id == track.artist_id,
                visible_track_clause(),
            ).limit(1)
        )).scalar_one_or_none()
        if autre is not None:
            continue
        recette = (await db.execute(
            select(Prompt).where(
                Prompt.id == pid,
                Prompt.artist_id == track.artist_id,
                Prompt.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
        if recette is None:
            continue
        if recette.is_published:
            recette.is_published = False
        await detach_partner_on_removal(db, prompt=recette)
    await db.flush()


async def delete_track(
    db: AsyncSession,
    *,
    track_id,
    user: User,
) -> Track | None:
    """
    Soft-delete d'un track (migration 0028) — voir soft_delete_track.

    - Idempotent : déjà supprimé → None (le router retourne 404).
    - Le DNA associé reste en DB (archivage).
    """
    result = await db.execute(
        select(Track).where(
            Track.id == track_id,
            Track.artist_id == user.id,
            Track.is_deleted.is_(False),
        )
    )
    track = result.scalar_one_or_none()
    if track is None:
        return None

    await soft_delete_track(db, track)
    await db.commit()
    await db.refresh(track)
    return track


async def get_user_tracks(db: AsyncSession, user: User) -> list[Track]:
    result = await db.execute(
        select(Track)
        .where(Track.artist_id == user.id, Track.is_deleted.is_(False))
        .order_by(Track.created_at.desc())
    )
    return list(result.scalars().all())
