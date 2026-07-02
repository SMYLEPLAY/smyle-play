"""seed_prix_watt — premiers prix officiels (fin binarité, décision Tom 02/07)

Revision ID: 0079_seed_prix_watt
Revises: 0078_adn_price_bounds
Create Date: 2026-07-02

Positionnement décidé (audit fin-binarité 02/07) :
  - image vendable (prompt + fichier HD)              →  40 Smyles
  - ADN Album (collection visuelle)                   → 300 Smyles
  - ADN Playlist (collection musicale, symétrie)      → 300 Smyles
  - ADN sommet (adns profil musique / visual_adns)    → 300 Smyles

Périmètre : UNIQUEMENT le compte officiel (users.is_official = TRUE, seedé
en 0022 — une seule ligne attendue). Aucun produit d'artiste tiers touché.

Sémantique par table :
  - albums / playlists : remplit adn_price seulement là où il est NULL
    (jamais d'écrasement — un prix déjà posé est une décision).
  - prompts (images) / adns / visual_adns : price_credits est NOT NULL,
    donc toute valeur existante est un placeholder de création → on ALIGNE
    sur le positionnement décidé. Ajustements fins (« 300 ou plus selon
    le nombre d'exemplaires ») : dans l'UI, après coup, par produit.

Idempotent : re-jouer la migration reproduit le même état final.
Rollback : no-op assumé (seed de données, pas de structure) — les anciens
prix placeholder n'ont pas de valeur à restaurer.
"""
from alembic import op


revision = "0079_seed_prix_watt"
down_revision = "0078_adn_price_bounds"
branch_labels = None
depends_on = None

_OFFICIAL = "SELECT id FROM users WHERE is_official = TRUE"


def upgrade() -> None:
    # Images vendables du compte officiel → 40
    op.execute(
        "UPDATE prompts SET price_credits = 40 "
        f"WHERE artist_id IN ({_OFFICIAL}) "
        "AND product_type = 'image' AND price_credits <> 40"
    )
    # ADN de collection : remplir uniquement les prix non posés → 300
    for table in ("albums", "playlists"):
        op.execute(
            f"UPDATE {table} SET adn_price = 300 "
            f"WHERE owner_id IN ({_OFFICIAL}) AND adn_price IS NULL"
        )
    # ADN sommet (profil musique + visuel artiste) → 300
    for table in ("adns", "visual_adns"):
        op.execute(
            f"UPDATE {table} SET price_credits = 300 "
            f"WHERE artist_id IN ({_OFFICIAL}) AND price_credits <> 300"
        )


def downgrade() -> None:
    # Seed de données : pas d'état antérieur à restaurer (cf. docstring).
    pass
