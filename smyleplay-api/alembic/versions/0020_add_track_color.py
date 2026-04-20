"""couleur par morceau (track_color) — cellule orpheline sur /u/<slug>

Revision ID: 0020_add_track_color
Revises: 0019_tighten_prompt_text_bounds
Create Date: 2026-04-20

Contexte produit — Étape 2 :
  Sur la page publique /u/<slug>, les morceaux qui ne sont PAS encore rangés
  dans une playlist (« orphelins ») s'affichent comme des petites cellules
  carrées. Pour que l'artiste puisse personnaliser visuellement chacun de
  ses sons (sans devoir se rabattre sur la cover au cas où il n'en a pas
  mis), on stocke une couleur hex par track. Si la couleur est NULL, on
  retombe sur la brandColor de l'artiste, puis sur l'or WATT par défaut.

Ajouts :
  - tracks.color : VARCHAR(7) NULL, format "#RRGGBB"

Nullable intentionnel :
  - migration non destructive (pas de DEFAULT) — les tracks existantes
    restent à NULL et héritent de la brandColor de leur auteur, ce qui
    préserve l'UX actuelle tant que l'artiste n'a pas été explicite.

Pas de CHECK contrainte en DB :
  - validation format faite côté Pydantic (regex ^#[0-9a-fA-F]{6}$). Rester
    additif-only en DB permet d'accepter des palettes étendues plus tard
    (gradients, HSL) sans rupture. Cohérent avec users.profile_*_color
    (migration 0017) qui a pris le même parti.
"""
import sqlalchemy as sa
from alembic import op


revision = "0020_add_track_color"
down_revision = "0019_tighten_prompt_text_bounds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracks", "color")
