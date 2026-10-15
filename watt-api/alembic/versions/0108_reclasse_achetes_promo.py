"""reclasse_achetes_promo — Smyles « achetés » et « gagnés » sans euro → promo

Revision ID: 0108_reclasse_achetes_promo
Revises: 0107_codes_pionnier
Create Date: 2026-10-15

MIGRATION DE DONNÉES uniquement, aucun changement de schéma. Même logique
que 0099 (pricing v2), étendue aux Smyles « achetés ».

POURQUOI. Aucun euro réel n'est encore entré sur la plateforme : Stripe n'a
jamais fonctionné qu'avec des clés de TEST. Pourtant, des soldes de la bêta
sont rangés en « achetés » (solde initial, anciens crédits, multiplication
×10 de 0100, achats de test). Quand un compte dépense des Smyles « achetés »,
le vendeur reçoit des Smyles « gagnés », RETIRABLES plus tard en euros. Deux
comptes d'une même personne pouvaient donc fabriquer une dette en euros sans
aucun paiement derrière. Depuis 0099, les ventes payées avec ces « achetés »
ont aussi recréé des « gagnés ».

CE QUI EST FAIT, pour chaque compte SAUF la trésorerie (`is_treasury`) :
    smyles_promo         += smyles_achetes + smyles_gagnes
    smyles_promo_gagnes  += smyles_gagnes      (gagnés non retirables)
    smyles_achetes        = 0
    smyles_gagnes         = 0
    smyles_gagnes_bloque  = 0
    credits_balance         INCHANGÉ (le CHECK de somme reste vrai)
Tout reste 100 % dépensable sur WATT ; rien n'est retirable.

À partir du lancement des paiements réels (clé live), les achats par carte
iront à nouveau en « achetés ». Les achats faits avec une clé de TEST vont
désormais en « promo » (app/services/stripe_payments.py).

TRACE dans `admin_journal` (état AVANT, une ligne par compte + synthèse).
Idempotent. DOWNGRADE = NO-OP volontaire (on ne recrée jamais de dette en
euros par un rollback).
"""
from alembic import op

revision = "0108_reclasse_achetes_promo"
down_revision = "0107_codes_pionnier"
branch_labels = None
depends_on = None

ACTION = "lancement_reclassement_achetes"
MOTIF = (
    "Lancement (15/10/2026) : Smyles achetés et gagnés de la bêta reclassés en "
    "promo (aucun paiement réel, non adossés à des euros)."
)

_CIBLE = ("NOT is_treasury AND (smyles_achetes > 0 OR smyles_gagnes > 0 "
          "OR smyles_gagnes_bloque > 0)")

SQL_JOURNAL_SYNTHESE = (
    "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
    "SELECT gen_random_uuid(), NULL, :action, 'plateforme', '0108', :motif, "
    "       jsonb_build_object('comptes', count(*), "
    "                          'achetes_reclasses', COALESCE(sum(smyles_achetes), 0), "
    "                          'gagnes_reclasses', COALESCE(sum(smyles_gagnes), 0)) "
    "FROM users WHERE " + _CIBLE + " HAVING count(*) > 0"
)

SQL_JOURNAL_COMPTES = (
    "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
    "SELECT gen_random_uuid(), NULL, :action, 'user', CAST(id AS text), :motif, "
    "       jsonb_build_object('avant', jsonb_build_object("
    "           'smyles_achetes', smyles_achetes, "
    "           'smyles_gagnes', smyles_gagnes, "
    "           'smyles_gagnes_bloque', smyles_gagnes_bloque, "
    "           'smyles_promo', smyles_promo, "
    "           'smyles_promo_gagnes', smyles_promo_gagnes, "
    "           'credits_balance', credits_balance)) "
    "FROM users WHERE " + _CIBLE
)

SQL_RECLASSER = (
    "UPDATE users SET "
    "  smyles_promo = smyles_promo + smyles_achetes + smyles_gagnes, "
    "  smyles_promo_gagnes = smyles_promo_gagnes + smyles_gagnes, "
    "  smyles_achetes = 0, "
    "  smyles_gagnes = 0, "
    "  smyles_gagnes_bloque = 0 "
    "WHERE " + _CIBLE
)


def _params_sql(sql: str) -> str:
    return (
        sql.replace(":action", "'" + ACTION + "'")
        .replace(":motif", "'" + MOTIF.replace("'", "''") + "'")
    )


def upgrade() -> None:
    op.execute(_params_sql(SQL_JOURNAL_SYNTHESE))
    op.execute(_params_sql(SQL_JOURNAL_COMPTES))
    op.execute(SQL_RECLASSER)


def downgrade() -> None:
    pass
