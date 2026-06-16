import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Prompt(Base):
    """
    Prompt vendu par un artiste sur la marketplace.

    - N par artiste, autant qu'il en publie
    - Transférable en Phase 10 (P2P) — cf. UnlockedPrompt qui a son propre
      UUID pour être tradeable plus tard
    - Plancher prix : 3 crédits
    - pack_eligible : prêt pour Phase 10 (packs aléatoires), default True
    - Validations au niveau DB (title 5+, prompt_text 100..1000).
      prompt_text est plafonné à 1000 car Suno n'accepte pas plus — vendre
      un prompt plus long reviendrait à vendre du contenu inutilisable.
    """

    __tablename__ = "prompts"
    __table_args__ = (
        CheckConstraint(
            "price_credits >= 3",
            name="ck_prompts_price_credits_min",
        ),
        CheckConstraint(
            "char_length(title) >= 5",
            name="ck_prompts_title_min_length",
        ),
        # Beats (0052) + Images (0057) : la borne 100..1000 de prompt_text n'est
        # exigée que pour les recettes (compat Suno) ; un beat n'a pas de prompt
        # (NULL) ; une image exige un prompt NOT NULL mais SANS borne (un prompt
        # d'image peut faire 3 mots comme 500).
        CheckConstraint(
            "(product_type = 'recipe' AND char_length(prompt_text) BETWEEN 100 AND 1000) "
            "OR (product_type = 'beat' AND prompt_text IS NULL) "
            "OR (product_type = 'image' AND prompt_text IS NOT NULL)",
            name="ck_prompts_prompt_text_length",
        ),
        CheckConstraint(
            "product_type IN ('recipe', 'beat', 'image')",
            name="ck_prompts_product_type",
        ),
        # C4 (0057) — provenance obligatoire UNIQUEMENT pour les images
        # (plateforme + version de modèle). recipe/beat non concernés.
        CheckConstraint(
            "product_type <> 'image' "
            "OR (image_platform IS NOT NULL AND image_model_version IS NOT NULL)",
            name="ck_prompts_image_provenance",
        ),
        CheckConstraint(
            "license_type IS NULL OR license_type IN ('lease', 'exclusive')",
            name="ck_prompts_license_type",
        ),
        # P1-F4 (2026-05-04) — enums réglages génération.
        # Conditionnelles (IS NULL OR IN ...) pour rétro-compat des
        # prompts existants en DB qui n'ont pas ces champs.
        CheckConstraint(
            "prompt_platform IS NULL OR prompt_platform IN "
            "('suno', 'udio', 'riffusion', 'stable_audio', 'autre')",
            name="ck_prompts_platform_enum",
        ),
        CheckConstraint(
            "prompt_vocal_gender IS NULL OR prompt_vocal_gender IN "
            "('masculin', 'feminin', 'instrumental', 'neutre', 'mixte')",
            name="ck_prompts_vocal_gender_enum",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULLable depuis 0052 (Beats) : un beat n'a pas de prompt. La contrainte
    # de longueur ne s'applique qu'aux recettes (cf. ck_prompts_prompt_text_length).
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Type de produit vendable : 'recipe' (recette IA, l'existant) | 'beat'
    # | 'image' (image IA, C4 — fichier original+aperçu portés ci-dessous).
    product_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="recipe", server_default="recipe"
    )
    # Licence du beat : 'lease' (non-exclusif) | 'exclusive'. NULL pour recettes.
    license_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Paroles complètes (gated behind unlock — ne JAMAIS retourner sans paiement)
    # Nullable car la majorité des morceaux sont instrumentaux ; rempli pour HIT MIX.
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    # Soft-delete (migration 0028) : TRUE = artiste a retiré ce prompt.
    # Disparaît du marketplace et du dashboard artiste.
    # Les acheteurs (UnlockedPrompt) gardent leur accès en library.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    pack_eligible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    # 2026-06-08 — Rareté/supply (copie du modèle ADN) : NULL = illimité,
    # 1 = pièce unique (mythic), N = édition limitée. Tier dérivé via
    # compute_rarity_tier(max_supply). Stock-out enforcé à l'achat
    # (sold_count = nb d'UnlockedPrompt vs max_supply). Prix libre (min 3) —
    # la rareté est un signal de valeur, pas un prix imposé.
    max_supply: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ── P1-F4 (2026-05-04) — Réglages de génération de la fiche prompt ──
    # Tous nullable côté DB pour rétro-compat. La validation strict
    # (4 obligatoires) est portée par PromptCreate Pydantic — les anciens
    # prompts restent valides en DB, les nouveaux doivent renseigner.
    prompt_platform: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    prompt_model_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    prompt_weirdness: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    prompt_style_influence: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    prompt_vocal_gender: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    # ── C4 Monde Visuel V1 (migration 0057) — champs IMAGE ────────────────
    # Tous nullable côté DB : remplis SEULEMENT pour product_type='image'.
    # La provenance (image_platform + image_model_version) est rendue
    # obligatoire pour les images par ck_prompts_image_provenance.
    # image_r2_key = ORIGINAL (jamais servi publiquement, gated derrière achat).
    # preview_r2_key = APERÇU réduit (≤1024px), public.
    image_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_r2_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_r2_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── C4 Taxonomie visuelle (migration 0061) — DNA image ────────────────
    # Nullable : remplis SEULEMENT pour product_type='image', et facultatifs
    # même alors (le style est recommandé, pas obligatoire — ne casse pas la
    # création existante). Servent à la recherche/découverte du Monde Image
    # (filtres ?style= et ?tag= sur GET /images).
    #   image_style : style de rendu (valeur unique parmi STYLES, cf. images.py)
    #   image_tags  : tags d'usage CSV (sous-ensemble de USAGE_TAGS, incl. 'fx')
    # Aucune contrainte DB enum : la validation (valeur hors-liste ignorée) est
    # portée côté router pour rester souple et portable.
    image_style: Mapped[str | None] = mapped_column(String(40), nullable=True)
    image_tags: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── C4 « Oeuvre complete » (migration 0059) — liaison 1:1 son <-> image ──
    # Pointe vers l'AUTRE produit de la paire (un son lie a une image ou
    # l'inverse). NULL = produit non lie. Self-FK ON DELETE SET NULL. La regle
    # 1:1 + nature croisee (image <-> son, jamais image <-> image) est portee
    # par le service link_products ; la colonne ne contraint que le type.
    linked_prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Nature du lien (migration 0059). TRUE = « ne ensemble » : les DEUX
    # produits ont ete crees dans la MEME action (flux A « vendre aussi la
    # pochette comme image »). Effet : ils ne s'affichent PAS en carte
    # individuelle sur les surfaces publiques (catalogues, top, vitrine
    # profil) — uniquement via la carte « Oeuvre complete ». FALSE = « lie
    # apres coup » (flux B, lien manuel) : les deux restent visibles
    # individuellement. Achat separe conserve dans TOUS les cas (pur effet
    # d'affichage). Repasse a FALSE a la deliaison / suppression d'une moitie.
    bundle_exclusive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
