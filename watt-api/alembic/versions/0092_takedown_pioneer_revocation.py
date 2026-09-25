"""takedown + pioneer_revocations — anti-squat Pionnier (Lot 2, décision Tom 23/09)

Revision ID: 0092_takedown_pioneer_revocation
Revises: 0091_pioneer_rank
Create Date: 2026-09-23

Règle validée par Tom : le rang Pionnier est acquis « à vie, sauf fraude ».
Deux besoins :

1. Un contenu RETIRÉ par la modération doit le rester, et ne plus jamais
   qualifier personne au programme Pionnier. Aujourd'hui le retrait passe
   `is_published` à false : le créateur pouvait le republier (PATCH) et
   requalifier son compte. On ajoute `taken_down_at` (TIMESTAMPTZ NULL) sur les
   cinq tables d'œuvres (prompts, adns, visual_adns, voices_for_sale, tracks)
   et un TRIGGER qui maintient le contenu caché tant que la marque est posée,
   QUEL QUE SOIT le chemin d'écriture (≈10 routes de publication) :
     - prompts / adns / visual_adns / voices_for_sale : is_published forcé à false ;
     - tracks (pas de drapeau de publication) : is_deleted forcé à true.
   Lever la marque (NULL) est une action de modération explicite (base).

2. Journal des révocations de rang (`pioneer_revocations`) : qui, quel rang,
   motif OBLIGATOIRE (CHECK non vide), par quel admin, et à qui la place a été
   réattribuée. Append-only par usage (aucune route de modification).

Sûreté : colonnes neuves NULL partout → aucun contenu existant n'est touché ;
le trigger ne change rien tant qu'aucune marque n'est posée. Aucun bucket de
solde n'est touché (CHECK de somme A1.4 inchangé).

Rollback : drop des triggers, de la fonction, de la table et des colonnes.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0092_takedown_pioneer_revocation"
down_revision = "0091_pioneer_rank"
branch_labels = None
depends_on = None

# Tables d'œuvres et la façon de « rester caché » pour chacune.
_PUBLISHED_TABLES = ("prompts", "adns", "visual_adns", "voices_for_sale")
_DELETED_TABLES = ("tracks",)

_FN_PUBLISHED = """
CREATE OR REPLACE FUNCTION keep_taken_down_unpublished() RETURNS trigger AS $$
BEGIN
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.is_published := FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FN_DELETED = """
CREATE OR REPLACE FUNCTION keep_taken_down_deleted() RETURNS trigger AS $$
BEGIN
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.is_deleted := TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    for t in _PUBLISHED_TABLES + _DELETED_TABLES:
        op.add_column(
            t, sa.Column("taken_down_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute(_FN_PUBLISHED)
    op.execute(_FN_DELETED)
    for t in _PUBLISHED_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{t}_keep_taken_down BEFORE INSERT OR UPDATE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION keep_taken_down_unpublished()"
        )
    for t in _DELETED_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{t}_keep_taken_down BEFORE INSERT OR UPDATE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION keep_taken_down_deleted()"
        )

    op.create_table(
        "pioneer_revocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "revoked_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reassigned_to",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(reason)) >= 3", name="ck_pioneer_revocations_reason"
        ),
        sa.CheckConstraint(
            "rank >= 1 AND rank <= 100", name="ck_pioneer_revocations_rank"
        ),
    )


def downgrade() -> None:
    op.drop_table("pioneer_revocations")
    for t in _PUBLISHED_TABLES + _DELETED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_keep_taken_down ON {t}")
    op.execute("DROP FUNCTION IF EXISTS keep_taken_down_unpublished()")
    op.execute("DROP FUNCTION IF EXISTS keep_taken_down_deleted()")
    for t in _PUBLISHED_TABLES + _DELETED_TABLES:
        op.drop_column(t, "taken_down_at")
