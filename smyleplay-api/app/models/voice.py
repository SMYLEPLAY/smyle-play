"""
Modèles Voice + OwnedVoice (P1-F9 — vente de voix sample audio).

Pendant : `tracks_for_sale` n'existe pas — on a `tracks` qui est multi-usage
(stream + métadonnées + prompt vendable). Pour les voix on crée une table
dédiée `voices_for_sale` parce que :

  - Le cycle de vie est différent : une voix mise en vente n'a pas de
    "play count", pas de cover, pas de DNA attaché. C'est un asset
    téléchargeable, pas un objet de stream.
  - La séparation simplifie les requêtes profil ("ses tracks vs ses voix
    à vendre") et évite de polluer `tracks.kind = 'voice'` avec des champs
    NULL en majorité.
  - Mémoire : règle Tom (project_voice_separation_rule) — voix séparées
    du flux musical, table et endpoints distincts.

Pas d'enum Postgres pour la licence (CHECK constraint VARCHAR à la place)
pour faciliter l'ajout futur d'une licence sans DROP/CREATE TYPE. Voir la
docstring de la migration 0023 pour le raisonnement complet.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# Licences valides — alignées sur ck_voices_license_enum (migration 0023).
# Si on ajoute une valeur ici, ALTER la CHECK constraint dans une nouvelle
# migration. Centralisé pour pouvoir importer depuis schemas et services.
VOICE_LICENSES = ("personnel", "commercial", "exclusif")


class Voice(Base):
    """
    Voix mise en vente par un artiste.

    - Plusieurs voix possibles par artiste (pas de UNIQUE artist_id) — un
      beatmaker peut publier plusieurs samples (homme/femme, styles, langues).
    - `is_published=False` par défaut : création != publication. Toggle
      explicite via PATCH /api/voices/{id} { is_published: true }.
    - `sample_url` est NOT NULL : on refuse une voix sans sample audio.
      Le frontend doit upload R2 d'abord, puis envoyer l'URL. Évite l'état
      "fiche existante, audio manquant" qui ouvrirait des trous UX (acheteur
      paie sans recevoir l'asset).
    - `genres` est un JSONB array de strings — recherche par genre via
      jsonb_array_elements côté SQL. Volume max ~10 chips, pas de junction.
    - Prix CHECK 50 ≤ price_credits ≤ 5000.
    """

    __tablename__ = "voices_for_sale"
    __table_args__ = (
        CheckConstraint(
            "price_credits >= 50 AND price_credits <= 5000",
            name="ck_voices_price_credits_range",
        ),
        CheckConstraint(
            "license IN ('personnel', 'commercial', 'exclusif')",
            name="ck_voices_license_enum",
        ),
        CheckConstraint(
            "char_length(name) >= 1 AND char_length(name) <= 40",
            name="ck_voices_name_length",
        ),
        CheckConstraint(
            "char_length(style) >= 1 AND char_length(style) <= 80",
            name="ck_voices_style_length",
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
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    style: Mapped[str] = mapped_column(String(80), nullable=False)
    # JSONB array de strings — ex ["RnB", "Pop", "Trap"]. Default = []
    genres: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="'[]'::jsonb",
    )
    sample_url: Mapped[str] = mapped_column(String(500), nullable=False)
    license: Mapped[str] = mapped_column(String(16), nullable=False)
    price_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(
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


class OwnedVoice(Base):
    """
    Jointure user ↔ voice. Représente la possession permanente d'une voix.

    - PK composite (user_id, voice_id) : un user ne peut acheter une voix
      qu'une seule fois. Un éventuel "renouveler la licence" devra être
      modélisé séparément (transactions multiples mais 1 ligne owned_voices).
    - CASCADE des deux côtés : si user OU voix supprimés → la possession
      disparaît. L'historique reste dans `transactions` (audit trail).
    - Pas de stockage de la licence ici : elle est figée dans
      `transactions.metadata_json` au moment de l'achat. Si on changeait
      le mapping pricing/licence plus tard, l'achat passé reste cohérent.
    """

    __tablename__ = "owned_voices"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "voice_id", name="pk_owned_voices"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    voice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voices_for_sale.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
