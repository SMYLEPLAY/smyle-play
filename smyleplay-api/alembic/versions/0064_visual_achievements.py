"""0064 — trophées du Monde Visuel (parité image ↔ son)

Revision ID: 0064_visual_achiev
Revises: 0063_visual_adn
Create Date: 2026-06-18

Ajoute trois axes de trophées au médium IMAGE, à parité avec l'audio :
  - image_creator : nb d'images PUBLIÉES par l'artiste
  - image_seller  : nb d'exemplaires d'images vendus
  - visual_dna    : ADN visuel publié (signature visuelle, 0/1)

Même pattern que 0040 (trader) : ALTER TYPE ... ADD VALUE ne peut pas être
utilisé dans la même transaction que son usage → on isole les ajouts d'enum
dans un autocommit_block(). Le seed (INSERT) vient ensuite, une fois les
valeurs committées. ON CONFLICT (code) DO NOTHING → idempotent et re-runnable.

Les valeurs de Smyles mirrorent les paliers audio équivalents (axe artist /
trader) pour ne pas créer de déséquilibre économique entre les deux médiums.
"""
from alembic import op

revision = "0064_visual_achiev"
down_revision = "0063_visual_adn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Ajout des valeurs d'enum (hors transaction — restriction PostgreSQL).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'image_creator'"
        )
        op.execute(
            "ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'image_seller'"
        )
        op.execute(
            "ALTER TYPE achievement_axis ADD VALUE IF NOT EXISTS 'visual_dna'"
        )

    # 2. Seed des trophées image (valeurs d'enum désormais committées).
    #    - image_creator : 1 / 5 / 20 images publiées
    #    - image_seller  : 1 / 10 / 50 ventes d'images (mirror paliers artist)
    #    - visual_dna    : 1 (ADN visuel publié)
    op.execute(
        """
        INSERT INTO achievements
            (id, code, name, description, axis, threshold, credit_reward, display_order)
        VALUES
            (gen_random_uuid(), 'image_first_publish', 'Premier pixel',
             'Première image publiée', 'image_creator', 1, 5, 10),
            (gen_random_uuid(), 'image_5_publish', 'Illustrateur',
             '5 images publiées', 'image_creator', 5, 15, 20),
            (gen_random_uuid(), 'image_20_publish', 'Studio visuel',
             '20 images publiées', 'image_creator', 20, 50, 30),
            (gen_random_uuid(), 'image_first_sale', 'Première toile vendue',
             'Première image vendue', 'image_seller', 1, 5, 10),
            (gen_random_uuid(), 'image_10_sales', 'Galeriste',
             '10 images vendues', 'image_seller', 10, 25, 20),
            (gen_random_uuid(), 'image_50_sales', 'Maison de vente',
             '50 images vendues', 'image_seller', 50, 100, 30),
            (gen_random_uuid(), 'visual_dna_published', 'Signature visuelle',
             'ADN visuel publié', 'visual_dna', 1, 5, 10)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    # On retire seulement le seed. Les valeurs d'enum restent (PostgreSQL ne
    # supporte pas proprement le retrait d'une valeur d'enum) — sans impact.
    op.execute(
        "DELETE FROM achievements WHERE code IN "
        "('image_first_publish','image_5_publish','image_20_publish',"
        "'image_first_sale','image_10_sales','image_50_sales',"
        "'visual_dna_published')"
    )
