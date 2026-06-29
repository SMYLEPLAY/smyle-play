"""ajout cover_url + prompt_id FK sur tracks (Sprint 1 — pivot ecoute)

Revision ID: 0025_track_cover_and_prompt_link
Revises: 0024_prompt_fiche_enriched
Create Date: 2026-05-04

Contexte produit (Sprint 1 — pivot du modèle vers Spotify-like) :

  Avant : la plateforme vendait des prompts « à l'aveugle ». L'acheteur
  voyait une fiche texte sans pouvoir écouter le morceau. Conversion
  faible, expérience de découverte zéro.

  Maintenant : le track devient le produit visible — cover + audio
  player public, le prompt est un bonus premium attaché. L'acheteur
  écoute, juge, achète éclairé.

  Cette migration ajoute 2 colonnes nullable sur `tracks` :

    1. **cover_url** (VARCHAR 2048, NULL) — URL R2 de la pochette du
       morceau. NULL = fallback sur brand_color de l'artiste (ce que
       fait déjà la card actuelle). Permet une expérience visuelle
       riche (album art) sans casser le rendu existant pour les
       tracks legacy.

    2. **prompt_id** (UUID FK, NULL) — lien explicite track → prompt.
       Quand l'artiste publie un track AVEC un prompt vendable, on
       crée le prompt puis on attache son ID au track. La cellule
       publique affiche alors le bouton « Débloquer le prompt » sur la
       card du track. NULL = track sans prompt vendable (juste
       écoutable, pas achetable).

       ON DELETE SET NULL : si le prompt est supprimé, le track reste
       (audio préservé), juste sans bouton débloquer. Plus safe que
       CASCADE qui supprimerait le track audio aussi.

Choix de design :
  - **Tout nullable** pour rétro-compat — les ~80 tracks WATT legacy
    importés via tracks.json restent valides sans cover ni prompt_id.
  - **Pas d'unicité prompt_id** — on permet techniquement plusieurs
    tracks de pointer le même prompt (cas remix / variations). Si on
    veut forcer 1-1 plus tard, on ajoute UNIQUE.
  - **Index sur prompt_id** — JOIN fréquent dans build_artist_detail_payload
    (chaque track doit savoir si un prompt existe pour afficher le bouton).

Rollback : downgrade() drop les 2 colonnes (FK auto-droppée par PG).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0025_track_cover_and_prompt_link"
down_revision = "0024_prompt_fiche_enriched"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("cover_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "tracks",
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tracks_prompt_id",
        "tracks",
        ["prompt_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_prompt_id", table_name="tracks")
    op.drop_column("tracks", "prompt_id")
    op.drop_column("tracks", "cover_url")
