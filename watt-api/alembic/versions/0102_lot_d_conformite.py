"""lot_d_conformite — version des CGU, retrait des collections, mesure sans compte

Revision ID: 0102_lot_d_conformite
Revises: 0101_parcours_v1
Create Date: 2026-10-10

Lot D (conformité DSA / RGPD) :

1. `users.accepted_terms_version` (texte, NULL). L'inscription y écrit la
   version des CGU en vigueur (app/core/legal.py::CGU_VERSION). Les comptes
   EXISTANTS restent à NULL : ils devront accepter les nouvelles CGU à leur
   prochaine connexion (fenêtre bloquante + refus serveur des actions qui
   écrivent). `accepted_terms_at` (0083) garde la date de la dernière
   acceptation.

2. `playlists.taken_down_at` et `albums.taken_down_at` : les collections
   peuvent être retirées par la modération, comme les œuvres (0092). Un
   trigger les garde PRIVÉES tant que la marque est posée, quel que soit le
   chemin d'écriture ; lever la marque n'est possible que par la restauration
   admin (même garde `watt.restauration` que 0098).

3. Mesure d'audience : `analytics_events.user_id` est vidé et interdit
   (CHECK user_id IS NULL). La mesure annoncée comme anonyme ne rattache plus
   aucun événement à un compte.

Sûreté : colonnes neuves NULL, aucun contenu existant n'est masqué ; aucun
solde n'est touché.

Rollback : drop des triggers, de la fonction, du CHECK et des colonnes (les
`user_id` effacés de la mesure ne reviennent pas).
"""
import sqlalchemy as sa
from alembic import op

revision = "0102_lot_d_conformite"
down_revision = "0101_parcours_v1"
branch_labels = None
depends_on = None

_TABLES = ("playlists", "albums")

_FN_PRIVATE = """
CREATE OR REPLACE FUNCTION keep_taken_down_private() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.taken_down_at IS NOT NULL AND NEW.taken_down_at IS NULL
       AND current_setting('watt.restauration', true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION 'restauration d''un contenu retiré : passer par la restauration admin';
    END IF;
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.visibility := 'private';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.add_column("users", sa.Column("accepted_terms_version", sa.String(20), nullable=True))

    op.execute(_FN_PRIVATE)
    for t in _TABLES:
        op.add_column(t, sa.Column("taken_down_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(
            f"CREATE TRIGGER trg_{t}_keep_taken_down BEFORE INSERT OR UPDATE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION keep_taken_down_private()"
        )

    op.execute("UPDATE analytics_events SET user_id = NULL WHERE user_id IS NOT NULL")
    op.create_check_constraint(
        "ck_analytics_events_sans_compte", "analytics_events", "user_id IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_analytics_events_sans_compte", "analytics_events", type_="check")
    for t in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_keep_taken_down ON {t}")
        op.drop_column(t, "taken_down_at")
    op.execute("DROP FUNCTION IF EXISTS keep_taken_down_private()")
    op.drop_column("users", "accepted_terms_version")
