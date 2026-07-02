"""voice : ajoute preview_url (clip 30s public)

Revision ID: 0029_voice_preview
Revises: 0027_voice_meta
Create Date: 2026-05-13

Tom 2026-05-13 — chantier preview 30s.

L'URL `sample_url` reste mais devient PRIVÉE (gated derrière unlock voix
OU achat track via linked_track_id). Une nouvelle colonne `preview_url`
contient un clip 30s extrait au moment de l'upload — c'est ce clip qui
est exposé publiquement pour la pré-écoute (standard SoundCloud).

Nullable car les voix legacy n'ont pas encore de preview généré
(script ops backfill à lancer manuellement après le déploiement).
"""
from alembic import op
import sqlalchemy as sa


revision = "0029_voice_preview"
down_revision = "0027_voice_meta"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return res is not None


def upgrade() -> None:
    if not _column_exists("voices_for_sale", "preview_url"):
        op.add_column(
            "voices_for_sale",
            sa.Column("preview_url", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("voices_for_sale", "preview_url"):
        op.drop_column("voices_for_sale", "preview_url")
