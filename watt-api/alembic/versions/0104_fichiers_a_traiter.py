"""fichiers_a_traiter — opérations sur les fichiers stockés, rejouables

Revision ID: 0104_fichiers_a_traiter
Revises: 0103_emails_minuscules
Create Date: 2026-10-10

Lot G. Deux opérations sur le stockage des fichiers :

- la purge des fichiers d'un compte supprimé (jusqu'ici une tâche en
  mémoire, qu'un redémarrage pouvait interrompre) ;
- le déplacement vers le stockage privé des fichiers d'un contenu retiré
  par la modération.

Table `fichiers_a_traiter` : une ligne par opération (supprimer, déplacer
vers le stockage privé, remettre en public), écrite DANS la transaction de
l'action qui la demande. L'application la traite juste après la réponse, puis
rejoue chaque jour celles qui n'ont pas abouti (stockage indisponible, bucket
privé pas encore configuré…).

Index partiel sur les produits retirés : le proxy d'images refuse les aperçus
d'un produit retiré sans parcourir toute la table.

Aucune donnée existante n'est modifiée. Rollback : suppression de la table et
de l'index.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0104_fichiers_a_traiter"
down_revision = "0103_emails_minuscules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fichiers_a_traiter",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("cle", sa.String(1024), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("motif", sa.String(40), nullable=True),
        sa.Column("cree_le", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("tentatives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derniere_erreur", sa.String(300), nullable=True),
        sa.Column("fait_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resultat", sa.String(40), nullable=True),
        sa.CheckConstraint(
            "action IN ('supprimer', 'vers_prive', 'vers_public')",
            name="ck_fichiers_a_traiter_action",
        ),
    )
    op.create_index(
        "ix_fichiers_a_traiter_en_attente", "fichiers_a_traiter", ["cree_le"],
        postgresql_where=sa.text("fait_le IS NULL"),
    )
    op.create_index(
        "ix_prompts_retires", "prompts", ["id"],
        postgresql_where=sa.text("taken_down_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_prompts_retires", table_name="prompts")
    op.drop_index("ix_fichiers_a_traiter_en_attente", table_name="fichiers_a_traiter")
    op.drop_table("fichiers_a_traiter")
