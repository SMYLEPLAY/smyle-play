# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — agents/orchestrator.py
#
# Orchestrateur global de la chaîne autonome WATT.
# Coordonne les 3 agents en séquence :
#
#   [Track] → dna_classifier → playlist_manager → suno_prompt_architect → [Result]
#
# Point d'entrée unique : process_track(track)
#
# Usage :
#   from agents.orchestrator import process_track
#   result = process_track({"name": "Golden Hour Drift", "genre": "tropical house"})
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import TypedDict

from .dna_classifier      import classify_track
from .playlist_manager    import assign_playlist
from .suno_prompt_architect import generate_prompt

logger = logging.getLogger(__name__)


# ── Observabilité (P2, 2026-07-30) ────────────────────────────────────────
# Les fallbacks silencieux masquaient des bugs : un classifieur cassé rangeait
# TOUT en SUNSET_LOVER confidence 0.0 sans que personne ne le voie. On garde
# les fallbacks (robustesse : jamais de crash pipeline) mais on les rend
# BRUYANTS : exc_info complet, marqueur FALLBACK grep-able, compteur cumulé.
FALLBACK_COUNTS = {'dna': 0, 'playlist': 0, 'suno': 0}


# ── Types ─────────────────────────────────────────────────────────────────────

class AgentResult(TypedDict):
    # ADN
    dna:            str
    confidence:     float
    scores:         dict[str, float]
    method:         str
    # Playlist
    playlist_id:    str
    playlist_label: str
    playlist_emoji: str
    playlist_color: str
    # Suno
    suno_prompt:    str
    style_tags:     list[str]
    negative:       str
    bpm_hint:       str
    mood:           str
    # Méta
    track_name:     str
    processed_at:   str   # ISO 8601


# ── Orchestrateur ─────────────────────────────────────────────────────────────

def process_track(track: dict) -> AgentResult:
    """
    Pipeline complet de traitement d'un morceau.

    Paramètres attendus dans `track` :
        name   (str)        — titre du morceau
        genre  (str)        — genre déclaré (optionnel)
        tags   (str | list) — tags libres (optionnel)
        bpm    (float)      — BPM si disponible (optionnel)
        id     (int)        — ID base de données (optionnel, pour logging)

    Retourne un AgentResult complet avec ADN, playlist et prompt Suno.

    Exceptions :
        Toutes les exceptions internes sont loggées mais ne propagent pas.
        En cas d'erreur partielle, les champs disponibles sont retournés.
    """
    track_name = (track.get('name') or '').strip()
    track_id   = track.get('id', '?')

    logger.info(f'[WATT Agent] Processing track id={track_id} name="{track_name}"')

    # ── Étape 1 : Classification ADN ─────────────────────────────────────────
    try:
        dna_result = classify_track(track)
        logger.info(
            f'[WATT Agent] DNA={dna_result["dna"]} '
            f'confidence={dna_result["confidence"]:.2f} '
            f'method={dna_result["method"]}'
        )
    except Exception:
        FALLBACK_COUNTS['dna'] += 1
        logger.error(
            f'[WATT Agent] FALLBACK dna_classifier — track id={track_id} '
            f'name="{track_name}" rangé en SUNSET_LOVER confidence=0.0 '
            f'(cumul: {FALLBACK_COUNTS["dna"]})',
            exc_info=True,
        )
        dna_result = {
            'dna': 'SUNSET_LOVER', 'confidence': 0.0,
            'scores': {}, 'method': 'error',
        }

    dna = dna_result['dna']

    # ── Étape 2 : Attribution playlist ───────────────────────────────────────
    try:
        playlist = assign_playlist(dna)
        logger.info(f'[WATT Agent] Playlist → {playlist["playlist_id"]}')
    except Exception:
        FALLBACK_COUNTS['playlist'] += 1
        logger.error(
            f'[WATT Agent] FALLBACK playlist_manager — track id={track_id} '
            f'→ playlist_uncategorized (cumul: {FALLBACK_COUNTS["playlist"]})',
            exc_info=True,
        )
        playlist = {
            'playlist_id': 'playlist_uncategorized',
            'playlist_label': 'Non classifié',
            'playlist_emoji': '🎵',
            'playlist_color': '#6B7280',
        }

    # ── Étape 3 : Génération prompt Suno ─────────────────────────────────────
    try:
        suno = generate_prompt(dna, track_title=track_name)
        logger.info(f'[WATT Agent] Suno prompt generated ({len(suno["prompt"])} chars)')
    except Exception:
        FALLBACK_COUNTS['suno'] += 1
        logger.error(
            f'[WATT Agent] FALLBACK suno_prompt_architect — track id={track_id} '
            f'→ prompt générique (cumul: {FALLBACK_COUNTS["suno"]})',
            exc_info=True,
        )
        suno = {
            'prompt':     'cinematic music, emotional, high quality production',
            'style_tags': [],
            'negative':   '',
            'bpm_hint':   '100 BPM',
            'mood':       'Universel, cinématique.',
        }

    # ── Assemblage du résultat final ──────────────────────────────────────────
    # Signal de synthèse : UNE ligne WARNING grep-able si le résultat est dégradé.
    if dna_result.get('method') == 'error':
        logger.warning(
            f'[WATT Agent] RESULT DEGRADED track id={track_id} name="{track_name}" '
            f'— classification en échec, ADN par défaut. Vérifier le classifieur.'
        )

    return AgentResult(
        # ADN
        dna=dna_result['dna'],
        confidence=dna_result['confidence'],
        scores=dna_result['scores'],
        method=dna_result['method'],
        # Playlist
        playlist_id=playlist['playlist_id'],
        playlist_label=playlist['playlist_label'],
        playlist_emoji=playlist['playlist_emoji'],
        playlist_color=playlist['playlist_color'],
        # Suno
        suno_prompt=suno['prompt'],
        style_tags=suno['style_tags'],
        negative=suno['negative'],
        bpm_hint=suno['bpm_hint'],
        mood=suno['mood'],
        # Méta
        track_name=track_name,
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
