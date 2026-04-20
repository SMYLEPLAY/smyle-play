"""
Phase 9.3 — Schémas Pydantic des endpoints unlock.

Réponses enrichies pour permettre à l'UI d'afficher proprement :
  - le détail "tu as économisé X grâce à ton perk -30%"
  - la transaction complète (audit + historique)
  - l'objet possédé (UnlockedPrompt ou OwnedAdn)

Aucun payload d'entrée : l'unlock est un POST sans body, l'identifiant
de la cible vient de l'URL (`/unlocks/prompts/{prompt_id}`) et le buyer
vient du JWT.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.credit import TransactionRead


# -----------------------------------------------------------------------------
# Read shapes des objets possédés
# -----------------------------------------------------------------------------

class UnlockedPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    current_owner_id: UUID
    prompt_id: UUID
    original_artist_id: UUID | None = None
    unlocked_at: datetime


class OwnedAdnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    adn_id: UUID
    owned_at: datetime


# -----------------------------------------------------------------------------
# Réponses unlock (objet possédé + transaction + détail prix)
# -----------------------------------------------------------------------------

class UnlockPromptResponse(BaseModel):
    """
    Réponse à POST /unlocks/prompts/{prompt_id}.

    `base_price` = prix affiché dans le catalogue (avant perk)
    `paid`       = prix effectif débité (après perk éventuel)
    `perk_applied` = True ssi acheteur possède l'ADN de l'artiste du prompt
    """

    unlocked_prompt: UnlockedPromptRead
    transaction: TransactionRead
    perk_applied: bool
    base_price: int
    paid: int


class UnlockAdnResponse(BaseModel):
    """
    Réponse à POST /unlocks/adns/{adn_id}.
    Pas de perk sur l'ADN (le perk s'applique aux prompts pour les
    détenteurs d'ADN, pas dans l'autre sens).
    """

    owned_adn: OwnedAdnRead
    transaction: TransactionRead
    paid: int
