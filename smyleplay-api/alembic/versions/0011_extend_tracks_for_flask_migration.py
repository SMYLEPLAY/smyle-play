"""extend tracks table with universe/duration/r2_key/plays for Flask migration

Revision ID: 0011_extend_tracks
Revises: 0010_strict_unlock_check
Create Date: 2026-04-18

Étape 1 de la migration Flask → FastAPI.

Le modèle Track FastAPI d'origine est minimaliste (id, title, audio_url,
artist_id, created_at). Pour pouvoir accueillir les 82 tracks du catalogue
WATT existant (tracks.json côté Flask), on ajoute :

  • universe        : 'sunset-lover' | 'jungle-osmose' | 'night-city' | 'hit-mix' | NULL
                      (NULL = track uploadée par un artiste, pas liée à un univers curaté)
  • duration_seconds: durée audio en secondes (float)
  • r2_key          : clé de l'objet sur Cloudflare R2 (pour suppression/gestion)
  • plays           : compteur de lectures (int, default 0)

Tous les nouveaux champs sont NULLABLE (sauf plays qui a un default 0)
pour ne pas casser les tracks existantes éventuellement créées avant cette
migration.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0011_extend_tracks"
down_revision = "0010b_create_tracks_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("universe", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "tracks",
        sa.Column("duration_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "tracks",
        sa.Column("r2_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "tracks",
        sa.Column(
            "plays",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Contrainte sur les valeurs valides d'universe (NULL autorisé)
    op.create_check_constraint(
        "ck_tracks_universe_enum",
        "tracks",
        "universe IS NULL OR universe IN "
        "('sunset-lover', 'jungle-osmose', 'night-city', 'hit-mix')",
    )

    # Index pour les listings filtrés par univers (home WATT, page univers)
    op.create_index(
        "ix_tracks_universe",
        "tracks",
        ["universe"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_universe", table_name="tracks")
    op.drop_constraint("ck_tracks_universe_enum", "tracks", type_="check")
    op.drop_column("tracks", "plays")
    op.drop_column("tracks", "r2_key")
    op.drop_column("tracks", "duration_seconds")
    op.drop_column("tracks", "universe")
