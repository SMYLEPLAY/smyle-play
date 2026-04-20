import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "credits_balance >= 0",
            name="ck_users_credits_balance_nonneg",
        ),
        CheckConstraint(
            "credits_earned_total >= 0",
            name="ck_users_credits_earned_total_nonneg",
        ),
        CheckConstraint(
            "language IN ('en', 'fr', 'es')",
            name="ck_users_language_enum",
        ),
        # Phase 9 : couleur de marque (hex strict #RRGGBB), nullable
        CheckConstraint(
            "brand_color IS NULL OR brand_color ~ '^#[0-9A-Fa-f]{6}$'",
            name="ck_users_brand_color_hex",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- Profil artiste ---
    artist_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    universe_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Chantier 1.2 : champs de profil remontés depuis le legacy Flask.
    # Tous nullable — un compte frais n'a rien de rempli, le front gère.
    genre:      Mapped[str | None] = mapped_column(String(100), nullable=True)
    city:       Mapped[str | None] = mapped_column(String(100), nullable=True)
    soundcloud: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instagram:  Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube:    Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Chantier "Profil artiste type" (migration 0016) : refonte complète.
    # Cover = bannière en tête de page. Influences = bio longue "inspirations".
    # Socials étendus : tiktok / spotify / twitter_x.
    cover_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    influences:      Mapped[str | None] = mapped_column(Text,        nullable=True)
    tiktok:          Mapped[str | None] = mapped_column(String(255), nullable=True)
    spotify:         Mapped[str | None] = mapped_column(String(500), nullable=True)
    twitter_x:       Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Phase 9 : couleur de marque, propagée sur profil + cartes prompts + ADN
    # Format hex strict #RRGGBB validé par CHECK constraint SQL
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Chantier "Profil artiste type" (migration 0017) : 2 couleurs de thème
    # pour la page publique, pilotées depuis le dashboard avant publication.
    #   profile_bg_color    → --bg    (couleur de fond)
    #   profile_brand_color → --brand (couleur d'accent / écritaux)
    # Null = fallback au thème violet WATT par défaut côté front.
    profile_bg_color:    Mapped[str | None] = mapped_column(String(7), nullable=True)
    profile_brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Chantier "Positionnement fan/artiste" (migration 0018) : casquettes
    # déclarées par l'utilisateur. JSON array de slugs — cf. ROLE_CODES
    # dans app/schemas/user.py pour la liste canonique fermée.
    # NULL = pas encore choisi (UI propose un CTA "définis ta casquette").
    # Array vide [] = explicitement "aucune casquette" (rare mais valide).
    roles: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Chantier 1 : visibilité publique du profil artiste.
    # Tant que FALSE → l'utilisateur n'apparaît ni dans /watt/artists,
    # ni dans le Réseau Créatif, ni sur l'accueil.
    # Le flag bascule à TRUE quand l'utilisateur publie son profil depuis
    # le wattboard (artist_name + bio non-vides + au moins 1 track).
    profile_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Phase 2 refonte marketplace (migration 0022) : flag serveur pour le
    # compte officiel "Smyle". Un seul user porte TRUE dans la base — il
    # est utilisé pour (a) afficher le checkmark coloré, (b) le prioriser
    # en tête des listes marketplace, (c) lui attacher les 4 playlists
    # modèles (Jungle Osmose, Night City, Hit Mix, Sunset Lover).
    # Ne peut être écrit qu'en migration ou par un script d'ops ; l'API
    # publique ne l'expose pas en write.
    is_official: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # --- Préférences ---
    language: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        default="en",
        server_default="en",
    )

    # --- Économie ---
    credits_balance: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
    )
    credits_earned_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # --- Timestamps ---
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
