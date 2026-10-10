"""emails_minuscules — emails en minuscules + unicité insensible à la casse

Revision ID: 0103_emails_minuscules
Revises: 0102_lot_d_conformite
Create Date: 2026-10-10

Lot D. « Marie@Exemple.fr » et « marie@exemple.fr » pouvaient être deux
comptes différents (l'index unique était sensible à la casse), et la
connexion échouait si la casse tapée différait de celle de l'inscription.

1. CONTRÔLE : s'il existe deux comptes dont l'email ne diffère que par la
   casse (ou par des espaces autour), la migration ÉCHOUE avec un message
   clair et ne touche à rien. Elle ne fusionne jamais de comptes : c'est une
   décision humaine (quel compte garder, que faire des Smyles et des achats).
   Le déploiement s'arrête alors et l'ancienne version reste en ligne.

   Requête de contrôle à lancer à l'avance :
     SELECT lower(btrim(email)) AS email, count(*) AS comptes,
            string_agg(id::text, ', ') AS identifiants
     FROM users GROUP BY lower(btrim(email)) HAVING count(*) > 1;

2. Tous les emails sont ramenés en minuscules, sans espaces autour.
3. Index unique `ux_users_email_lower` sur lower(email).

Le jeton de connexion porte l'email tel qu'il était : le code compare
désormais en minuscules (services/users.py::get_user_by_email), donc les
sessions déjà ouvertes restent valides. La connexion marche avec n'importe
quelle casse.

Rollback : suppression de l'index (la casse d'origine n'est pas restaurée).
"""
from alembic import op

revision = "0103_emails_minuscules"
down_revision = "0102_lot_d_conformite"
branch_labels = None
depends_on = None

_CONTROLE = """
DO $$
DECLARE
    doublons text;
BEGIN
    SELECT string_agg(e || ' (' || n || ' comptes)', '; ')
      INTO doublons
      FROM (SELECT lower(btrim(email)) AS e, count(*) AS n
              FROM users GROUP BY lower(btrim(email)) HAVING count(*) > 1) d;
    IF doublons IS NOT NULL THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Migration 0103 arrêtée : des comptes ont le même email à la casse près. '
                      || 'Rien n''a été modifié. Emails concernés : ' || doublons,
            HINT = 'Décider à la main quel compte garder (fusion ou changement d''email), puis relancer le déploiement.';
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(_CONTROLE)
    op.execute(
        "UPDATE users SET email = lower(btrim(email)) WHERE email <> lower(btrim(email))"
    )
    op.execute("CREATE UNIQUE INDEX ux_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_email_lower")
