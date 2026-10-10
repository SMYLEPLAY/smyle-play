"""parcours_v1 — guide d'accueil vu, Œuvre masquée, vidéos de playlist

Revision ID: 0101_parcours_v1
Revises: 0100_redenomination_x10
Create Date: 2026-10-09

Trois changements pour le parcours V1 (décisions de Tom du 9/10/2026) :

1. `users.onboarding_done_at` (horodatage, NULL = guide jamais vu). Le guide
   d'accueil s'ouvre une seule fois, juste après la première connexion d'un
   NOUVEAU compte. Les comptes existants sont marqués « vu » à la date de la
   migration : ils ne le voient pas surgir (ils peuvent le rouvrir depuis le
   menu « Guide »).

2. `tracks.hidden_at` (horodatage, NULL = visible). Posé par le créateur depuis
   l'écran « Mes Œuvres » (Masquer). Un son masqué disparaît de toutes les
   listes publiques ; son propriétaire et ses acheteurs y gardent accès. Les
   moitiés vendables (recette, image) passent en non publiées en même temps :
   elles ont déjà ce drapeau, filtré partout.

3. Vidéos de couverture de playlist : elles étaient servies par le lecteur
   audio, qui refuse les vidéos. Elles ont désormais leur propre adresse
   (`/watt/playlist-video/…`) : les URL déjà enregistrées sont réécrites.

Downgrade : suppression des deux colonnes, URL de vidéo remises à l'ancienne
forme.
"""
import sqlalchemy as sa
from alembic import op

revision = "0101_parcours_v1"
down_revision = "0100_redenomination_x10"
branch_labels = None
depends_on = None

_ANCIEN = "/watt/stream/PLAYLISTS/"
_NOUVEAU = "/watt/playlist-video/PLAYLISTS/"


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "onboarding_done_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET onboarding_done_at = now()")

    op.add_column("tracks", sa.Column(
        "hidden_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        f"UPDATE playlists SET cover_video_url = replace(cover_video_url, '{_ANCIEN}', '{_NOUVEAU}') "
        f"WHERE cover_video_url LIKE '{_ANCIEN}%'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE playlists SET cover_video_url = replace(cover_video_url, '{_NOUVEAU}', '{_ANCIEN}') "
        f"WHERE cover_video_url LIKE '{_NOUVEAU}%'"
    )
    op.drop_column("tracks", "hidden_at")
    op.drop_column("users", "onboarding_done_at")
