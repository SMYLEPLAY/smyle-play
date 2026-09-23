"""oeuvre_track_link — liaison Œuvre au niveau du MORCEAU (Lot 2, C4)

Revision ID: 0093_oeuvre_track_link
Revises: 0092_takedown_pioneer_revocation
Create Date: 2026-09-23

L'Œuvre = 1 son + 1 image (décision 23/09). Jusqu'ici la liaison (0059) ne
reliait que deux lignes `prompts` : une RECETTE sonore et une IMAGE. Un morceau
publié sans recette (écoute seule, ou recette incomplète à l'envoi) ne pouvait
donc pas recevoir d'image.

Ajout : `prompts.linked_track_id` (UUID NULL, FK tracks ON DELETE SET NULL),
porté par l'IMAGE seulement. Une image est liée à un morceau ; si ce morceau a
une recette, la liaison historique recette <-> image (linked_prompt_id) est
posée EN PLUS, pour que toutes les surfaces existantes continuent de marcher.

Contraintes :
  - `ck_prompts_linked_track_image_only` : seule une image porte un morceau ;
  - `uq_prompts_linked_track_id` (index unique partiel) : un morceau = une
    image au plus (1:1).

Rétrocompatibilité : aucune donnée existante n'est modifiée. Les Œuvres déjà
liées par recette se lisent comme avant ; le morceau d'une telle Œuvre se
retrouve par `tracks.prompt_id` (résolu à la lecture, cf. services/links.py).

Rollback : drop de l'index, de la contrainte et de la colonne.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0093_oeuvre_track_link"
down_revision = "0092_takedown_pioneer_revocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column(
            "linked_track_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tracks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_prompts_linked_track_image_only",
        "prompts",
        "linked_track_id IS NULL OR product_type = 'image'",
    )
    op.create_index(
        "uq_prompts_linked_track_id",
        "prompts",
        ["linked_track_id"],
        unique=True,
        postgresql_where=sa.text("linked_track_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_prompts_linked_track_id", table_name="prompts")
    op.drop_constraint("ck_prompts_linked_track_image_only", "prompts", type_="check")
    op.drop_column("prompts", "linked_track_id")
