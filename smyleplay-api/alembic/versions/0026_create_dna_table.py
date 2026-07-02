"""crée la table dna manquante (fix bug 500 POST /tracks/)

Revision ID: 0026_create_dna_table
Revises: 0025_track_cover_and_prompt_link
Create Date: 2026-05-05

Bug détecté 2026-05-05 lors du 1er test bout-en-bout du pivot écoute :
POST /tracks/ retournait 500 "UndefinedTableError: relation 'dna' does
not exist". Le modèle SQLAlchemy `app.models.dna.DNA` (table `dna`)
existait depuis la phase initiale mais aucune migration Alembic ne
l'a jamais créée en DB. Conséquence : impossible de créer un track
puisque create_track_with_dna insère dans `dna` après `tracks`.

Cette migration crée la table avec exactement le shape du modèle
SQLAlchemy. Pas de backfill (la table était simplement absente,
pas de données legacy à récupérer).

Schema :
  - id (UUID, PK, default=uuid_generate_v4)
  - track_id (UUID, FK tracks(id) ON DELETE CASCADE, UNIQUE, NOT NULL)
    → contrainte 1-1 stricte : un track a 0 ou 1 DNA, pas plus.
  - artist_id (UUID, FK users(id), NOT NULL)
    → pas de CASCADE car on veut préserver l'historique DNA même si
       l'user est supprimé (RESTRICT par défaut).
  - full_prompt (TEXT, NOT NULL)
    → recette IA complète associée au track. Visible à l'owner et aux
       acheteurs (cf project_prompt_visibility_rule).
  - created_at (TIMESTAMPTZ, default now())

Index :
  - ix_dna_track_id (sur track_id) — JOIN fréquent (track + dna ensemble)
  - ix_dna_artist_id (sur artist_id) — pour filtrer par artiste
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0026_create_dna_table"
down_revision = "0025_track_cover_and_prompt_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dna",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("full_prompt", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # UNIQUE sur track_id : un track a au plus 1 DNA. Empêche le
    # double-insert si create_track_with_dna est appelé 2 fois sur le
    # même track.
    op.create_unique_constraint(
        "uq_dna_track_id", "dna", ["track_id"]
    )
    op.create_index("ix_dna_track_id", "dna", ["track_id"])
    op.create_index("ix_dna_artist_id", "dna", ["artist_id"])


def downgrade() -> None:
    op.drop_index("ix_dna_artist_id", table_name="dna")
    op.drop_index("ix_dna_track_id", table_name="dna")
    op.drop_constraint("uq_dna_track_id", "dna", type_="unique")
    op.drop_table("dna")
