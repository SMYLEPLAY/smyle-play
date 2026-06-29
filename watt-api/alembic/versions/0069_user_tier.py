"""user_tier — palier créateur (C6 paliers + Offres)

Revision ID: 0069_user_tier
Revises: 0068_download_events
Create Date: 2026-06-26

C6 (décision Tom 2026-06-26). Colonne `tier` sur users : palier d'abonnement
créateur, enum fermé ('standard' / 'premium' / 'mythique'), défaut 'standard'.

Le palier détermine :
  - la COMMISSION de vente (20 / 12 / 5 % → part artiste 80 / 88 / 95) ;
  - le nombre d'EMPLACEMENTS de vente simultanés (10 / 50 / illimité) ;
  - la VISIBILITÉ (mise en avant Premium/Mythique).

NOT NULL avec server_default 'standard' : tous les comptes existants
deviennent 'standard' = exactement le comportement historique (80% artiste),
donc aucune vente ne change tant qu'un palier payant n'est pas activé.

CHECK constraint pour verrouiller l'enum côté DB.

Rollback : drop de la contrainte puis de la colonne (aucune dépendance).
"""
import sqlalchemy as sa
from alembic import op


revision = "0069_user_tier"
down_revision = "0068_download_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tier",
            sa.String(16),
            nullable=False,
            server_default="standard",
        ),
    )
    op.create_check_constraint(
        "ck_users_tier_enum",
        "users",
        "tier IN ('standard', 'premium', 'mythique')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_tier_enum", "users", type_="check")
    op.drop_column("users", "tier")
