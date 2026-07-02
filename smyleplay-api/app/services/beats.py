"""
Service Beats (Phase 2 Marketplace VF, 2026-06-09).

Un beat est une ligne `prompts` avec product_type='beat'. Pas de pré-requis
ADN (contrairement aux recettes). La possession / l'achat / la revente
réutilisent la machinerie des prompts (UnlockedPrompt, unlock_prompt_atomic).
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt


async def create_beat(
    db: AsyncSession,
    *,
    artist_id: UUID,
    title: str,
    description: str | None,
    price_credits: int,
    license_type: str,
    max_supply: int | None = None,
    is_published: bool = False,
) -> Prompt:
    """
    Crée un beat vendable (product_type='beat').

    - Pas de prompt_text (un beat n'est pas une recette) → la contrainte de
      longueur ne s'applique pas (cf. ck_prompts_prompt_text_length).
    - EXCLUSIVE : on force max_supply=1 (vente unique) pour que le stock-out
      atomique existant garantisse qu'un seul acheteur l'obtienne, sous le
      verrou artiste. Le retrait de la vente (is_published=False) est fait à
      l'achat dans unlock_prompt_atomic.
    """
    effective_supply = 1 if license_type == "exclusive" else max_supply

    beat = Prompt(
        artist_id=artist_id,
        title=title,
        description=description,
        prompt_text=None,
        price_credits=price_credits,
        is_published=is_published,
        max_supply=effective_supply,
        product_type="beat",
        license_type=license_type,
    )
    db.add(beat)
    await db.flush()
    return beat
