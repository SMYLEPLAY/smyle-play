"""user_activity_days — activité par jour (Lot 2, mesures « prêt à sortir »)

Revision ID: 0094_user_activity_days
Revises: 0093_oeuvre_track_link
Create Date: 2026-09-23

Base du futur agent analytique : une ligne par (utilisateur, jour) où le compte
a été vu CONNECTÉ. Écrite au plus une fois par jour et par compte (cache
mémoire + INSERT … ON CONFLICT DO NOTHING, hors du chemin de la requête).

Colonnes :
  - user_id  UUID FK users ON DELETE CASCADE (RGPD : la suppression d'un compte
             efface son historique d'activité) ;
  - day      DATE (UTC) ;
  - listened BOOLEAN — le compte a ÉCOUTÉ un son ce jour-là en étant connecté.
             Les écoutes (`play_events`) sont anonymes par conception ; ce
             drapeau est la seule façon d'attribuer « écouter » à un actif,
             sans rien stocker de plus fin (ni quel son, ni combien).
PK (user_id, day) → idempotence et unicité ; index sur day pour les agrégats.

Aucune donnée existante touchée. Rollback : drop de la table.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0094_user_activity_days"
down_revision = "0093_oeuvre_track_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_activity_days",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column(
            "listened", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_index("ix_user_activity_days_day", "user_activity_days", ["day"])


def downgrade() -> None:
    op.drop_index("ix_user_activity_days_day", table_name="user_activity_days")
    op.drop_table("user_activity_days")
