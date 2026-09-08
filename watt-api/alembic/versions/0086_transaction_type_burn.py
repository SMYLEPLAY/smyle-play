"""transaction_type: ajout de la valeur 'burn' (destruction de Smyles)

Revision ID: 0086_transaction_type_burn
Revises: 0085_users_is_admin
Create Date: 2026-09-08

D6 — Le troc (`PATCH /trades/offers/{id}/accept`) prélève des frais d'échange
et les BRÛLE : les soldes des deux parties sont débités, mais aucune ligne
n'était écrite dans `transactions`. Résultat : la somme des écritures ne
réconcilie plus avec la variation des soldes dès qu'un échange est accepté —
c'était le seul chemin applicatif qui détruisait des Smyles sans trace.

Aucune valeur existante de l'enum ne décrit une DESTRUCTION :
  - unlock / resale  : achat avec split (artiste + plateforme), conservatif ;
  - credit_purchase  : entrée d'argent ;
  - earning / bonus / grant : crédits ;
  - refund           : contre-passation d'un débit, rend les Smyles.
D'où une nouvelle valeur 'burn' : montant retiré de la circulation, sans
bénéficiaire (ni artiste, ni vendeur).

Migration ADDITIVE et rétro-compatible :
  - `ALTER TYPE ... ADD VALUE IF NOT EXISTS` uniquement ; aucune table, aucune
    contrainte, aucune donnée touchée ;
  - le CHECK `ck_transactions_split_within_amount` n'a PAS besoin d'être
    récrit : 'burn' tombe dans la branche `type NOT IN ('unlock','resale')`
    → `artist_revenue + platform_fee <= credits_amount` (0 + 0 <= montant) ;
  - l'ancien code tourne sans problème sur la nouvelle base (valeur dormante
    tant que le code applicatif n'écrit pas de BURN).

Note PostgreSQL : `ALTER TYPE ... ADD VALUE` ne peut pas être exécuté dans une
transaction qui référence ensuite la nouvelle valeur → autocommit_block, comme
en 0010 pour 'resale'.

Downgrade : PostgreSQL n'a pas de `DROP VALUE` sur un enum. Le downgrade est
donc un no-op documenté (la valeur reste, inoffensive tant qu'aucune ligne ne
l'utilise).
"""
from alembic import op


revision = "0086_transaction_type_burn"
down_revision = "0085_users_is_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'burn'"
        )


def downgrade() -> None:
    # Impossible de retirer une valeur d'un ENUM PostgreSQL (pas de DROP
    # VALUE). No-op volontaire : 'burn' reste dans l'enum.
    pass
