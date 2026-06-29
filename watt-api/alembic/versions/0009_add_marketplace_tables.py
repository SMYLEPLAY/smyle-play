"""add marketplace tables (Adn, Prompt, OwnedAdn, UnlockedPrompt, Achievements) + brand_color

Revision ID: 0009_add_marketplace
Revises: 0008_add_transactions
Create Date: 2026-04-18

Phase 9.1 — Couche données marketplace:
  - users.brand_color (hex #RRGGBB, nullable)
  - tighten transactions: credits_amount > 0, splits cohérents (<=)
  - tables adns, prompts, owned_adns, unlocked_prompts
  - tables achievements + user_achievements
  - seed achievements idempotent (ON CONFLICT DO NOTHING)

IMPORTANT:
  - Le seed des achievements est idempotent: re-runnable, et permet
    d'ajouter de nouveaux badges via migrations futures sans casser
    les déblocages existants.
  - Le check transactions.artist_revenue + platform_fee <= credits_amount
    est volontairement <= (pas =) pour tolérer GRANT/BONUS/CREDIT_PURCHASE
    où le split n'a pas de sens (montant from outside). La logique
    marketplace côté code enforce strictement = pour UNLOCK.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0009_add_marketplace"
# Pointe sur la dernière migration existante du projet (Phase 7+8 sync).
# Avant Phase 9, le projet a 3 migrations auto-générées :
#   4856b7981481_init  →  34003a80bc2b_init  →  b2fe0db4906d_phase_7_and_8_sync
down_revision = "b2fe0db4906d"
branch_labels = None
depends_on = None


achievement_axis = postgresql.ENUM(
    "buyer",
    "fan",
    "artist",
    name="achievement_axis",
    create_type=False,
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. users.brand_color
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("brand_color", sa.String(length=7), nullable=True),
    )
    op.create_check_constraint(
        "ck_users_brand_color_hex",
        "users",
        "brand_color IS NULL OR brand_color ~ '^#[0-9A-Fa-f]{6}$'",
    )

    # ------------------------------------------------------------------
    # 2. transactions: tighten constraints
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_transactions_credits_amount_nonneg",
        "transactions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transactions_credits_amount_positive",
        "transactions",
        "credits_amount > 0",
    )
    op.create_check_constraint(
        "ck_transactions_split_within_amount",
        "transactions",
        "artist_revenue + platform_fee <= credits_amount",
    )

    # ------------------------------------------------------------------
    # 3. ENUM achievement_axis
    # ------------------------------------------------------------------
    achievement_axis.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 4. Table adns
    # ------------------------------------------------------------------
    op.create_table(
        "adns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("usage_guide", sa.Text, nullable=True),
        sa.Column("example_outputs", sa.Text, nullable=True),
        sa.Column("price_credits", sa.Integer, nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_updated_by_artist_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint("artist_id", name="uq_adns_artist_id"),
        sa.CheckConstraint(
            "price_credits >= 30 AND price_credits <= 500",
            name="ck_adns_price_credits_range",
        ),
        sa.CheckConstraint(
            "char_length(description) >= 200",
            name="ck_adns_description_min_length",
        ),
    )
    op.create_index("ix_adns_artist_id", "adns", ["artist_id"])

    # ------------------------------------------------------------------
    # 5. Table prompts
    # ------------------------------------------------------------------
    op.create_table(
        "prompts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("price_credits", sa.Integer, nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "pack_eligible",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "price_credits >= 3",
            name="ck_prompts_price_credits_min",
        ),
        sa.CheckConstraint(
            "char_length(title) >= 5",
            name="ck_prompts_title_min_length",
        ),
        sa.CheckConstraint(
            "char_length(prompt_text) >= 50",
            name="ck_prompts_prompt_text_min_length",
        ),
    )
    op.create_index("ix_prompts_artist_id", "prompts", ["artist_id"])
    op.create_index("ix_prompts_is_published", "prompts", ["is_published"])

    # ------------------------------------------------------------------
    # 6. Table owned_adns (jointure)
    # ------------------------------------------------------------------
    op.create_table(
        "owned_adns",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "adn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("adns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "adn_id", name="pk_owned_adns"),
    )
    op.create_index("ix_owned_adns_user_id", "owned_adns", ["user_id"])
    op.create_index("ix_owned_adns_adn_id", "owned_adns", ["adn_id"])

    # ------------------------------------------------------------------
    # 7. Table unlocked_prompts (avec UUID propre pour P2P futur)
    # ------------------------------------------------------------------
    op.create_table(
        "unlocked_prompts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "current_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "original_artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "current_owner_id",
            "prompt_id",
            name="uq_unlocked_prompts_owner_prompt",
        ),
    )
    op.create_index(
        "ix_unlocked_prompts_current_owner_id",
        "unlocked_prompts",
        ["current_owner_id"],
    )
    op.create_index(
        "ix_unlocked_prompts_prompt_id",
        "unlocked_prompts",
        ["prompt_id"],
    )
    op.create_index(
        "ix_unlocked_prompts_original_artist_id",
        "unlocked_prompts",
        ["original_artist_id"],
    )

    # ------------------------------------------------------------------
    # 8. Table achievements (catalogue statique)
    # ------------------------------------------------------------------
    op.create_table(
        "achievements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("axis", achievement_axis, nullable=False),
        sa.Column("threshold", sa.Integer, nullable=False),
        sa.Column(
            "credit_reward",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "display_order",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint("code", name="uq_achievements_code"),
        sa.CheckConstraint(
            "threshold > 0",
            name="ck_achievements_threshold_positive",
        ),
        sa.CheckConstraint(
            "credit_reward >= 0",
            name="ck_achievements_credit_reward_nonneg",
        ),
    )
    op.create_index("ix_achievements_axis", "achievements", ["axis"])

    # ------------------------------------------------------------------
    # 9. Table user_achievements
    # ------------------------------------------------------------------
    op.create_table(
        "user_achievements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "achievement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("achievements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "bonus_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "user_id",
            "achievement_id",
            name="uq_user_achievements_user_ach",
        ),
    )
    op.create_index(
        "ix_user_achievements_user_id", "user_achievements", ["user_id"]
    )
    op.create_index(
        "ix_user_achievements_achievement_id",
        "user_achievements",
        ["achievement_id"],
    )

    # ------------------------------------------------------------------
    # 10. Seed achievements (idempotent via ON CONFLICT)
    # ------------------------------------------------------------------
    # Codes stables (slugs). Re-runnable sans erreur. Pour ajouter des
    # achievements futurs : nouvelle migration avec INSERT ... ON CONFLICT.
    op.execute(
        """
        INSERT INTO achievements
            (id, code, name, description, axis, threshold, credit_reward, display_order)
        VALUES
            (gen_random_uuid(), 'buyer_first_unlock', 'Curieux',
             'Premier prompt débloqué', 'buyer', 1, 0, 10),
            (gen_random_uuid(), 'buyer_10_prompts', 'Mélomane',
             '10 prompts débloqués', 'buyer', 10, 5, 20),
            (gen_random_uuid(), 'buyer_50_prompts', 'Collectionneur',
             '50 prompts débloqués', 'buyer', 50, 25, 30),
            (gen_random_uuid(), 'buyer_100_prompts', 'Connaisseur',
             '100 prompts débloqués', 'buyer', 100, 50, 40),
            (gen_random_uuid(), 'buyer_250_prompts', 'Encyclopédie',
             '250 prompts débloqués', 'buyer', 250, 100, 50),
            (gen_random_uuid(), 'fan_first_adn', 'Croyant',
             'Première ADN possédée', 'fan', 1, 5, 10),
            (gen_random_uuid(), 'fan_3_adns', 'Mécène',
             '3 ADN possédées', 'fan', 3, 20, 20),
            (gen_random_uuid(), 'fan_5_adns', 'Curateur',
             '5 ADN possédées', 'fan', 5, 50, 30),
            (gen_random_uuid(), 'fan_10_adns', 'Cercle d''or',
             '10 ADN possédées', 'fan', 10, 150, 40),
            (gen_random_uuid(), 'artist_first_credit', 'Premier souffle',
             'Première vente effectuée', 'artist', 1, 5, 10),
            (gen_random_uuid(), 'artist_10_credits', 'Voix qui porte',
             '10 crédits gagnés', 'artist', 10, 10, 20),
            (gen_random_uuid(), 'artist_100_credits', 'Pro',
             '100 crédits gagnés', 'artist', 100, 50, 30),
            (gen_random_uuid(), 'artist_1000_credits', 'Établi',
             '1000 crédits gagnés', 'artist', 1000, 250, 40)
        ON CONFLICT (code) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_achievements_achievement_id", table_name="user_achievements")
    op.drop_index("ix_user_achievements_user_id", table_name="user_achievements")
    op.drop_table("user_achievements")

    op.drop_index("ix_achievements_axis", table_name="achievements")
    op.drop_table("achievements")

    achievement_axis.drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_unlocked_prompts_original_artist_id", table_name="unlocked_prompts")
    op.drop_index("ix_unlocked_prompts_prompt_id", table_name="unlocked_prompts")
    op.drop_index("ix_unlocked_prompts_current_owner_id", table_name="unlocked_prompts")
    op.drop_table("unlocked_prompts")

    op.drop_index("ix_owned_adns_adn_id", table_name="owned_adns")
    op.drop_index("ix_owned_adns_user_id", table_name="owned_adns")
    op.drop_table("owned_adns")

    op.drop_index("ix_prompts_is_published", table_name="prompts")
    op.drop_index("ix_prompts_artist_id", table_name="prompts")
    op.drop_table("prompts")

    op.drop_index("ix_adns_artist_id", table_name="adns")
    op.drop_table("adns")

    op.drop_constraint(
        "ck_transactions_split_within_amount",
        "transactions",
        type_="check",
    )
    op.drop_constraint(
        "ck_transactions_credits_amount_positive",
        "transactions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transactions_credits_amount_nonneg",
        "transactions",
        "credits_amount >= 0",
    )

    op.drop_constraint(
        "ck_users_brand_color_hex",
        "users",
        type_="check",
    )
    op.drop_column("users", "brand_color")
