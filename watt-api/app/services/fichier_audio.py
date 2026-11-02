"""Le fichier audio est-il inclus dans un achat ? — décision Tom du 02/11/2026.

Règle (OBSIDIAN 01_PRODUIT/2026-11-02_DECISION-studios-adn-et-fichiers) :
  - acheter un SON donne la RECETTE (et l'écoute sur WATT), pas le fichier ;
  - acheter un BEAT donne le FICHIER (+ la recette), sous licence beat ;
  - un exemplaire acheté AVANT la bascule garde son fichier (droits acquis,
    colonne unlocked_prompts.fichier_inclus posée par la migration 0111) ;
  - le créateur garde toujours accès à son propre fichier.

Un produit est un beat si c'est un produit beat historique
(product_type = 'beat') ou si un morceau DU MÊME CRÉATEUR, lié à ce produit,
est publié comme beat (tracks.is_beat, ou lien beat_id historique).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import event, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt

MESSAGE_RECETTE_SEULE = (
    "Cet achat comprend la recette, pas le fichier audio. "
    "Le fichier est vendu avec les beats."
)


def clause_produit_beat():
    """Expression SQL corrélée à Prompt : True si le produit est un beat."""
    morceau_beat = exists(
        select(Track.id).where(
            or_(Track.prompt_id == Prompt.id, Track.beat_id == Prompt.id),
            Track.artist_id == Prompt.artist_id,
            or_(Track.is_beat.is_(True), Track.beat_id.is_not(None)),
            Track.taken_down_at.is_(None),
        )
    ).correlate(Prompt)
    return or_(Prompt.product_type == "beat", morceau_beat)


async def produit_est_beat(db: AsyncSession, prompt_id: UUID) -> bool:
    return bool((await db.execute(
        select(clause_produit_beat()).select_from(Prompt).where(Prompt.id == prompt_id)
    )).scalar())


def fichier_autorise(*, est_beat: bool, fichier_inclus: bool, est_createur: bool) -> bool:
    """Le détenteur peut-il télécharger le fichier audio ?"""
    return bool(est_createur or est_beat or fichier_inclus)


# ── Le droit au fichier est FIGÉ à l'achat ──────────────────────────────────
# Un exemplaire acheté comme BEAT garde son fichier même si le créateur
# repasse ensuite son morceau en « son ». Un seul point d'accroche pour tous
# les chemins d'achat (déblocage direct, pack, Œuvre, échange) : l'insertion
# d'une ligne UnlockedPrompt. La revente transfère la ligne → le droit suit.
@event.listens_for(UnlockedPrompt, "before_insert")
def _figer_fichier_a_l_achat(_mapper, connection, target) -> None:
    if target.fichier_inclus or target.prompt_id is None:
        return
    est_beat = connection.execute(
        select(clause_produit_beat()).select_from(Prompt).where(Prompt.id == target.prompt_id)
    ).scalar()
    if est_beat:
        target.fichier_inclus = True
