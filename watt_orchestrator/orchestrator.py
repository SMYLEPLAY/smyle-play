# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — watt_orchestrator/orchestrator.py
#
# Orchestrateur LLM de la chaîne autonome WATT.
# Pipeline async :
#
#   [Track] → dna_classifier (LLM) → playlist_manager (rules)
#           → suno_prompt_architect (LLM) → [AgentResult]
#
# Interface identique à agents/orchestrator.py :
#   process_track(track: dict) -> AgentResult
#
# Différences vs. agents/orchestrator.py :
#   - Async : utilise await sur les agents LLM.
#   - Prompt caching actif sur chaque appel LLM.
#   - Métriques de cache loggées en JSON structuré avec tag [CACHE].
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TypedDict

from .agents.dna_classifier import classify_track
from .agents.playlist_manager import assign_playlist
from .agents.suno_prompt_architect import generate_prompt

logger = logging.getLogger(__name__)


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

async def process_track(track: dict) -> AgentResult:
    """
    Pipeline complet de traitement d'un morceau (async, LLM-backed).

    Paramètres attendus dans `track` :
        name   (str)        — titre du morceau
        genre  (str)        — genre déclaré (optionnel)
        tags   (str | list) — tags libres (optionnel)
        bpm    (float)      — BPM si disponible (optionnel)
        id     (int)        — ID base de données (optionnel, pour logging)

    Retourne un AgentResult complet avec ADN, playlist et prompt Suno.

    Toutes les exceptions internes sont loggées ; en cas d'erreur partielle,
    les champs disponibles sont retournés avec des valeurs de fallback.
    """
    track_name = (track.get("name") or "").strip()
    track_id   = track.get("id", "?")

    logger.info('[WATT Orchestrator] Processing track id=%s name="%s"', track_id, track_name)

    # ── Étape 1 : Classification ADN (LLM + cache) ────────────────────────
    try:
        dna_result = await classify_track(track)
        logger.info(
            "[WATT Orchestrator] DNA=%s confidence=%.2f method=%s",
            dna_result["dna"],
            dna_result["confidence"],
            dna_result["method"],
        )
    except Exception as e:
        logger.error("[WATT Orchestrator] dna_classifier error: %s", e)
        dna_result = {
            "dna": "SUNSET_LOVER",
            "confidence": 0.0,
            "scores": {
                "SUNSET_LOVER": 1.0,
                "NIGHT_CITY": 0.0,
                "JUNGLE_OSMOSE": 0.0,
            },
            "method": "error",
        }

    dna = dna_result["dna"]

    # ── Étape 2 : Attribution playlist (rule-based, synchrone) ───────────
    try:
        playlist = assign_playlist(dna)
        logger.info("[WATT Orchestrator] Playlist → %s", playlist["playlist_id"])
    except Exception as e:
        logger.error("[WATT Orchestrator] playlist_manager error: %s", e)
        playlist = {
            "playlist_id":    "playlist_uncategorized",
            "playlist_label": "Non classifié",
            "playlist_emoji": "🎵",
            "playlist_color": "#6B7280",
        }

    # ── Étape 3 : Génération prompt Suno (LLM + cache) ───────────────────
    try:
        suno = await generate_prompt(dna, track_title=track_name)
        logger.info(
            "[WATT Orchestrator] Suno prompt generated (%d chars)",
            len(suno["prompt"]),
        )
    except Exception as e:
        logger.error("[WATT Orchestrator] suno_prompt_architect error: %s", e)
        suno = {
            "prompt":     "cinematic music, emotional, high quality production",
            "style_tags": [],
            "negative":   "",
            "bpm_hint":   "100 BPM",
            "mood":       "Universel, cinématique.",
        }

    # ── Assemblage du résultat final ──────────────────────────────────────
    return AgentResult(
        dna=dna_result["dna"],
        confidence=dna_result["confidence"],
        scores=dna_result["scores"],
        method=dna_result["method"],
        playlist_id=playlist["playlist_id"],
        playlist_label=playlist["playlist_label"],
        playlist_emoji=playlist["playlist_emoji"],
        playlist_color=playlist["playlist_color"],
        suno_prompt=suno["prompt"],
        style_tags=suno["style_tags"],
        negative=suno["negative"],
        bpm_hint=suno["bpm_hint"],
        mood=suno["mood"],
        track_name=track_name,
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
