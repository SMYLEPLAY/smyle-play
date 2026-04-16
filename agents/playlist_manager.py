# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — agents/playlist_manager.py
#
# Agent d'attribution de playlist selon l'ADN musical.
# Fait le lien entre l'ADN classifié et la playlist cible dans l'app.
#
# Mapping actuel :
#   SUNSET_LOVER   → playlist_sunset
#   NIGHT_CITY     → playlist_cyber_city
#   JUNGLE_OSMOSE  → playlist_jungle_nature
#
# Extensible : ajouter de nouveaux ADN dans _DNA_TO_PLAYLIST.
#
# Usage :
#   from agents.playlist_manager import assign_playlist
#   result = assign_playlist("NIGHT_CITY")
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
from typing import TypedDict


# ── Types ─────────────────────────────────────────────────────────────────────

class PlaylistAssignment(TypedDict):
    playlist_id:    str     # identifiant interne (utilisé dans l'app)
    playlist_label: str     # nom affiché dans l'UI
    playlist_emoji: str     # icône associée
    playlist_color: str     # couleur hex dominante pour le rendu


# ── Table de mapping ADN → Playlist ──────────────────────────────────────────
# Structure extensible : chaque ADN pointe vers un dictionnaire PlaylistAssignment.
# Pour ajouter un nouvel ADN, ajouter une entrée ici.

_DNA_TO_PLAYLIST: dict[str, PlaylistAssignment] = {

    'SUNSET_LOVER': PlaylistAssignment(
        playlist_id='playlist_sunset',
        playlist_label='Sunset Lover',
        playlist_emoji='🌅',
        playlist_color='#FF9B4A',
    ),

    'NIGHT_CITY': PlaylistAssignment(
        playlist_id='playlist_cyber_city',
        playlist_label='Night City',
        playlist_emoji='🌃',
        playlist_color='#8B5CF6',
    ),

    'JUNGLE_OSMOSE': PlaylistAssignment(
        playlist_id='playlist_jungle_nature',
        playlist_label='Jungle Osmose',
        playlist_emoji='🌿',
        playlist_color='#22C55E',
    ),

    # ── Réservés pour futurs ADN ──────────────────────────────────────────
    # 'DEEP_OCEAN': PlaylistAssignment(
    #     playlist_id='playlist_deep_ocean',
    #     playlist_label='Deep Ocean',
    #     playlist_emoji='🌊',
    #     playlist_color='#0EA5E9',
    # ),
    # 'DESERT_WIND': PlaylistAssignment(
    #     playlist_id='playlist_desert_wind',
    #     playlist_label='Desert Wind',
    #     playlist_emoji='🏜️',
    #     playlist_color='#F59E0B',
    # ),
}

# Playlist de fallback si l'ADN est inconnu
_FALLBACK_PLAYLIST = PlaylistAssignment(
    playlist_id='playlist_uncategorized',
    playlist_label='Non classifié',
    playlist_emoji='🎵',
    playlist_color='#6B7280',
)


# ── Fonction principale ───────────────────────────────────────────────────────

def assign_playlist(dna: str) -> PlaylistAssignment:
    """
    Retourne la playlist correspondant à l'ADN donné.

    Paramètre :
        dna (str) — code ADN, ex: "SUNSET_LOVER", "NIGHT_CITY", "JUNGLE_OSMOSE"

    Retourne :
        {
            "playlist_id":    str,   # ex: "playlist_sunset"
            "playlist_label": str,   # ex: "Sunset Lover"
            "playlist_emoji": str,   # ex: "🌅"
            "playlist_color": str,   # ex: "#FF9B4A"
        }
    """
    return _DNA_TO_PLAYLIST.get(dna, _FALLBACK_PLAYLIST)


def list_dna() -> list[str]:
    """Retourne la liste de tous les ADN connus."""
    return list(_DNA_TO_PLAYLIST.keys())


def list_playlists() -> list[PlaylistAssignment]:
    """Retourne toutes les playlists disponibles."""
    return list(_DNA_TO_PLAYLIST.values())
