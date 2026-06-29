"""0045 — masque le compte 'Smyle' doublon vide (nettoyage incident 2026-06-07)

Revision ID: 0045_hide_duplicate_smyle
Revises: 0044_loop_achievements
Create Date: 2026-06-07

Contexte : deux comptes partagent le slug 'smyle'.
  - A (213dd27e…) = le vrai compte officiel : 81 sons, ADN, photo, isOfficial.
  - B (b36dea11…) = ancien seed officiel, VIDE (0 son / 0 playlist / 0 ADN).

Le hotfix #237 a déjà rendu la résolution de slug déterministe (préfère le
compte officiel). Ici on neutralise définitivement la collision en passant le
compte B en NON public : il disparaît de la marketplace et du réseau, mais
AUCUNE donnée n'est supprimée (réversible via downgrade). Ciblage par id exact,
idempotent (no-op si la ligne n'existe pas / déjà masquée).
"""
from alembic import op

revision = "0045_hide_duplicate_smyle"
down_revision = "0044_loop_achievements"
branch_labels = None
depends_on = None

# Compte B — doublon 'Smyle' vide à masquer.
_DUPLICATE_ID = "b36dea11-6ace-4be3-828d-431f43c9ec5d"


def upgrade() -> None:
    op.execute(
        f"UPDATE users SET profile_public = false "
        f"WHERE id = '{_DUPLICATE_ID}'"
    )


def downgrade() -> None:
    # Restaure la visibilité publique (rollback propre).
    op.execute(
        f"UPDATE users SET profile_public = true "
        f"WHERE id = '{_DUPLICATE_ID}'"
    )
