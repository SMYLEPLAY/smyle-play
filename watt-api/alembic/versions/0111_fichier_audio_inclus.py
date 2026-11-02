"""fichier_audio_inclus — un son ne donne plus son fichier, sauf beat (02/11)

Revision ID: 0111_fichier_audio_inclus
Revises: 0110_preuve_achat_carte
Create Date: 2026-11-02

Décision Tom du 02/11/2026 (OBSIDIAN 01_PRODUIT/2026-11-02_DECISION-studios-
adn-et-fichiers) : acheter un SON donne la recette, plus le fichier audio.
Le fichier reste vendu avec les BEATS (section « Poster un beat »).

Droits acquis : tout exemplaire débloqué AVANT cette migration a été vendu
comme « fichier + recette » → `fichier_inclus = TRUE` pour toutes les lignes
existantes. Les nouveaux exemplaires naissent à FALSE (le beat, lui, donne le
fichier par sa nature, cf. app.services.fichier_audio). La migration tourne
au déploiement (railway.toml, preDeployCommand) : la bascule coïncide avec la
mise en ligne. Une revente transfère la ligne → le droit suit l'exemplaire.

Rollback : suppression de la colonne (le téléchargement redevient universel
seulement si le code est aussi revenu en arrière).
"""
import sqlalchemy as sa
from alembic import op

revision = "0111_fichier_audio_inclus"
down_revision = "0110_preuve_achat_carte"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "unlocked_prompts",
        sa.Column("fichier_inclus", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE unlocked_prompts SET fichier_inclus = TRUE")


def downgrade() -> None:
    op.drop_column("unlocked_prompts", "fichier_inclus")
