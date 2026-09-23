"""pioneer_rank — rang Pionnier figé + exclusion persistée (Brique 2)

Revision ID: 0091_pioneer_rank
Revises: 0090_user_is_pioneer
Create Date: 2026-09-23

Programme Pionnier (décision Tom 23/09) : les 100 PREMIERS créateurs qui publient
une œuvre deviennent Pionniers (commission plafonnée à 10 % à vie, cf. 0090).
Le rang est FIGÉ à vie.

Colonnes ajoutées sur `users` :
  - `pioneer_rank`       INTEGER NULL — rang 1..100, UNIQUE (deux comptes ne
    peuvent jamais porter le même rang ; plusieurs NULL autorisés) ;
  - `pioneer_awarded_at` TIMESTAMPTZ NULL — horodatage d'attribution (audit) ;
  - `pioneer_excluded`   BOOLEAN NOT NULL DEFAULT false — exclusion PERSISTÉE.
    Posée par l'action admin de rattrapage (« exclure ces comptes ») : un compte
    exclu ne reçoit JAMAIS de rang, ni au rattrapage ni plus tard en direct
    (sinon un compte de test exclu reprendrait une place à sa prochaine
    publication).

Contraintes :
  - `ck_users_pioneer_rank_range`   : pioneer_rank IS NULL OR 1..100 ;
  - `uq_users_pioneer_rank`         : unicité du rang (filet DB anti-course,
    en plus du verrou applicatif qui sérialise les attributions) ;
  - `ck_users_pioneer_coherent`     : is_pioneer = (pioneer_rank IS NOT NULL).
    Le statut Pionnier n'existe QUE par l'attribution d'un rang.

Sûreté : colonnes neuves (NULL / false partout), donc les contraintes sont
trivialement satisfaites à la pose ; `users` est une petite table → pose directe.
N'AJOUTE AUCUN bucket : le CHECK de somme A1.4 n'est pas touché.

Rollback : drop des contraintes et des colonnes.
"""
import sqlalchemy as sa
from alembic import op

revision = "0091_pioneer_rank"
down_revision = "0090_user_is_pioneer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pioneer_rank", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column("pioneer_awarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "pioneer_excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_users_pioneer_rank_range",
        "users",
        "pioneer_rank IS NULL OR (pioneer_rank >= 1 AND pioneer_rank <= 100)",
    )
    op.create_unique_constraint("uq_users_pioneer_rank", "users", ["pioneer_rank"])
    op.create_check_constraint(
        "ck_users_pioneer_coherent",
        "users",
        "is_pioneer = (pioneer_rank IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_pioneer_coherent", "users", type_="check")
    op.drop_constraint("uq_users_pioneer_rank", "users", type_="unique")
    op.drop_constraint("ck_users_pioneer_rank_range", "users", type_="check")
    op.drop_column("users", "pioneer_excluded")
    op.drop_column("users", "pioneer_awarded_at")
    op.drop_column("users", "pioneer_rank")
