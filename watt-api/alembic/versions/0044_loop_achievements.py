"""0044 — trophées de la boucle d'engagement (referrer / streak / collector)

Revision ID: 0044_loop_achievements
Revises: 0043_streak
Create Date: 2026-06-07

Ajoute 3 axes de trophées branchés sur la boucle (mécaniques 1-3) et seede
leurs paliers (récompenses one-time en Smyles) :
  - referrer  : 1 / 5 / 10 / 25 filleuls validés
  - streak    : 7 / 30 / 100 jours consécutifs
  - collector : 1 / 10 / 50 / 100 packs mystère ouverts

Même pattern que 0040 (axe 'trader') : ALTER TYPE ... ADD VALUE isolé dans un
autocommit_block (restriction PostgreSQL), puis seed en INSERT ... ON CONFLICT
DO NOTHING (idempotent).
"""
from alembic import op

revision = "0044_loop_achievements"
down_revision = "0043_streak"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Nouvelles valeurs d'enum (hors transaction — restriction PG).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'referrer'")
        op.execute("ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'streak'")
        op.execute("ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'collector'")

    # 2. Seed des paliers (valeurs d'enum désormais committées).
    op.execute(
        """
        INSERT INTO achievements
            (id, code, name, description, axis, threshold, credit_reward, display_order)
        VALUES
            -- Parrainage
            (gen_random_uuid(), 'referrer_1',   'Premier filleul',
             '1 filleul validé', 'referrer', 1, 5, 70),
            (gen_random_uuid(), 'referrer_5',   'Recruteur',
             '5 filleuls validés', 'referrer', 5, 15, 71),
            (gen_random_uuid(), 'referrer_10',  'Ambassadeur',
             '10 filleuls validés', 'referrer', 10, 30, 72),
            (gen_random_uuid(), 'referrer_25',  'Tête de réseau',
             '25 filleuls validés', 'referrer', 25, 75, 73),
            -- Streak
            (gen_random_uuid(), 'streak_7',     'Semaine pleine',
             '7 jours de connexion consécutifs', 'streak', 7, 10, 80),
            (gen_random_uuid(), 'streak_30',    'Habitué',
             '30 jours de connexion consécutifs', 'streak', 30, 40, 81),
            (gen_random_uuid(), 'streak_100',   'Inarrêtable',
             '100 jours de connexion consécutifs', 'streak', 100, 150, 82),
            -- Packs
            (gen_random_uuid(), 'collector_1',   'Premier pack',
             '1 pack mystère ouvert', 'collector', 1, 3, 90),
            (gen_random_uuid(), 'collector_10',  'Chineur',
             '10 packs mystère ouverts', 'collector', 10, 15, 91),
            (gen_random_uuid(), 'collector_50',  'Collectionneur',
             '50 packs mystère ouverts', 'collector', 50, 50, 92),
            (gen_random_uuid(), 'collector_100', 'Maître collectionneur',
             '100 packs mystère ouverts', 'collector', 100, 120, 93)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    # On retire seulement le seed. Les valeurs d'enum restent (PostgreSQL ne
    # supporte pas proprement le retrait d'une valeur d'enum) — sans impact.
    op.execute(
        "DELETE FROM achievements WHERE code IN ("
        "'referrer_1','referrer_5','referrer_10','referrer_25',"
        "'streak_7','streak_30','streak_100',"
        "'collector_1','collector_10','collector_50','collector_100')"
    )
