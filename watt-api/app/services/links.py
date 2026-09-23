"""
Service de liaison « Oeuvre complete » (C4).

Lie un SON (prompt product_type 'recipe'/'beat') et une IMAGE (product_type
'image') en deux produits INDEPENDANTS mais relies pour l'affichage. Lien 1:1
strict, nature croisee obligatoire (image <-> son, jamais image <-> image,
jamais son <-> son).

La colonne prompts.linked_prompt_id (migration 0059) porte le pointeur des
DEUX cotes (chaque produit pointe vers son partenaire). Pose/clear atomiques.

Aucun couplage avec l'achat : lier deux produits ne change NI leur prix NI
leur rarete NI leur recette — c'est purement un lien d'affichage. La recette
de l'un n'est jamais exposee via l'autre (cf. helpers de payload qui ne
sortent qu'id/titre/apercu/cover/prix).
"""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt

# Natures « son » (audio vendable) vs « image ».
_SOUND_TYPES = ("recipe", "beat")
_IMAGE_TYPE = "image"


class LinkError(Exception):
    """Erreur de liaison generique (HTTP traduit par le router)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _is_sound(p: Prompt) -> bool:
    return p.product_type in _SOUND_TYPES


def _is_image(p: Prompt) -> bool:
    return p.product_type == _IMAGE_TYPE


async def _load_owned_prompt_or_404(
    db: AsyncSession, *, prompt_id: _uuid.UUID, owner_id: _uuid.UUID
) -> Prompt:
    """
    Charge un prompt appartenant a owner (non soft-deleted), sinon 404
    (anti-enumeration : inexistant / pas owner / supprime → meme 404).
    """
    p = (await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.artist_id == owner_id,
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if p is None:
        raise LinkError(404, "Produit introuvable.")
    return p


async def link_products(
    db: AsyncSession,
    *,
    owner_id: _uuid.UUID,
    prompt_a_id: _uuid.UUID,
    prompt_b_id: _uuid.UUID,
    bundle_exclusive: bool = False,
) -> tuple[Prompt, Prompt]:
    """
    Lie deux produits de l'artiste owner en une « oeuvre complete ».

    Verifie : les deux existent et appartiennent a owner (404 sinon), l'un est
    une IMAGE et l'autre un SON (409 si natures incompatibles), aucun des deux
    n'est deja lie (409, 1:1 strict). Pose linked_prompt_id sur LES DEUX cotes
    et flush (commit a la charge de l'appelant).

    bundle_exclusive : nature du lien (pose sur LES DEUX produits).
      - True  = « ne ensemble » (flux A, les deux crees dans la meme action).
                Les produits disparaissent des CARTES INDIVIDUELLES sur les
                surfaces publiques (ils n'apparaissent que via la carte
                « Oeuvre complete »). L'achat separe reste possible.
      - False = « lie apres coup » (flux B / lien manuel). Les deux restent
                visibles individuellement ET forment une oeuvre.
    Defaut False : tout appel non explicite est un lien apres coup.

    Retourne (prompt_a, prompt_b) rafraichis.
    """
    if prompt_a_id == prompt_b_id:
        raise LinkError(409, "Un produit ne peut pas etre lie a lui-meme.")

    a = await _load_owned_prompt_or_404(db, prompt_id=prompt_a_id, owner_id=owner_id)
    b = await _load_owned_prompt_or_404(db, prompt_id=prompt_b_id, owner_id=owner_id)

    # Nature croisee obligatoire : exactement une image + un son.
    if not ((_is_image(a) and _is_sound(b)) or (_is_sound(a) and _is_image(b))):
        raise LinkError(
            409,
            "Une oeuvre complete relie un son ET une image (jamais deux "
            "produits de meme nature).",
        )

    # 1:1 strict : aucun des deux ne doit deja avoir de partenaire.
    if a.linked_prompt_id is not None or b.linked_prompt_id is not None:
        raise LinkError(
            409,
            "L'un des deux produits est deja lie a une autre oeuvre complete.",
        )

    # Lot 2 : le morceau de la recette a peut-être déjà une image posée
    # directement sur lui (0093) → ce son a déjà son Œuvre.
    son = a if _is_sound(a) else b
    from app.models.track import Track

    deja = (await db.execute(
        select(Prompt.id).join(Track, Prompt.linked_track_id == Track.id).where(
            Track.prompt_id == son.id
        ).limit(1)
    )).scalar_one_or_none()
    if deja is not None:
        raise LinkError(409, "Ce son a déjà une image.")
    image = b if son is a else a
    if image.linked_track_id is not None:
        raise LinkError(409, "Cette image est déjà dans une autre Œuvre.")

    a.linked_prompt_id = b.id
    b.linked_prompt_id = a.id
    # Nature du lien posee symetriquement sur les deux cotes.
    a.bundle_exclusive = bundle_exclusive
    b.bundle_exclusive = bundle_exclusive
    await db.flush()
    return a, b


async def linkable_candidates(
    db: AsyncSession,
    *,
    owner_id: _uuid.UUID,
    prompt_id: _uuid.UUID,
) -> list[dict]:
    """
    Liste les produits de owner eligibles a etre lies a prompt_id (C4 lien
    retroactif). Renvoie un APERCU LEGER par candidat — JAMAIS de champ gate
    (prompt_text / lyrics / image_r2_key / image_settings / negative_prompt).

    Criteres d'eligibilite :
      - nature OPPOSEE a prompt_id (si prompt_id est une image → on renvoie ses
        SONS recipe/beat ; si c'est un son → ses IMAGES),
      - owner = owner_id, is_deleted=False, linked_prompt_id IS NULL (libre),
      - exclut prompt_id lui-meme.

    Si prompt_id est deja lie, on renvoie quand meme la liste des candidats
    libres (le front masque le bloc de selection dans ce cas) — pas d'erreur.

    404 (LinkError) si prompt_id n'existe pas / pas owner / supprime.

    Forme par candidat : {id, title, productType, priceCredits, coverUrl?,
    previewKey?} — coverUrl pour un son (cover_url du Track lie), previewKey
    pour une image (preview_r2_key).
    """
    pivot = await _load_owned_prompt_or_404(
        db, prompt_id=prompt_id, owner_id=owner_id
    )

    # Nature opposee : image → on cherche des sons ; son → on cherche des images.
    if _is_image(pivot):
        wanted_types = list(_SOUND_TYPES)
        wanted_is_image = False
        # Lot 2 : les MORCEAUX sans recette sont aussi des sons liables.
        extra_tracks = await _free_tracks_without_recipe(db, owner_id)
    elif _is_sound(pivot):
        wanted_types = [_IMAGE_TYPE]
        wanted_is_image = True
    else:
        # Type inconnu : aucun candidat liable.
        return []

    rows = (await db.execute(
        select(Prompt).where(
            Prompt.artist_id == owner_id,
            Prompt.is_deleted.is_(False),
            Prompt.linked_prompt_id.is_(None),
            Prompt.product_type.in_(wanted_types),
            Prompt.id != prompt_id,
        ).order_by(Prompt.created_at.desc())
    )).scalars().all()

    out: list[dict] = []
    if wanted_is_image:
        # Candidats IMAGE : apercu = preview_r2_key (jamais l'original).
        for p in rows:
            out.append({
                "id":           str(p.id),
                "title":        p.title,
                "productType":  p.product_type,
                "priceCredits": p.price_credits,
                "previewKey":   p.preview_r2_key or "",
            })
    else:
        # Candidats SON : cover = cover_url du Track lie (track.prompt_id == p.id).
        from app.models.track import Track

        cover_by_prompt: dict[_uuid.UUID, str] = {}
        if rows:
            cover_rows = (await db.execute(
                select(Track.prompt_id, Track.cover_url).where(
                    Track.prompt_id.in_([p.id for p in rows]),
                    Track.is_deleted.is_(False),
                )
            )).all()
            for pid, cover in cover_rows:
                if pid is not None and pid not in cover_by_prompt:
                    cover_by_prompt[pid] = cover or ""
        for p in rows:
            out.append({
                "id":           str(p.id),
                "kind":         "prompt",
                "title":        p.title,
                "productType":  p.product_type,
                "priceCredits": p.price_credits,
                "coverUrl":     cover_by_prompt.get(p.id, ""),
            })
        # Lot 2 : morceaux sans recette (écoute seule) → kind « track » ;
        # le front les lie par POST /artist/me/tracks/{id}/link.
        for t in extra_tracks:
            out.append({
                "id":           str(t.id),
                "kind":         "track",
                "title":        t.title,
                "productType":  "track",
                "priceCredits": None,
                "coverUrl":     t.cover_url or "",
            })
    return out


async def unlink_products(
    db: AsyncSession,
    *,
    owner_id: _uuid.UUID,
    prompt_id: _uuid.UUID,
) -> Prompt:
    """
    Delie un produit de l'artiste owner. Clear linked_prompt_id des DEUX cotes
    (le produit ET son partenaire, si encore present). Idempotent : si le
    produit n'est pas lie, ne fait rien. Le partenaire est resolu via le
    pointeur stocke ; s'il a disparu, on clear quand meme notre cote.
    """
    p = await _load_owned_prompt_or_404(db, prompt_id=prompt_id, owner_id=owner_id)
    partner_id = p.linked_prompt_id
    p.linked_prompt_id = None
    # Lot 2 : une image peut aussi être liée à un MORCEAU (linked_track_id).
    p.linked_track_id = None
    if _is_sound(p):
        # Délier une recette délie aussi l'image posée sur son morceau.
        await _clear_track_link_of_recipe(db, p.id)
    # Le produit delie redevient un produit individuel ordinaire : il ne peut
    # plus etre « ne ensemble » (plus de partenaire). On le remet visible.
    p.bundle_exclusive = False
    if partner_id is not None:
        partner = (await db.execute(
            select(Prompt).where(Prompt.id == partner_id)
        )).scalar_one_or_none()
        if partner is not None and partner.linked_prompt_id == p.id:
            partner.linked_prompt_id = None
            partner.linked_track_id = None
            # Jamais de produit fantome invisible : le survivant redevient
            # visible individuellement (bundle_exclusive=False).
            partner.bundle_exclusive = False
    await db.flush()
    return p


async def detach_partner_on_removal(
    db: AsyncSession, *, prompt: Prompt
) -> None:
    """
    A appeler lors du soft-delete d'un produit (image OU son) qui peut etre
    moitie d'une oeuvre complete. Coupe le lien des DEUX cotes et remet le
    SURVIVANT en bundle_exclusive=False (visible + vendable individuellement),
    afin de ne JAMAIS laisser un produit fantome invisible et invendable.

    Le produit supprime lui-meme voit son linked_prompt_id efface (coherence) ;
    il sortira de toute facon des listings via is_deleted. Idempotent si le
    produit n'etait pas lie. Ne commit pas (flush seulement) — l'appelant gere
    la transaction du delete.
    """
    # Lot 2 : une image liée à un MORCEAU (sans recette) est aussi détachée.
    if prompt.linked_track_id is not None:
        prompt.linked_track_id = None
        prompt.bundle_exclusive = False
    if _is_sound(prompt):
        await _clear_track_link_of_recipe(db, prompt.id)
    partner_id = prompt.linked_prompt_id
    if partner_id is None:
        await db.flush()
        return
    prompt.linked_prompt_id = None
    prompt.bundle_exclusive = False
    partner = (await db.execute(
        select(Prompt).where(Prompt.id == partner_id)
    )).scalar_one_or_none()
    if partner is not None and partner.linked_prompt_id == prompt.id:
        partner.linked_prompt_id = None
        partner.linked_track_id = None
        partner.bundle_exclusive = False
    await db.flush()


# ──────────────────────────────────────────────────────────────────────────
# Payloads partenaire (anti-fuite). On n'expose JAMAIS la recette/original du
# partenaire : seulement id, titre, apercu/cover, prix, productType. Utilises
# par images.py (linkedSound sur la carte image) et watt_compat.py
# (linkedImage sur la carte son/profil).
# ──────────────────────────────────────────────────────────────────────────


async def _partner_prompt(
    db: AsyncSession, p: Prompt
) -> Prompt | None:
    """Charge le partenaire lie de p (None si pas lie / introuvable / supprime)."""
    if p.linked_prompt_id is None:
        return None
    partner = (await db.execute(
        select(Prompt).where(
            Prompt.id == p.linked_prompt_id,
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    return partner


async def linked_sound_payload(db: AsyncSession, image: Prompt) -> dict | None:
    """
    Pour une IMAGE liee, renvoie l'apercu PUBLIC de son SON partenaire :
    {id, title, coverUrl, priceCredits, productType}. La cover du son =
    cover_url du Track qui pointe ce prompt (track.prompt_id == son.id).
    Aucune recette/lyrics n'est exposee. None si pas lie ou partenaire non son.
    """
    if image.linked_prompt_id is None and image.linked_track_id is not None:
        # Lot 2 (0093) : image liée à un MORCEAU sans recette.
        from app.models.track import Track

        t = (await db.execute(
            select(Track).where(Track.id == image.linked_track_id, Track.is_deleted.is_(False))
        )).scalar_one_or_none()
        if t is None:
            return None
        return {
            "id":           None,
            "trackId":      str(t.id),
            "title":        t.title,
            "coverUrl":     t.cover_url or "",
            "priceCredits": None,
            "productType":  "track",
        }
    son = await _partner_prompt(db, image)
    if son is None or not _is_sound(son):
        return None
    from app.models.track import Track

    cover = (await db.execute(
        select(Track.cover_url).where(
            Track.prompt_id == son.id,
            Track.is_deleted.is_(False),
        ).limit(1)
    )).scalar_one_or_none()
    return {
        "id":           str(son.id),
        "title":        son.title,
        "coverUrl":     cover or "",
        "priceCredits": son.price_credits,
        "productType":  son.product_type,
    }


async def linked_image_payload(db: AsyncSession, sound: Prompt) -> dict | None:
    """
    Pour un SON lie, renvoie l'apercu PUBLIC de son IMAGE partenaire :
    {id, previewKey, priceCredits}. Aucun champ gate (image_r2_key /
    prompt_text / image_settings / negative_prompt) n'est expose. None si pas
    lie ou partenaire non image.
    """
    img = await _partner_prompt(db, sound)
    if img is None or not _is_image(img):
        return None
    return {
        "id":           str(img.id),
        "previewKey":   img.preview_r2_key or "",
        "priceCredits": img.price_credits,
    }


async def linked_image_payload_for_son_id(
    db: AsyncSession, son_prompt_id: _uuid.UUID | None
) -> dict | None:
    """
    Variante quand on n'a que l'id du prompt-son (cas tracks/profil ou on
    itere sur des Track, pas des Prompt). Charge le son puis son image liee.
    """
    if son_prompt_id is None:
        return None
    son = (await db.execute(
        select(Prompt).where(Prompt.id == son_prompt_id)
    )).scalar_one_or_none()
    if son is None:
        return None
    return await linked_image_payload(db, son)



# ──────────────────────────────────────────────────────────────────────────
# Lot 2 — liaison au niveau du MORCEAU (migration 0093)
#
# L'Œuvre = 1 son + 1 image. Le « son » est le MORCEAU publié (tracks), avec
# ou sans recette. L'image porte `linked_track_id`. Si le morceau a une
# recette sonore libre, la liaison historique recette <-> image est posée en
# plus : toutes les surfaces existantes (cartes, /oeuvres, profil) continuent
# de fonctionner sans changement.
# ──────────────────────────────────────────────────────────────────────────


async def _clear_track_link_of_recipe(db: AsyncSession, recipe_id: _uuid.UUID) -> None:
    """Détache l'image posée sur le(s) morceau(x) portant cette recette."""
    from app.models.track import Track

    track_ids = (await db.execute(
        select(Track.id).where(Track.prompt_id == recipe_id)
    )).scalars().all()
    if not track_ids:
        return
    imgs = (await db.execute(
        select(Prompt).where(Prompt.linked_track_id.in_(track_ids))
    )).scalars().all()
    for img in imgs:
        img.linked_track_id = None


async def _free_tracks_without_recipe(db: AsyncSession, owner_id: _uuid.UUID):
    """Morceaux de owner, non supprimés, SANS recette, sans image liée."""
    from app.models.track import Track

    taken = select(Prompt.linked_track_id).where(Prompt.linked_track_id.isnot(None))
    return (await db.execute(
        select(Track).where(
            Track.artist_id == owner_id,
            Track.is_deleted.is_(False),
            Track.prompt_id.is_(None),
            Track.id.not_in(taken),
        ).order_by(Track.created_at.desc())
    )).scalars().all()


async def _load_owned_track_or_404(db: AsyncSession, *, track_id, owner_id):
    from app.models.track import Track

    t = (await db.execute(
        select(Track).where(
            Track.id == track_id,
            Track.artist_id == owner_id,
            Track.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if t is None:
        raise LinkError(404, "Morceau introuvable.")
    return t


async def _image_of_track(db: AsyncSession, track) -> Prompt | None:
    """Image liée à ce morceau : par le morceau (0093) ou par sa recette (0059)."""
    img = (await db.execute(
        select(Prompt).where(
            Prompt.linked_track_id == track.id,
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if img is not None:
        return img
    if track.prompt_id is None:
        return None
    recipe = (await db.execute(
        select(Prompt).where(Prompt.id == track.prompt_id)
    )).scalar_one_or_none()
    if recipe is None or recipe.linked_prompt_id is None:
        return None
    img = (await db.execute(
        select(Prompt).where(
            Prompt.id == recipe.linked_prompt_id,
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    return img if img is not None and _is_image(img) else None


async def link_image_to_track(
    db: AsyncSession,
    *,
    owner_id: _uuid.UUID,
    track_id: _uuid.UUID,
    image_id: _uuid.UUID,
    bundle_exclusive: bool = False,
) -> Prompt:
    """Lie une IMAGE de owner à un MORCEAU de owner (1:1).

      - 404 si l'un des deux est absent / pas owner / supprimé ;
      - 409 si ce n'est pas une image, si l'image est déjà liée, ou si le
        morceau a déjà une image (directement ou via sa recette).
    Si le morceau a une recette sonore LIBRE, la liaison recette <-> image
    (0059) est posée aussi. Ne commit pas.
    """
    track = await _load_owned_track_or_404(db, track_id=track_id, owner_id=owner_id)
    img = await _load_owned_prompt_or_404(db, prompt_id=image_id, owner_id=owner_id)
    if not _is_image(img):
        raise LinkError(409, "Une Œuvre relie un son et une IMAGE.")
    if img.linked_prompt_id is not None or img.linked_track_id is not None:
        raise LinkError(409, "Cette image est déjà dans une autre Œuvre.")
    if await _image_of_track(db, track) is not None:
        raise LinkError(409, "Ce son a déjà une image.")

    img.linked_track_id = track.id
    img.bundle_exclusive = bundle_exclusive
    if track.prompt_id is not None:
        recipe = (await db.execute(
            select(Prompt).where(
                Prompt.id == track.prompt_id, Prompt.is_deleted.is_(False)
            )
        )).scalar_one_or_none()
        if recipe is not None and _is_sound(recipe) and recipe.linked_prompt_id is None:
            recipe.linked_prompt_id = img.id
            img.linked_prompt_id = recipe.id
            recipe.bundle_exclusive = bundle_exclusive
    await db.flush()
    return img


async def unlink_track(db: AsyncSession, *, owner_id: _uuid.UUID, track_id: _uuid.UUID) -> None:
    """Délie l'image de ce morceau (et la recette du morceau, le cas échéant).
    Idempotent. Ne commit pas."""
    track = await _load_owned_track_or_404(db, track_id=track_id, owner_id=owner_id)
    img = await _image_of_track(db, track)
    if img is None:
        return
    await unlink_products(db, owner_id=owner_id, prompt_id=img.id)
    img.linked_track_id = None
    img.bundle_exclusive = False
    await db.flush()


async def track_linkable_images(
    db: AsyncSession, *, owner_id: _uuid.UUID, track_id: _uuid.UUID
) -> list[dict]:
    """Images LIBRES de owner, liables à ce morceau (aperçu léger, anti-fuite)."""
    await _load_owned_track_or_404(db, track_id=track_id, owner_id=owner_id)
    rows = (await db.execute(
        select(Prompt).where(
            Prompt.artist_id == owner_id,
            Prompt.is_deleted.is_(False),
            Prompt.product_type == _IMAGE_TYPE,
            Prompt.linked_prompt_id.is_(None),
            Prompt.linked_track_id.is_(None),
        ).order_by(Prompt.created_at.desc())
    )).scalars().all()
    return [
        {
            "id":           str(p.id),
            "kind":         "image",
            "title":        p.title,
            "productType":  p.product_type,
            "priceCredits": p.price_credits,
            "previewKey":   p.preview_r2_key or "",
        }
        for p in rows
    ]


async def track_link_state(
    db: AsyncSession, *, owner_id: _uuid.UUID, track_id: _uuid.UUID
) -> dict:
    """État de liaison d'un morceau pour l'éditeur du créateur."""
    track = await _load_owned_track_or_404(db, track_id=track_id, owner_id=owner_id)
    img = await _image_of_track(db, track)
    if img is None:
        return {"linked": False, "oeuvreId": None, "image": None}
    return {
        "linked": True,
        "oeuvreId": str(img.id),
        "image": {"id": str(img.id), "title": img.title,
                  "previewKey": img.preview_r2_key or ""},
    }


async def track_images_for_cards(db: AsyncSession, track_ids: list) -> dict:
    """Pour des cartes de morceaux : {track_id: aperçu image} des images liées
    AU MORCEAU (0093). Aperçu public only ; image publiée, non supprimée.
    Une requête."""
    if not track_ids:
        return {}
    rows = (await db.execute(
        select(Prompt).where(
            Prompt.linked_track_id.in_(track_ids),
            Prompt.product_type == _IMAGE_TYPE,
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
        )
    )).scalars().all()
    return {
        p.linked_track_id: {
            "id":              str(p.id),
            "previewKey":      p.preview_r2_key or "",
            "priceCredits":    p.price_credits,
            "imagePlatform":   p.image_platform,
            "bundleExclusive": bool(p.bundle_exclusive),
        }
        for p in rows
    }


# ──────────────────────────────────────────────────────────────────────────
# Lot 2 — lecture PUBLIQUE d'une Œuvre (page /o/{id}). L'identifiant d'une
# Œuvre est celui de son IMAGE : toute Œuvre a exactement une image, qu'elle
# soit liée par le morceau (0093) ou par la recette (0059).
# ──────────────────────────────────────────────────────────────────────────


async def public_oeuvre(db: AsyncSession, image_id: _uuid.UUID) -> dict | None:
    """Œuvre publique (image + son + créateur), ou None.

    Filtres : image publiée, non supprimée, non retirée ; créateur au profil
    public et non suspendu ; son = morceau non supprimé (ou, pour une Œuvre
    historique sans morceau, recette publiée). N'expose JAMAIS de champ gaté
    (recette, paroles, original de l'image).
    """
    from app.models.track import Track
    from app.models.user import User

    img = (await db.execute(
        select(Prompt).where(
            Prompt.id == image_id,
            Prompt.product_type == _IMAGE_TYPE,
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            Prompt.taken_down_at.is_(None),
        )
    )).scalar_one_or_none()
    if img is None:
        return None
    artist = (await db.execute(select(User).where(User.id == img.artist_id))).scalar_one_or_none()
    if artist is None or not artist.profile_public or artist.is_banned:
        return None

    track = None
    recipe = None
    if img.linked_track_id is not None:
        track = (await db.execute(
            select(Track).where(Track.id == img.linked_track_id, Track.is_deleted.is_(False))
        )).scalar_one_or_none()
    if img.linked_prompt_id is not None:
        recipe = (await db.execute(
            select(Prompt).where(
                Prompt.id == img.linked_prompt_id,
                Prompt.is_published.is_(True),
                Prompt.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
        if recipe is not None and not _is_sound(recipe):
            recipe = None
        if track is None and recipe is not None:
            track = (await db.execute(
                select(Track).where(Track.prompt_id == recipe.id, Track.is_deleted.is_(False))
                .order_by(Track.created_at.asc()).limit(1)
            )).scalar_one_or_none()
    if track is not None and recipe is None and track.prompt_id is not None:
        recipe = (await db.execute(
            select(Prompt).where(
                Prompt.id == track.prompt_id,
                Prompt.is_published.is_(True),
                Prompt.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
    if track is None and recipe is None:
        return None

    from app.routers.watt_compat import _build_stream_url, _derive_artist_slug

    title = (track.title if track is not None else recipe.title) or img.title
    return {
        "id": str(img.id),
        "title": title,
        "creator": {
            "id": str(artist.id),
            "name": artist.artist_name or "",
            "slug": _derive_artist_slug(artist),
            "avatarUrl": artist.avatar_url or "",
        },
        "image": {
            "id": str(img.id),
            "title": img.title,
            "previewKey": img.preview_r2_key or "",
            "priceCredits": img.price_credits,
            "platform": img.image_platform,
        },
        "sound": {
            "trackId": str(track.id) if track is not None else None,
            "title": title,
            "streamUrl": _build_stream_url(track) if track is not None else "",
            "coverUrl": (track.cover_url or "") if track is not None else "",
            # La moitié SON n'est achetable que si le morceau a une recette.
            "recipe": (
                {"id": str(recipe.id), "priceCredits": recipe.price_credits,
                 "productType": recipe.product_type}
                if recipe is not None else None
            ),
        },
        # Achat de l'Œuvre entière : décision d'argent en attente (prix).
        # Le front réserve l'emplacement ; rien n'est vendable ici.
        "bundle": None,
    }
