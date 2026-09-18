"""buckets_invariant_check — CHECK solde non-négatif + invariant de somme (A1.4)

Revision ID: 0088_buckets_invariant_check
Revises: 0087_email_verification
Create Date: 2026-09-18

A1.4 de la doctrine économique. On VERROUILLE en base deux invariants des
sous-soldes de `users` :

  1. ck_users_credits_balance_nonneg : credits_balance >= 0.
     Ce CHECK est déclaré dans le modèle User et la migration 0070 le suppose
     déjà posé (« aucun solde négatif est déjà garanti par
     ck_users_credits_balance_nonneg »), mais il était ABSENT de la base :
     dérive modèle/DB comblée ici.

  2. ck_users_buckets_sum_eq_balance :
     smyles_achetes + smyles_gagnes + smyles_promo = credits_balance.
     (smyles_gagnes_bloque ⊆ smyles_gagnes : ce n'est pas un bucket
     indépendant, il n'entre pas dans la somme.)

ÉTAT RÉEL (vérifié avant de poser — corrige une prémisse erronée d'une version
antérieure de cette migration) : TOUS les chemins d'écriture de prod maintiennent
DÉJÀ cet invariant. Chaque mutation de `credits_balance` met à jour les buckets
dans le MÊME UPDATE : débit acheteur en cascade promo→achetés→gagnés
(unlocks / oeuvre_purchase / packs / pack_purchase / resale / voices /
adn_offers / visual_adn / trades) et crédit vendeur en `smyles_gagnes`
(retirable). Les helpers `credit_bucket` / `debit_with_priority` (credits.py)
font de même. Preuve : la suite des chemins argent passe au vert avec ce CHECK
actif (les incohérences observées auparavant venaient de SEEDS DE TEST qui
posaient credits_balance sans aligner les buckets — corrigés dans la même PR).
Ce CHECK ne CRÉE donc pas l'invariant : il VERROUILLE un acquis, pour empêcher
toute régression future (un nouveau chemin qui oublierait un bucket échouerait
immédiatement au lieu de dériver en silence).

Note réserve plateforme : la commission 20 % sera plus tard créditée à un compte
plateforme (Brique 1, décision Tom). `0074_platform_reserve` est une table euros
séparée (poches payout/tax/refund/cash), HORS de cet invariant. Quand la
commission sera créditée EN SMYLES à un compte `users`, ce crédit devra lui
aussi router vers un bucket (via credit_bucket ou équivalent) pour rester
conforme à ce CHECK. Rien à faire ici.

Sûreté de déploiement (zéro-downtime) pour CHAQUE contrainte :
  1. ADD ... NOT VALID : métadonnée seule, PAS de scan des lignes existantes →
     l'ADD est instantané et ne peut jamais faire échouer le déploiement. Les
     NOUVELLES écritures sont immédiatement contraintes.
  2. On compte les violations pré-existantes (= le canari
     count_bucket_inconsistencies pour l'invariant de somme). Si 0 →
     VALIDATE CONSTRAINT (scan sous SHARE UPDATE EXCLUSIVE, non bloquant pour
     lectures/écritures). Sinon → NOT VALID conservé + log fort (déploiement NON
     bloqué) : réconcilier les lignes legacy puis VALIDATE à la main.

Idempotent : une contrainte de même nom déjà présente n'est pas recréée.
Rollback : drop des deux contraintes (IF EXISTS).
"""
import sqlalchemy as sa
from alembic import op

revision = "0088_buckets_invariant_check"
down_revision = "0087_email_verification"
branch_labels = None
depends_on = None


# (nom, expression du CHECK, SQL de comptage des violations)
_CHECKS = [
    (
        "ck_users_credits_balance_nonneg",
        "credits_balance >= 0",
        "SELECT count(*) FROM users WHERE credits_balance < 0",
    ),
    (
        "ck_users_buckets_sum_eq_balance",
        "smyles_achetes + smyles_gagnes + smyles_promo = credits_balance",
        "SELECT count(*) FROM users "
        "WHERE smyles_achetes + smyles_gagnes + smyles_promo <> credits_balance",
    ),
]


def _constraint_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :n AND conrelid = 'users'::regclass"
            ),
            {"n": name},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()
    for name, expr, violation_sql in _CHECKS:
        if _constraint_exists(conn, name):
            continue
        # 1. Ajout NOT VALID : instantané, ne scanne pas l'existant.
        op.execute(
            f"ALTER TABLE users ADD CONSTRAINT {name} CHECK ({expr}) NOT VALID"
        )
        # 2. Compte des violations pré-existantes (canari pour l'invariant de somme).
        violations = conn.execute(sa.text(violation_sql)).scalar() or 0
        if violations == 0:
            # 3a. Base propre → validation complète.
            op.execute(f"ALTER TABLE users VALIDATE CONSTRAINT {name}")
        else:
            # 3b. Base incohérente (lignes legacy) → NOT VALID conservé, on signale.
            print(
                f"[migration 0088] ATTENTION : {violations} ligne(s) violent "
                f"« {expr} ». Contrainte {name} laissée en NOT VALID (déploiement "
                f"NON bloqué). Réconcilier puis : "
                f"ALTER TABLE users VALIDATE CONSTRAINT {name};"
            )


def downgrade() -> None:
    for name, _expr, _sql in _CHECKS:
        op.execute(f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {name}")
