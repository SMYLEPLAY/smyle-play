"""reconcile_buckets — réconcilie les sous-soldes avec le solde (A1.4)

Revision ID: 0072_reconcile_buckets
Revises: 0071_smyle_buckets
Create Date: 2026-06-29

A1.4 du moteur économique. Après le câblage de TOUS les chemins crédit/débit
(A1.3a/b/c), tous les flux maintiennent désormais
smyles_achetes + smyles_gagnes + smyles_promo == credits_balance.

Cette migration réconcilie les lignes existantes qui auraient dérivé pendant la
transition (ex. un débit effectué avant que A1.3c soit déployé, qui réduisait le
solde sans toucher les buckets). On force la cohérence en préservant promo et
gagnés autant que possible, le reste tombant dans achetés (non encaissable,
conservateur — ne surestime jamais la dette encaissable) :

  1. promo  ← min(promo, solde)
  2. gagnés ← min(gagnés, solde - promo)
  3. achetés ← solde - promo - gagnés   (= reste, toujours >= 0)

⇒ somme == solde pour toutes les lignes, sans violer les CHECK >= 0.

NB — PAS de contrainte CHECK d'invariant ajoutée ici, volontairement :
l'invariant est garanti PAR LE CODE (tous les flux passent par les helpers /
SQL bucket-aware) et SURVEILLÉ par le canari `count_bucket_inconsistencies`
(A1.2). Un CHECK DB rigide casserait des fixtures de test (qui posent un solde
sans buckets) et le test qui crée volontairement une incohérence pour vérifier
le détecteur. Discipline de code + réconciliation + monitoring = suffisant et
non bloquant.

Rollback : aucun (réconciliation idempotente, pas de schéma modifié).
"""
from alembic import op


revision = "0072_reconcile_buckets"
down_revision = "0071_smyle_buckets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET smyles_promo = LEAST(smyles_promo, credits_balance)")
    op.execute(
        "UPDATE users SET smyles_gagnes = LEAST(smyles_gagnes, credits_balance - smyles_promo)"
    )
    op.execute(
        "UPDATE users SET smyles_achetes = credits_balance - smyles_promo - smyles_gagnes"
    )


def downgrade() -> None:
    # Réconciliation idempotente : rien à défaire.
    pass
