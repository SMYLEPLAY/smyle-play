"""Modération DSA — actions concrètes sur un contenu ou un compte signalé.

Phase 3 lancement (2026-07-24). Le signalement DSA (0081) ne faisait que
RECEVOIR. Ici on AGIT, réservé au compte officiel (contrôle is_official fait
au niveau des endpoints) :

- `takedown_content` : retire un contenu de la vue publique en réutilisant le
  drapeau « caché » propre à chaque type (is_published / is_deleted / visibility).
  Lot 2 (anti-squat Pionnier) : les œuvres (prompts, images, morceaux, ADN,
  ADN visuels, voix) reçoivent en plus la marque `taken_down_at` — un trigger
  en base (migration 0092) les garde cachées même si le créateur tente de les
  republier, et elles ne qualifient plus personne au programme Pionnier
  (cf. publications.SQL_OEUVRES_EN_LIGNE).
  On NE supprime jamais la ligne → la preuve est conservée (exigence DSA) et un
  éventuel acheteur garde son accès en bibliothèque.
- `ban_user` / `unban_user` : suspend / rétablit un compte (login + tout accès
  authentifié bloqués via get_current_user).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.album import Album
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.models.visual_adn import VisualAdn
from app.models.voice import Voice

# Types d'œuvres « publiables » : retrait = is_published false + marque
# taken_down_at (le trigger 0092 empêche toute republication).
_PUBLISHABLE = {
    "prompt": (Prompt, "Contenu retiré de la vitrine."),
    "image": (Prompt, "Contenu retiré de la vitrine."),
    "adn": (Adn, "ADN retiré de la vitrine."),
    "visual_adn": (VisualAdn, "ADN visuel retiré de la vitrine."),
    "voix": (Voice, "Voix retirée de la vitrine."),
}


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def ban_user(
    db: AsyncSession, user_id: uuid.UUID, reason: str | None = None
) -> User | None:
    """Suspend un compte. Retourne le User modifié, ou None s'il n'existe pas."""
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        return None
    user.is_banned = True
    user.banned_at = datetime.now(timezone.utc)
    user.ban_reason = (reason or "").strip()[:500] or None
    return user


async def unban_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Rétablit un compte suspendu."""
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        return None
    user.is_banned = False
    user.banned_at = None
    user.ban_reason = None
    return user


async def takedown_content(
    db: AsyncSession,
    target_type: str,
    target_id: str,
    reason: str | None = None,
    *,
    admin_id: uuid.UUID | None = None,
) -> dict:
    """
    Retire de la vue publique le contenu signalé, selon son type.
    Retourne {"ok": bool, "detail": str}. Ne commit PAS (l'appelant commit).
    Étape 2 : chaque retrait d'œuvre est journalisé (`admin_journal`, action
    « retrait ») avec son motif et l'état d'avant — c'est ce que l'écran
    « Contenus retirés » affiche, et ce que la restauration remet.
    """
    ttype = (target_type or "").strip().lower()
    tid = _as_uuid(target_id)
    if tid is None and ttype != "profil":
        return {"ok": False, "detail": "Identifiant de cible invalide."}

    if ttype in _PUBLISHABLE:
        model, done = _PUBLISHABLE[ttype]
        obj = (await db.execute(
            select(model).where(model.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Contenu introuvable."}
        etait_publie = bool(obj.is_published)
        obj.is_published = False
        if obj.taken_down_at is None:
            obj.taken_down_at = datetime.now(timezone.utc)
            await journaliser(db, admin_id=admin_id, action="retrait", cible_type=ttype,
                              cible_id=str(tid), motif=reason,
                              details={"etait_publie": etait_publie})
        return {"ok": True, "detail": done}

    if ttype == "track":
        obj = (await db.execute(
            select(Track).where(Track.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Morceau introuvable."}
        etait_supprime = bool(obj.is_deleted)
        obj.is_deleted = True
        if obj.taken_down_at is None:
            obj.taken_down_at = datetime.now(timezone.utc)
            await journaliser(db, admin_id=admin_id, action="retrait", cible_type="track",
                              cible_id=str(tid), motif=reason,
                              details={"etait_supprime": etait_supprime})
        return {"ok": True, "detail": "Morceau retiré."}

    if ttype == "playlist":
        obj = (await db.execute(
            select(Playlist).where(Playlist.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Playlist introuvable."}
        obj.visibility = "private"
        return {"ok": True, "detail": "Playlist passée en privé."}

    if ttype == "album":
        obj = (await db.execute(
            select(Album).where(Album.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Album introuvable."}
        obj.visibility = "private"
        return {"ok": True, "detail": "Album passé en privé."}

    if ttype == "profil":
        # Signalement d'un profil → on suspend le compte visé.
        pid = tid or _as_uuid(target_id)
        if pid is None:
            return {"ok": False, "detail": "Identifiant de profil invalide."}
        user = await ban_user(db, pid, reason)
        if user is None:
            return {"ok": False, "detail": "Compte introuvable."}
        return {"ok": True, "detail": "Compte suspendu."}

    return {"ok": False, "detail": f"Type de cible non géré : {ttype}."}


# ─────────────────────────────────────────────────────────────────────────────
# Étape 2 — journal d'administration + restauration d'un contenu retiré
# ─────────────────────────────────────────────────────────────────────────────

async def journaliser(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID | None,
    action: str,
    cible_type: str,
    cible_id: str,
    motif: str | None = None,
    details: dict | None = None,
) -> None:
    """Ajoute une ligne au journal d'administration (dans la transaction de
    l'appelant : l'action et sa trace sont validées ensemble)."""
    import json

    await db.execute(
        text(
            "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
            "VALUES (gen_random_uuid(), :a, :act, :t, :c, :m, CAST(:d AS jsonb))"
        ),
        {"a": admin_id, "act": action, "t": cible_type, "c": cible_id,
         "m": (motif or "").strip()[:500] or None,
         "d": json.dumps(details) if details is not None else None},
    )


# (table SQL, colonne titre, libellé) par type d'œuvre retirable.
_RETIRABLES = {
    "prompt": ("prompts", "title", "Recette"),
    "image": ("prompts", "title", "Image"),
    "adn": ("adns", None, "ADN musical"),
    "visual_adn": ("visual_adns", None, "ADN visuel"),
    "voix": ("voices_for_sale", "name", "Voix"),
    "track": ("tracks", "title", "Morceau"),
}


async def contenus_retires(db: AsyncSession, limit: int = 200) -> list[dict]:
    """Contenus actuellement retirés par la modération, du plus récent au plus
    ancien : type, titre, auteur, motif (journal, sinon signalement), date."""
    union = []
    for ttype, table in (("prompt", "prompts"), ("adn", "adns"), ("visual_adn", "visual_adns"),
                         ("voix", "voices_for_sale"), ("track", "tracks")):
        titre = {"prompts": "t.title", "voices_for_sale": "t.name", "tracks": "t.title"}.get(table, "NULL")
        kind = "CASE WHEN t.product_type = 'image' THEN 'image' ELSE 'prompt' END" if table == "prompts" else f"'{ttype}'"
        union.append(
            f"SELECT {kind} AS type, t.id::text AS id, {titre} AS titre, t.artist_id, "
            f"t.taken_down_at FROM {table} t WHERE t.taken_down_at IS NOT NULL"
        )
    rows = (await db.execute(text(
        "WITH r AS (" + " UNION ALL ".join(union) + ") "
        "SELECT r.*, u.artist_name, "
        " (SELECT j.motif FROM admin_journal j WHERE j.action = 'retrait' AND j.cible_id = r.id "
        "  ORDER BY j.created_at DESC LIMIT 1) AS motif_journal, "
        " (SELECT COALESCE(NULLIF(c.detail, ''), c.reason::text) FROM content_reports c "
        "  WHERE c.target_id = r.id AND c.status = 'actioned' "
        "  ORDER BY c.resolved_at DESC NULLS LAST LIMIT 1) AS motif_signalement "
        "FROM r LEFT JOIN users u ON u.id = r.artist_id "
        "ORDER BY r.taken_down_at DESC LIMIT :l"
    ), {"l": max(1, min(limit, 500))})).all()
    out = []
    for r in rows:
        libelle = _RETIRABLES.get(r.type, (None, None, r.type))[2]
        out.append({
            "type": r.type,
            "type_libelle": libelle,
            "id": r.id,
            "titre": r.titre or libelle,
            "auteur": r.artist_name or "(sans pseudo)",
            "auteur_id": str(r.artist_id) if r.artist_id else None,
            "motif": r.motif_journal or r.motif_signalement or "Motif non enregistré",
            "retire_le": r.taken_down_at.isoformat() if r.taken_down_at else None,
        })
    return out


class RestaurationImpossible(Exception):
    pass


async def restaurer_contenu(
    db: AsyncSession, *, admin_id: uuid.UUID, cible_type: str, cible_id: str, motif: str
) -> dict:
    """Restaure un contenu retiré — SEUL chemin autorisé à lever la marque.

    Sûreté (migration 0098) : le trigger refuse d'effacer `taken_down_at`
    sauf si la transaction pose `watt.restauration = on` (SET LOCAL : limité à
    cette transaction). On le pose, on restaure, on le retire aussitôt, et on
    journalise dans la même transaction. L'état remis est celui d'avant le
    retrait (journal) ; à défaut (retrait antérieur au journal), le contenu
    revient EN LIGNE, puisqu'il était visible quand il a été signalé.
    Ne commit pas."""
    motif = (motif or "").strip()
    if len(motif) < 3:
        raise RestaurationImpossible("Motif obligatoire (3 caractères minimum).")
    ttype = (cible_type or "").strip().lower()
    if ttype not in _RETIRABLES:
        raise RestaurationImpossible("Type de contenu inconnu.")
    tid = _as_uuid(cible_id)
    if tid is None:
        raise RestaurationImpossible("Identifiant invalide.")
    table = _RETIRABLES[ttype][0]
    row = (await db.execute(
        text(f"SELECT taken_down_at, artist_id FROM {table} WHERE id = :i FOR UPDATE"),  # noqa: S608
        {"i": tid},
    )).first()
    if row is None:
        raise RestaurationImpossible("Contenu introuvable.")
    if row.taken_down_at is None:
        raise RestaurationImpossible("Ce contenu n'est pas retiré.")
    avant = (await db.execute(text(
        "SELECT details FROM admin_journal WHERE action = 'retrait' AND cible_id = :c "
        "ORDER BY created_at DESC LIMIT 1"), {"c": str(tid)})).scalar_one_or_none() or {}

    await db.execute(text("SELECT set_config('watt.restauration', 'on', true)"))
    if table == "tracks":
        await db.execute(
            text("UPDATE tracks SET taken_down_at = NULL, is_deleted = :d WHERE id = :i"),
            {"d": bool(avant.get("etait_supprime", False)), "i": tid},
        )
    else:
        await db.execute(
            text(f"UPDATE {table} SET taken_down_at = NULL, is_published = :p WHERE id = :i"),  # noqa: S608
            {"p": bool(avant.get("etait_publie", True)), "i": tid},
        )
    await db.execute(text("SELECT set_config('watt.restauration', 'off', true)"))
    await journaliser(db, admin_id=admin_id, action="restauration", cible_type=ttype,
                      cible_id=str(tid), motif=motif, details={"etat_remis": avant or "en_ligne"})
    # Informer l'auteur (best-effort).
    try:
        from app.models.notification import NotificationType
        from app.services.notifications import create_notification

        await create_notification(
            db, user_id=row.artist_id, type=NotificationType.SYSTEM,
            metadata={"text": f"Un de tes contenus retirés a été restauré par la modération. Motif : {motif}."},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "detail": "Contenu restauré."}
