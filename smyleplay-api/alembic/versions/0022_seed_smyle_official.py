"""colonne is_official + seed du compte Smyle officiel

Revision ID: 0022_seed_smyle_official
Revises: 0021_add_playlists
Create Date: 2026-04-20

Contexte produit — Phase 2 refonte marketplace :

  Introduction du compte "Smyle" officiel, seul compte de la plateforme
  marqué `is_official = TRUE`. Il sert de :
    - vitrine sur l'accueil (marketplace) : les playlists modèles
      (Jungle Osmose, Night City, Hit Mix, Sunset Lover) lui appartiennent ;
    - badge de confiance (checkmark coloré) distinct des artistes tiers ;
    - point d'ancrage éditorial (tracks & packs mis en avant).

  Design choices :
    • `is_official` BOOLEAN NOT NULL DEFAULT FALSE : flag serveur, pas un
      rôle utilisateur. Aucun user ne peut l'auto-attribuer via l'API —
      il n'est écrit qu'ici en migration (et par un éventuel script d'ops).
    • un seul index partiel sur `is_official = TRUE` : on attend 1 ligne,
      donc scanner "le compte officiel" est instantané sans peser sur les
      writes normaux.
    • insertion idempotente via `ON CONFLICT (email) DO NOTHING` : si le
      seed est rejoué (ex. DB détruite, migration relancée en dev), on
      n'écrase pas un éventuel état artisanal et on ne double pas le user.
    • mot de passe : bcrypt d'un token aléatoire 64-bytes généré à la
      migration. Personne ne connaît ce mot de passe → le compte n'est
      pas login-able, il est piloté uniquement en write côté ops.
    • `artist_name='Smyle'`, `profile_public=true` : apparaît immédiatement
      dans /watt/artists dès que 0022 est appliquée.

  Rollback :
    • `downgrade()` supprime le user Smyle puis drop la colonne.
    • Note : si des tracks/playlists pointent vers ce user via FK
      ON DELETE CASCADE, elles disparaîtront aussi — c'est voulu pour un
      rollback propre.
"""
import secrets

import bcrypt
import sqlalchemy as sa
from alembic import op


revision = "0022_seed_smyle_official"
down_revision = "0021_add_playlists"
branch_labels = None
depends_on = None


# Constantes du compte officiel. Séparées en module-level pour être réutilisées
# par downgrade() sans risque de dérive.
SMYLE_EMAIL = "smyle@smyleplay.com"
SMYLE_ARTIST_NAME = "Smyle"
SMYLE_BRAND_COLOR = "#7C3AED"  # violet WATT canonique
SMYLE_BIO = (
    "Compte officiel Smyle. Nos playlists modèles, nos sons de référence, "
    "l'ADN collectif de la plateforme."
)
SMYLE_GENRE = "Tous styles"
SMYLE_CITY = "Paris"


def upgrade() -> None:
    # ── 1. Colonne is_official ────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "is_official",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Index partiel : 1 ligne attendue → lookup O(1) sans peser sur les writes.
    op.create_index(
        "ix_users_is_official_true",
        "users",
        ["is_official"],
        unique=False,
        postgresql_where=sa.text("is_official = TRUE"),
    )

    # ── 2. Seed idempotent du compte Smyle ────────────────────────────────
    # Mot de passe : bcrypt d'un token aléatoire 64 bytes. Personne ne le
    # connaît → compte non login-able, c'est volontaire.
    random_password = secrets.token_urlsafe(64)
    password_hash = bcrypt.hashpw(
        random_password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    users_table = sa.table(
        "users",
        sa.column("email", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("artist_name", sa.String),
        sa.column("bio", sa.Text),
        sa.column("genre", sa.String),
        sa.column("city", sa.String),
        sa.column("brand_color", sa.String),
        sa.column("profile_public", sa.Boolean),
        sa.column("is_official", sa.Boolean),
    )

    # ON CONFLICT (email) DO NOTHING pour que le rejouage soit safe.
    # On passe par une instruction SQL brute car alembic.op.bulk_insert ne
    # supporte pas ON CONFLICT, et on veut garder l'idempotence stricte.
    op.execute(
        sa.text(
            """
            INSERT INTO users (
                email, password_hash, artist_name, bio, genre, city,
                brand_color, profile_public, is_official
            ) VALUES (
                :email, :password_hash, :artist_name, :bio, :genre, :city,
                :brand_color, TRUE, TRUE
            )
            ON CONFLICT (email) DO NOTHING
            """
        ).bindparams(
            email=SMYLE_EMAIL,
            password_hash=password_hash,
            artist_name=SMYLE_ARTIST_NAME,
            bio=SMYLE_BIO,
            genre=SMYLE_GENRE,
            city=SMYLE_CITY,
            brand_color=SMYLE_BRAND_COLOR,
        )
    )


def downgrade() -> None:
    # On supprime d'abord le user seed (FK cascade s'applique).
    op.execute(
        sa.text("DELETE FROM users WHERE email = :email").bindparams(
            email=SMYLE_EMAIL
        )
    )
    op.drop_index("ix_users_is_official_true", table_name="users")
    op.drop_column("users", "is_official")
