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

    a.linked_prompt_id = b.id
    b.linked_prompt_id = a.id
    # Nature du lien posee symetriquement sur les deux cotes.
    a.bundle_exclusive = bundle_exclusive
    b.bundle_exclusive = bundle_exclusive
    await db.flush()
    return a, b


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
    # Le produit delie redevient un produit individuel ordinaire : il ne peut
    # plus etre « ne ensemble » (plus de partenaire). On le remet visible.
    p.bundle_exclusive = False
    if partner_id is not None:
        partner = (await db.execute(
            select(Prompt).where(Prompt.id == partner_id)
        )).scalar_one_or_none()
        if partner is not None and partner.linked_prompt_id == p.id:
            partner.linked_prompt_id = None
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
    partner_id = prompt.linked_prompt_id
    if partner_id is None:
        return
    prompt.linked_prompt_id = None
    prompt.bundle_exclusive = False
    partner = (await db.execute(
        select(Prompt).where(Prompt.id == partner_id)
    )).scalar_one_or_none()
    if partner is not None and partner.linked_prompt_id == prompt.id:
        partner.linked_prompt_id = None
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
