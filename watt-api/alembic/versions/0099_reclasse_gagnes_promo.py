"""reclasse_gagnes_promo — pricing v2 : Smyles « gagnés » de la bêta → promo

Revision ID: 0099_reclasse_gagnes_promo
Revises: 0098_admin_restauration
Create Date: 2026-09-30

Pricing v2 (validé le 30/09/2026, option A). MIGRATION DE DONNÉES uniquement,
aucun changement de schéma.

POURQUOI. Aucun argent réel n'est encore entré sur la plateforme : Stripe n'a
jamais fonctionné en paiement réel (clés de test uniquement, cf. 0098
`stripe_payments.mode_test`). Les Smyles « gagnés » (bucket retirable) accumulés
pendant la bêta viennent donc de ventes payées avec des Smyles offerts ou de
test : ils ne sont adossés à AUCUN euro. Les laisser retirables créerait une
dette en euros sans contrepartie. On les reclasse en « promo » : ils restent
100 % dépensables sur WATT, mais ne se retirent pas.

CE QUI EST FAIT, pour chaque compte SAUF le compte trésorerie (`is_treasury`) :
    smyles_promo         += smyles_gagnes
    smyles_promo_gagnes  += smyles_gagnes   (sous-total « gagnés — non
                                             retirables », ⊆ smyles_promo)
    smyles_gagnes         = 0
    smyles_gagnes_bloque  = 0               (⊆ smyles_gagnes : la part gelée
                                             n'a plus d'objet une fois les
                                             gagnés à 0)
    credits_balance         INCHANGÉ        → le CHECK de somme
                                             (achetes + gagnes + promo =
                                             credits_balance) reste vrai.
Contraintes vérifiées : tous les buckets restent >= 0 ; smyles_promo_gagnes
reste <= smyles_promo (on ajoute la même quantité des deux côtés).

TRACE. Le registre `transactions` n'a pas de type « reclassement » (ses types
sont des mouvements de solde ; en ajouter un ferait apparaître ces lignes comme
des crédits dans les tableaux de bord). La trace va donc dans `admin_journal`
(0098) : une ligne par compte touché (état AVANT : gagnés, bloqués, promo,
promo_gagnes) + une ligne de synthèse (nombre de comptes, total reclassé).
`admin_id` = NULL (action système, pas un admin).

Idempotent : un second passage ne trouve plus aucun gagné → ne fait rien.

DOWNGRADE = NO-OP VOLONTAIRE. Remettre des Smyles en retirable, c'est recréer
une dette en euros : cela ne doit jamais arriver par un simple rollback de
code. Si Tom le décide un jour, l'état d'avant est dans `admin_journal`
(action 'pricing_v2_reclassement', details->'avant') et peut être rejoué à la
main, compte par compte.
"""
from alembic import op

revision = "0099_reclasse_gagnes_promo"
down_revision = "0098_admin_restauration"
branch_labels = None
depends_on = None

ACTION = "pricing_v2_reclassement"
MOTIF = (
    "Pricing v2 (30/09/2026) : Smyles gagnés de la bêta reclassés en promo "
    "(aucun argent réel entré, non adossés)."
)

# Comptes concernés : tout sauf la trésorerie, avec des gagnés (ou une part gelée).
_CIBLE = "NOT is_treasury AND (smyles_gagnes > 0 OR smyles_gagnes_bloque > 0)"

# 1. Synthèse (avant la mise à jour, pour compter ce qui va bouger). Rien
#    n'est écrit s'il n'y a aucun compte à reclasser (base neuve, second passage).
SQL_JOURNAL_SYNTHESE = (
    "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
    "SELECT gen_random_uuid(), NULL, :action, 'plateforme', '0099', :motif, "
    "       jsonb_build_object('comptes', count(*), "
    "                          'smyles_reclasses', COALESCE(sum(smyles_gagnes), 0), "
    "                          'smyles_bloques_liberes', COALESCE(sum(smyles_gagnes_bloque), 0)) "
    "FROM users WHERE " + _CIBLE + " HAVING count(*) > 0"
)

# 2. Une ligne par compte, avec l'état AVANT (permet un rejeu manuel).
SQL_JOURNAL_COMPTES = (
    "INSERT INTO admin_journal (id, admin_id, action, cible_type, cible_id, motif, details) "
    "SELECT gen_random_uuid(), NULL, :action, 'user', CAST(id AS text), :motif, "
    "       jsonb_build_object('avant', jsonb_build_object("
    "           'smyles_gagnes', smyles_gagnes, "
    "           'smyles_gagnes_bloque', smyles_gagnes_bloque, "
    "           'smyles_promo', smyles_promo, "
    "           'smyles_promo_gagnes', smyles_promo_gagnes, "
    "           'credits_balance', credits_balance)) "
    "FROM users WHERE " + _CIBLE
)

# 3. Le reclassement lui-même (une seule instruction : chaque ligne passe d'un
#    état cohérent à un état cohérent, le CHECK de somme est évalué sur la
#    ligne finale).
SQL_RECLASSER = (
    "UPDATE users SET "
    "  smyles_promo = smyles_promo + smyles_gagnes, "
    "  smyles_promo_gagnes = smyles_promo_gagnes + smyles_gagnes, "
    "  smyles_gagnes = 0, "
    "  smyles_gagnes_bloque = 0 "
    "WHERE " + _CIBLE
)


def _params_sql(sql: str) -> str:
    """Remplace les paramètres nommés par des littéraux sûrs (constantes du
    module, jamais de données utilisateur) — op.execute n'a pas de binds."""
    return (
        sql.replace(":action", "'" + ACTION + "'")
        .replace(":motif", "'" + MOTIF.replace("'", "''") + "'")
    )


def upgrade() -> None:
    op.execute(_params_sql(SQL_JOURNAL_SYNTHESE))
    op.execute(_params_sql(SQL_JOURNAL_COMPTES))
    op.execute(SQL_RECLASSER)


def downgrade() -> None:
    # No-op volontaire (voir la docstring) : on ne recrée jamais de dette en
    # euros par un rollback. L'état d'avant est conservé dans admin_journal.
    pass
