"""user_is_pioneer — marqueur Pionnier (Brique 1)

Revision ID: 0090_user_is_pioneer
Revises: 0089_treasury_account
Create Date: 2026-09-20

Statut Pionnier : commission plafonnée à 10 % À VIE, selon la règle du **taux le
plus favorable** (décision Tom 20/09) — un Pionnier ne paie jamais plus de 10 %,
mais un Mythique Pionnier garde ses 5 %.

Cette migration ne pose QUE le marqueur (colonne booléenne, défaut false).
L'ATTRIBUTION (les 100 premiers créateurs, rang figé) n'est PAS codée ici :
la règle de sélection n'est pas tranchée, c'est la Brique 2. Tant que personne
n'est marqué, le barème par palier (20 / 12 / 5) s'applique inchangé.

Colonne simple, `NOT NULL DEFAULT false` : en PostgreSQL 11+ l'ajout d'une
colonne avec défaut constant est une opération de métadonnée (pas de réécriture
de table) → instantanée, sans risque de déploiement.

N'AJOUTE AUCUN bucket : le CHECK de somme A1.4 (0088) n'est pas touché.

Rollback : suppression de la colonne.
"""
import sqlalchemy as sa
from alembic import op

revision = "0090_user_is_pioneer"
down_revision = "0089_treasury_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_pioneer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_pioneer")
