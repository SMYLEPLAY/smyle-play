"""trophees_sans_recompense — paliers acquis pendant le masquage (Lot 3)

Revision ID: 0096_trophees_sans_recompense
Revises: 0095_promo_non_retirable
Create Date: 2026-09-24

Décision Tom (23/09) : au rallumage des trophées (1er déc.), les paliers DÉJÀ
atteints donnent le badge mais PAS les Smyles ; seuls les paliers atteints
APRÈS la réactivation créditent.

Équivalent robuste d'une « date de réactivation » : pendant que les trophées
sont masqués, chaque palier franchi est ENREGISTRÉ au moment exact où il est
franchi (le calcul a lieu à chaque action, comme avant), mais SANS crédit et
marqué `reward_forfeited = true`. Au rallumage, ces badges apparaissent ; un
palier franchi après le rallumage est crédité normalement. Aucun calcul
« à une date donnée » n'est nécessaire (certains axes — gains cumulés, série —
ne sont pas datables), et il n'y a pas de rattrapage massif de Smyles.

Ajout : `user_achievements.reward_forfeited` BOOLEAN NOT NULL DEFAULT false.
Rollback : drop de la colonne.
"""
import sqlalchemy as sa
from alembic import op

revision = "0096_trophees_sans_recompense"
down_revision = "0095_promo_non_retirable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_achievements", sa.Column(
        "reward_forfeited", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("user_achievements", "reward_forfeited")
