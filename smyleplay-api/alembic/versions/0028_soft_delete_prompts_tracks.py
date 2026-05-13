"""feat: soft-delete prompts & tracks (is_deleted flag)

Révision : 0028_soft_delete_prompts_tracks
Précédente : 0027_voice_origin_and_linked_track

Pourquoi :
  - UnlockedPrompt.prompt_id a ondelete="CASCADE" → hard-delete détruit
    les achats des acheteurs. Interdit business.
  - La règle métier est : artiste peut RETIRER un produit du marketplace,
    mais les acheteurs gardent leur accès en library.
  - Implémentation : is_deleted=TRUE + is_published=FALSE côté artiste.
    Les queries marketplace filtrent is_deleted=FALSE.
    La library (UnlockedPrompt join) ne filtre PAS is_deleted.

Champs ajoutés :
  - prompts.is_deleted  BOOLEAN NOT NULL DEFAULT FALSE
  - tracks.is_deleted   BOOLEAN NOT NULL DEFAULT FALSE
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_soft_delete_prompts_tracks"
down_revision = "0027_voice_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index(
        "ix_prompts_is_deleted",
        "prompts",
        ["is_deleted"],
    )

    op.add_column(
        "tracks",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index(
        "ix_tracks_is_deleted",
        "tracks",
        ["is_deleted"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_is_deleted", table_name="tracks")
    op.drop_column("tracks", "is_deleted")

    op.drop_index("ix_prompts_is_deleted", table_name="prompts")
    op.drop_column("prompts", "is_deleted")
