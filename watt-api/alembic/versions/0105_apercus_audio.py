"""apercus_audio — écoute publique en version légère, original après achat

Revision ID: 0105_apercus_audio
Revises: 0104_fichiers_a_traiter
Create Date: 2026-10-13

Lot H. Jusqu'ici, l'adresse d'écoute d'un son menait au fichier ORIGINAL
(souvent un WAV de plusieurs dizaines de Mo), le même que celui vendu avec la
recette : il était récupérable sans achat, et lent à charger sur téléphone.

- `tracks.apercu_key` : clé de stockage de la version d'écoute (MP3 128 kb/s,
  durée complète, métadonnées retirées). C'est la seule adresse publique.
- L'original est recopié sous une clé secrète (jamais renvoyée au
  navigateur) ; seul le téléchargement réservé aux acheteurs le lit.
- Nouvelle opération `proteger_audio` dans `fichiers_a_traiter` : faite par
  l'application après la publication d'un son, et pour tous les sons déjà en
  ligne par la boucle d'entretien (au démarrage, puis chaque jour).

Aucune donnée existante n'est modifiée par la migration elle-même.
Rollback : suppression de la colonne et retour à la contrainte de 0104.
"""
import sqlalchemy as sa
from alembic import op

revision = "0105_apercus_audio"
down_revision = "0104_fichiers_a_traiter"
branch_labels = None
depends_on = None

_AVANT = "action IN ('supprimer', 'vers_prive', 'vers_public')"
_APRES = "action IN ('supprimer', 'vers_prive', 'vers_public', 'proteger_audio')"


def upgrade() -> None:
    op.add_column("tracks", sa.Column("apercu_key", sa.String(500), nullable=True))
    op.drop_constraint("ck_fichiers_a_traiter_action", "fichiers_a_traiter", type_="check")
    op.create_check_constraint("ck_fichiers_a_traiter_action", "fichiers_a_traiter", _APRES)


def downgrade() -> None:
    op.execute("DELETE FROM fichiers_a_traiter WHERE action = 'proteger_audio'")
    op.drop_constraint("ck_fichiers_a_traiter_action", "fichiers_a_traiter", type_="check")
    op.create_check_constraint("ck_fichiers_a_traiter_action", "fichiers_a_traiter", _AVANT)
    op.drop_column("tracks", "apercu_key")
