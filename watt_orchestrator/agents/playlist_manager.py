# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — watt_orchestrator/agents/playlist_manager.py
#
# Agent d'attribution de playlist selon l'ADN musical.
# Implémentation rule-based (lookup table) — aucun appel LLM nécessaire
# car la correspondance ADN → playlist est une table de mapping statique.
#
# Interface : identique à agents.playlist_manager.assign_playlist()
#   assign_playlist(dna: str) -> PlaylistAssignment
#
# Synchrone (pas async) car aucune I/O.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from typing import TypedDict


# ── Types ─────────────────────────────────────────────────────────────────────

class PlaylistAssignment(TypedDict):
    playlist_id:    str
    playlist_label: str
    playlist_emoji: str
    playlist_color: str


# ── Table de mapping ADN → Playlist ──────────────────────────────────────────

_DNA_TO_PLAYLIST: dict[str, PlaylistAssignment] = {
    "SUNSET_LOVER": PlaylistAssignment(
        playlist_id="playlist_sunset",
        playlist_label="Sunset Lover",
        playlist_emoji="🌅",
        playlist_color="#FF9B4A",
    ),
    "NIGHT_CITY": PlaylistAssignment(
        playlist_id="playlist_cyber_city",
        playlist_label="Night City",
        playlist_emoji="🌃",
        playlist_color="#8B5CF6",
    ),
    "JUNGLE_OSMOSE": PlaylistAssignment(
        playlist_id="playlist_jungle_nature",
        playlist_label="Jungle Osmose",
        playlist_emoji="🌿",
        playlist_color="#22C55E",
    ),
}

_FALLBACK_PLAYLIST = PlaylistAssignment(
    playlist_id="playlist_uncategorized",
    playlist_label="Non classifié",
    playlist_emoji="🎵",
    playlist_color="#6B7280",
)


# ── Fonction principale ───────────────────────────────────────────────────────

def assign_playlist(dna: str) -> PlaylistAssignment:
    """
    Retourne la playlist correspondant à l'ADN donné.

    Synchrone — aucun appel réseau. La table est statique et exhaustive
    pour les 3 ADN WATT actuels. Fallback vers 'Non classifié' pour tout
    ADN inconnu (futur ADN, erreur upstream).
    """
    return _DNA_TO_PLAYLIST.get(dna, _FALLBACK_PLAYLIST)


def list_dna() -> list[str]:
    """Retourne la liste de tous les ADN connus."""
    return list(_DNA_TO_PLAYLIST.keys())
