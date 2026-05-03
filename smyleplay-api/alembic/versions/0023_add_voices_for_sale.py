"""ajout table voices_for_sale + owned_voices (P1-F9 backend)

Revision ID: 0023_add_voices_for_sale
Revises: 0022_seed_smyle_official
Create Date: 2026-05-03

Contexte produit — Étape 4 du chantier `2026-04-29_chantier_continuation` :

  Le bloc 1c "Vendre une voix" du dashboard est déjà livré en aperçu visuel
  (localStorage). Cette migration ouvre le backend pour persister vraiment
  les voix mises en vente et l'historique d'achats.

  Modèle produit (recette B validée 2026-04-22, voir BACKLOG_SHIP P1-F9) :
    - L'artiste vend un sample audio a cappella (pas un clone IA)
    - Métadonnées : nom, style, genres compatibles, licence, prix
    - L'acheteur télécharge le sample via une URL R2 signée

  Choix de design :
    • Table `voices_for_sale` (et pas `voices` tout court) parce que la
      sémantique métier est "voix mise en vente", pas "asset voix" générique.
      Si plus tard on veut un catalogue de voix non-monétisées (showcase),
      on créera une table dédiée — pas de mélange.
    • Pas de UNIQUE(artist_id) — un beatmaker peut avoir plusieurs voix
      à vendre (différents styles, hommes/femmes, etc.). Contraint plus
      tard si abus observé.
    • `genres` en JSONB array : volume modéré (max 10 chips), recherche par
      genre se fait côté requête. Évite une junction table `voice_genres`.
    • `license` en VARCHAR(16) avec CHECK constraint plutôt qu'un ENUM
      Postgres : ajouter une licence future = ALTER CHECK (instantané),
      versus DROP/CREATE TYPE pour un ENUM (downtime).
    • Prix encadré 50 ≤ price_credits ≤ 5000 (CHECK constraint) — fourchette
      validée par Tom 2026-04-22, alignée sur fiche dashboard 1c.
    • `is_published` default false : la création de l'objet ≠ publication.
      Un brouillon reste invisible jusqu'au toggle.
    • `sample_url` VARCHAR(500) nullable=False : on REFUSE de créer une
      voix sans sample. Pas d'état "métadonnées remplies, sample manquant"
      — ça ouvrirait des trous UX (acheteur paie, sample absent).

  Table `owned_voices` (jointure) :
    • Calque `owned_adns` : PK composite (user_id, voice_id), CASCADE des
      deux côtés, owned_at en server_default.
    • Pas de quantité ni de licence personnalisée — la licence est figée
      au moment de l'achat dans la transaction (metadata_json), pas dans
      la jointure.

  Indices :
    • `(artist_id, is_published)` couvre "liste les voix publiées d'un
      artiste" — requête principale du profil public /u/<slug>.
    • `(is_published, created_at DESC)` pour un futur flux marketplace.

  Rollback : downgrade() drop owned_voices puis voices_for_sale (junction
  avant parent, comme 0021_add_playlists).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0023_add_voices_for_sale"
down_revision = "0022_seed_smyle_official"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Table principale : voix à vendre ──────────────────────────────────
    op.create_table(
        "voices_for_sale",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("style", sa.String(length=80), nullable=False),
        # JSONB array de strings (genres compatibles : RnB, Pop, Trap, ...)
        sa.Column(
            "genres",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sample_url", sa.String(length=500), nullable=False),
        sa.Column("license", sa.String(length=16), nullable=False),
        sa.Column("price_credits", sa.Integer(), nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean(),
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
        sa.CheckConstraint(
            "price_credits >= 50 AND price_credits <= 5000",
            name="ck_voices_price_credits_range",
        ),
        sa.CheckConstraint(
            "license IN ('personnel', 'commercial', 'exclusif')",
            name="ck_voices_license_enum",
        ),
        sa.CheckConstraint(
            "char_length(name) >= 1 AND char_length(name) <= 40",
            name="ck_voices_name_length",
        ),
        sa.CheckConstraint(
            "char_length(style) >= 1 AND char_length(style) <= 80",
            name="ck_voices_style_length",
        ),
    )
    op.create_index(
        "ix_voices_artist_published",
        "voices_for_sale",
        ["artist_id", "is_published"],
    )
    op.create_index(
        "ix_voices_published_created",
        "voices_for_sale",
        ["is_published", "created_at"],
    )

    # ── Junction user ↔ voice possédée ────────────────────────────────────
    op.create_table(
        "owned_voices",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "voice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voices_for_sale.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "owned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "voice_id", name="pk_owned_voices"
        ),
    )


def downgrade() -> None:
    op.drop_table("owned_voices")
    op.drop_index(
        "ix_voices_published_created", table_name="voices_for_sale"
    )
    op.drop_index(
        "ix_voices_artist_published", table_name="voices_for_sale"
    )
    op.drop_table("voices_for_sale")
