"""adn_price_bounds — bornes DB sur albums.adn_price et playlists.adn_price

Revision ID: 0078_adn_price_bounds
Revises: 0077_prompt_universe
Create Date: 2026-07-02

Trou relevé par l'audit fin-binarité (02/07) : `prompts.price_credits` a un
CHECK min (0001/0033), `adns` et `visual_adns` sont bornés 30..500, mais
`albums.adn_price` et `playlists.adn_price` n'ont AUCUNE contrainte DB — un
prix négatif ou astronomique passait si un client contournait Pydantic.

Bornes choisies : 1..100000, MIROIR EXACT du schéma Pydantic playlist
(`ge=1, le=100_000`, schemas/playlist.py). C'est une borne DÉFENSIVE
(anti-corruption), pas une borne business — le positionnement (300 par
défaut, ajustable selon exemplaires) vit en 0079 et dans l'UI. On ne
reprend PAS 30..500 (bornes adns/visual_adns) pour ne pas contraindre les
ADN de collection dont le prix libre dépendra du nombre d'exemplaires.

Défensif : on neutralise (NULL) toute ligne hors bornes AVANT la pose du
CHECK — sinon ALTER TABLE échoue au déploiement si une ligne corrompue
existe déjà en prod. NULL = « pas de prix posé », l'état sain par défaut.

Rollback : drop des deux CHECK.
"""
from alembic import op


revision = "0078_adn_price_bounds"
down_revision = "0077_prompt_universe"
branch_labels = None
depends_on = None

_BOUNDS = "(adn_price >= 1 AND adn_price <= 100000)"


def upgrade() -> None:
    for table in ("albums", "playlists"):
        op.execute(
            f"UPDATE {table} SET adn_price = NULL "
            f"WHERE adn_price IS NOT NULL AND NOT {_BOUNDS}"
        )
        op.create_check_constraint(
            f"ck_{table}_adn_price_bounds",
            table,
            f"adn_price IS NULL OR {_BOUNDS}",
        )


def downgrade() -> None:
    for table in ("albums", "playlists"):
        op.drop_constraint(f"ck_{table}_adn_price_bounds", table, type_="check")
