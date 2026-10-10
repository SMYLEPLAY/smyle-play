"""Écran « Mes Œuvres » (Parcours V1, décision Tom du 9/10/2026).

Une ligne par SON publié du créateur (morceau non supprimé), avec ce qui s'y
rattache : l'image de l'Œuvre (si elle existe), la recette vendue, les prix,
le statut (publiée / masquée) et le nombre de ventes.

Actions (toutes limitées aux Œuvres du compte connecté) :
  - masquer      : le son disparaît des listes publiques, la recette et
                   l'image passent en non publiées ;
  - republier    : l'inverse (soumis au seuil d'abonnés pour vendre) ;
  - prix         : entre 10 et 150 Smyles, sur la recette, l'image ou les deux ;
  - supprimer    : suppression DOUCE (rien n'est effacé en base ni sur le
                   stockage) — le son, sa recette et son image disparaissent ;
  - modifier     : titre, description, pochette, prix.

RÈGLE DE PROTECTION DES ACHETEURS : aucune de ces actions ne touche aux
exemplaires déjà achetés (`unlocked_prompts`) — la bibliothèque, la recette
et le téléchargement de l'image restent accessibles à ceux qui ont payé.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.marketplace import (
    PROMPT_DESCRIPTION_MAX,
    PROMPT_PRICE_MAX,
    PROMPT_PRICE_MIN,
    PROMPT_TITLE_MAX,
    PROMPT_TITLE_MIN,
)

ACTIONS = ("masquer", "republier", "prix", "supprimer")
CIBLES_PRIX = ("les_deux", "recette", "image")
MAX_PAR_LOT = 200


class OeuvreErreur(ValueError):
    """Erreur métier lisible (→ 400/422 côté routeur)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prix_valide(prix) -> int:
    try:
        p = int(prix)
    except (TypeError, ValueError):
        raise OeuvreErreur(f"Le prix doit être entre {PROMPT_PRICE_MIN} et {PROMPT_PRICE_MAX} Smyles.")
    if not (PROMPT_PRICE_MIN <= p <= PROMPT_PRICE_MAX):
        raise OeuvreErreur(f"Le prix doit être entre {PROMPT_PRICE_MIN} et {PROMPT_PRICE_MAX} Smyles.")
    return p


async def _mes_sons(db: AsyncSession, user_id: UUID, track_ids=None) -> list[Track]:
    q = select(Track).where(Track.artist_id == user_id, Track.is_deleted.is_(False))
    if track_ids is not None:
        q = q.where(Track.id.in_(list(track_ids)))
    return list((await db.execute(q.order_by(Track.created_at.desc()))).scalars().all())


async def _rattachements(db: AsyncSession, user_id: UUID, tracks: list[Track]) -> dict:
    """{track_id: (recette | None, image | None)} — seulement des produits du
    même créateur, non supprimés. Quatre requêtes au plus, quel que soit le
    nombre d'Œuvres."""
    if not tracks:
        return {}
    ids = [t.id for t in tracks]
    recette_ids = [t.prompt_id for t in tracks if t.prompt_id is not None]
    recettes = {}
    if recette_ids:
        recettes = {p.id: p for p in (await db.execute(
            select(Prompt).where(
                Prompt.id.in_(recette_ids),
                Prompt.artist_id == user_id,
                Prompt.is_deleted.is_(False),
            )
        )).scalars().all()}
    images_par_son = {p.linked_track_id: p for p in (await db.execute(
        select(Prompt).where(
            Prompt.linked_track_id.in_(ids),
            Prompt.artist_id == user_id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
        )
    )).scalars().all()}
    # Œuvres historiques : image liée à la RECETTE (0059), pas au morceau.
    via_recette = [r.linked_prompt_id for r in recettes.values() if r.linked_prompt_id]
    images_par_id = {}
    if via_recette:
        images_par_id = {p.id: p for p in (await db.execute(
            select(Prompt).where(
                Prompt.id.in_(via_recette),
                Prompt.artist_id == user_id,
                Prompt.product_type == "image",
                Prompt.is_deleted.is_(False),
            )
        )).scalars().all()}
    out = {}
    for t in tracks:
        r = recettes.get(t.prompt_id) if t.prompt_id else None
        if r is not None and r.product_type not in ("recipe", "beat"):
            r = None
        img = images_par_son.get(t.id)
        if img is None and r is not None and r.linked_prompt_id:
            img = images_par_id.get(r.linked_prompt_id)
        out[t.id] = (r, img)
    return out


async def lister(db: AsyncSession, user: User) -> list[dict]:
    from app.routers.watt_compat import _build_stream_url
    from app.services.oeuvre_c4_purchase import oeuvre_bundle_price

    tracks = await _mes_sons(db, user.id)
    liens = await _rattachements(db, user.id, tracks)
    produits = [p.id for r, i in liens.values() for p in (r, i) if p is not None]
    ventes = {}
    if produits:
        ventes = dict((await db.execute(
            select(UnlockedPrompt.prompt_id, func.count(UnlockedPrompt.id))
            .where(UnlockedPrompt.prompt_id.in_(produits))
            .group_by(UnlockedPrompt.prompt_id)
        )).all())
    out = []
    for t in tracks:
        r, img = liens[t.id]
        masquee = t.hidden_at is not None
        retiree = t.taken_down_at is not None
        prix_oeuvre = None
        if r is not None and img is not None:
            prix_oeuvre = oeuvre_bundle_price(r.price_credits, img.price_credits)[0]
        out.append({
            "trackId": str(t.id),
            "title": t.title,
            "streamUrl": _build_stream_url(t),
            "coverUrl": t.cover_url or "",
            "image": (
                {"id": str(img.id), "title": img.title,
                 "previewKey": img.preview_r2_key or "",
                 "priceCredits": img.price_credits,
                 "published": bool(img.is_published)}
                if img is not None else None
            ),
            "recipe": (
                {"id": str(r.id), "title": r.title,
                 "description": r.description or "",
                 "priceCredits": r.price_credits,
                 "published": bool(r.is_published)}
                if r is not None else None
            ),
            "oeuvrePrice": prix_oeuvre,
            "status": "retiree" if retiree else ("masquee" if masquee else "publiee"),
            "sales": int(sum(ventes.get(p.id, 0) for p in (r, img) if p is not None)),
            "oeuvreUrl": f"/o/{img.id}" if img is not None else None,
            "createdAt": t.created_at.isoformat() if t.created_at else None,
        })
    return out


def _publier(produit: Prompt | None, valeur: bool) -> None:
    if produit is None or produit.taken_down_at is not None:
        return
    produit.is_published = valeur


async def _supprimer(db: AsyncSession, track: Track, recette, image) -> None:
    """Suppression douce de l'Œuvre entière. Les exemplaires achetés restent."""
    from app.services.links import detach_partner_on_removal
    from app.services.tracks import soft_delete_track, visible_track_clause

    if image is not None:
        await detach_partner_on_removal(db, prompt=image)
        image.is_deleted = True
        image.is_published = False
    await soft_delete_track(db, track)
    if recette is not None:
        # La recette n'est supprimée que si aucun autre son visible du
        # créateur ne la porte (sinon elle reste, dépubliée par
        # soft_delete_track seulement si elle n'est plus portée).
        autre = (await db.execute(
            select(Track.id).where(
                Track.prompt_id == recette.id,
                Track.id != track.id,
                Track.artist_id == track.artist_id,
                visible_track_clause(),
            ).limit(1)
        )).scalar_one_or_none()
        if autre is None:
            await detach_partner_on_removal(db, prompt=recette)
            recette.is_deleted = True
            recette.is_published = False


async def action_groupee(
    db: AsyncSession, user: User, *, track_ids: list[UUID], action: str,
    prix: int | None = None, cible: str = "les_deux",
) -> dict:
    """Applique `action` aux Œuvres demandées qui appartiennent au compte.
    Les identifiants inconnus ou d'un autre compte sont ignorés (comptés dans
    `introuvables`, sans dire pourquoi). Le caller commit."""
    if action not in ACTIONS:
        raise OeuvreErreur("Action inconnue.")
    ids = list(dict.fromkeys(track_ids))
    if not ids:
        raise OeuvreErreur("Sélectionne au moins une Œuvre.")
    if len(ids) > MAX_PAR_LOT:
        raise OeuvreErreur(f"{MAX_PAR_LOT} Œuvres au plus par action.")
    if action == "prix":
        prix = _prix_valide(prix)
        if cible not in CIBLES_PRIX:
            raise OeuvreErreur("Cible de prix inconnue.")
    tracks = await _mes_sons(db, user.id, ids)
    liens = await _rattachements(db, user.id, tracks)

    if action == "republier":
        # Republier = remettre en vente : même seuil que toute mise en vente.
        if any(r is not None or i is not None for r, i in liens.values()):
            from app.services.droit_de_vendre import exiger_droit_de_vendre

            await exiger_droit_de_vendre(db, user)

    faits, ignores = [], []
    for t in tracks:
        r, img = liens[t.id]
        if t.taken_down_at is not None and action in ("masquer", "republier"):
            ignores.append(str(t.id))  # retirée par la modération : intouchable ici
            continue
        if action == "masquer":
            t.hidden_at = t.hidden_at or _now()
            _publier(r, False)
            _publier(img, False)
        elif action == "republier":
            t.hidden_at = None
            _publier(r, True)
            _publier(img, True)
        elif action == "prix":
            touche = False
            if r is not None and cible in ("les_deux", "recette"):
                r.price_credits = prix
                touche = True
            if img is not None and cible in ("les_deux", "image"):
                img.price_credits = prix
                touche = True
            if not touche:
                ignores.append(str(t.id))  # rien à vendre sur cette cible
                continue
        elif action == "supprimer":
            await _supprimer(db, t, r, img)
        faits.append(str(t.id))
    await db.flush()
    return {
        "action": action,
        "faits": faits,
        "ignores": ignores,
        "introuvables": len(ids) - len(tracks),
    }


async def modifier(db: AsyncSession, user: User, track_id: UUID, data: dict) -> dict:
    """Modification unitaire : titre, description, pochette, prix. Le caller commit."""
    from app.schemas.track import validate_media_url
    from app.services.media_ownership import (
        MediaOwnershipError,
        media_url_owned_or_external,
    )

    tracks = await _mes_sons(db, user.id, [track_id])
    if not tracks:
        raise LookupError("Œuvre introuvable.")
    t = tracks[0]
    r, img = (await _rattachements(db, user.id, tracks))[t.id]

    if "title" in data and data["title"] is not None:
        titre = " ".join(str(data["title"]).split())
        if not (PROMPT_TITLE_MIN <= len(titre) <= PROMPT_TITLE_MAX):
            raise OeuvreErreur(
                f"Le titre doit faire entre {PROMPT_TITLE_MIN} et {PROMPT_TITLE_MAX} caractères."
            )
        t.title = titre
        for p in (r, img):
            if p is not None:
                p.title = titre
    if "description" in data and data["description"] is not None:
        desc = str(data["description"]).strip()
        if len(desc) > PROMPT_DESCRIPTION_MAX:
            raise OeuvreErreur(f"Description trop longue ({PROMPT_DESCRIPTION_MAX} caractères au plus).")
        for p in (r, img):
            if p is not None:
                p.description = desc or None
    if "cover_url" in data:
        url = validate_media_url(data["cover_url"]) if data["cover_url"] else None
        if url and not media_url_owned_or_external(url, user.id):
            raise MediaOwnershipError("Image non reconnue pour ce compte.")
        t.cover_url = url
    if data.get("recipe_price") is not None:
        if r is None:
            raise OeuvreErreur("Cette Œuvre n'a pas de recette en vente.")
        r.price_credits = _prix_valide(data["recipe_price"])
    if data.get("image_price") is not None:
        if img is None:
            raise OeuvreErreur("Cette Œuvre n'a pas d'image en vente.")
        img.price_credits = _prix_valide(data["image_price"])
    await db.flush()
    return {"trackId": str(t.id), "title": t.title}
