"""0040 — axe de trophées 'trader' + seed des trophées d'échange

Revision ID: 0040_trader_achievements
Revises: 0038_track_tags
Create Date: 2026-06-06

Ajoute la valeur d'enum 'trader' à achievement_axis et seed 6 paliers de
trophées d'échange (1 / 5 / 10 / 25 / 50 / 100 échanges acceptés → Smyles).

Note PostgreSQL : ALTER TYPE ... ADD VALUE ne peut pas être utilisé dans la
même transaction que son ajout → on l'isole dans un autocommit_block()
(même pattern que la migration 0010). Le seed (INSERT) vient ensuite, une
fois la valeur committée. ON CONFLICT (code) DO NOTHING → idempotent.
"""
from alembic import op

revision = "0040_trader_achievements"
down_revision = "0038_track_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Ajout de la valeur d'enum 'trader' (hors transaction — restriction PG).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'trader'"
        )

    # 2. Seed des trophées d'échange (la valeur 'trader' est désormais committée).
    op.execute(
        """
        INSERT INTO achievements
            (id, code, name, description, axis, threshold, credit_reward, display_order)
        VALUES
            (gen_random_uuid(), 'trader_1',   'Premier troc',
             'Premier échange réalisé', 'trader', 1, 5, 10),
            (gen_random_uuid(), 'trader_5',   'Échangeur',
             '5 échanges réalisés', 'trader', 5, 15, 20),
            (gen_random_uuid(), 'trader_10',  'Marchand',
             '10 échanges réalisés', 'trader', 10, 30, 30),
            (gen_random_uuid(), 'trader_25',  'Négociateur',
             '25 échanges réalisés', 'trader', 25, 75, 40),
            (gen_random_uuid(), 'trader_50',  'Trader WATT',
             '50 échanges réalisés', 'trader', 50, 150, 50),
            (gen_random_uuid(), 'trader_100', 'Maître du troc',
             '100 échanges réalisés', 'trader', 100, 300, 60)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    # On retire seulement le seed. La valeur d'enum 'trader' reste (PostgreSQL
    # ne supporte pas proprement le retrait d'une valeur d'enum) — sans impact.
    op.execute(
        "DELETE FROM achievements WHERE code IN "
        "('trader_1','trader_5','trader_10','trader_25','trader_50','trader_100')"
    )
