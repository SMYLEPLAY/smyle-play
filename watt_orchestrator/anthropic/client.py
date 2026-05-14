# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — watt_orchestrator/anthropic/client.py
#
# Wrapper logging autour d'anthropic.AsyncAnthropic.
#
# Responsabilité unique : instrumenter chaque appel messages.create() pour
# logger les métriques de cache Anthropic en JSON structuré :
#   - cache_creation_input_tokens
#   - cache_read_input_tokens
#   - input_tokens
#
# Ces métriques alimenteront le Control Center WATT (Phase F).
#
# Usage :
#   from watt_orchestrator.anthropic.client import create_message
#
#   response = await create_message(
#       agent_name="dna_classifier",
#       model="claude-haiku-4-5-20251001",
#       system=system_blocks,
#       tools=cached_tools,
#       messages=messages,
#       max_tokens=512,
#   )
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# Client singleton partagé entre les agents — thread-safe (asyncio)
_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    """Retourne le client Anthropic singleton (lazy init)."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY non définie. "
                "Exporte-la dans ton environnement avant de lancer les agents."
            )
        _client = anthropic.AsyncAnthropic(api_key=api_key)
    return _client


def _log_cache_metrics(
    agent_name: str,
    model: str,
    usage: Any,
    duration_ms: float,
) -> None:
    """
    Log JSON structuré des métriques cache en niveau INFO.

    Format attendu :
        [CACHE] {"agent": "dna_classifier", "model": "...", "input_tokens": N,
                 "cache_creation": N, "cache_read": N, "duration_ms": N}
    """
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read     = getattr(usage, "cache_read_input_tokens", 0) or 0
    input_tokens   = getattr(usage, "input_tokens", 0) or 0
    output_tokens  = getattr(usage, "output_tokens", 0) or 0

    # Taux de hit cache : proportion des tokens stable servis depuis le cache
    total_input = input_tokens + cache_read + cache_creation
    cache_hit_rate = round(cache_read / total_input, 3) if total_input > 0 else 0.0

    metrics = {
        "agent":           agent_name,
        "model":           model,
        "input_tokens":    input_tokens,
        "cache_creation":  cache_creation,
        "cache_read":      cache_read,
        "output_tokens":   output_tokens,
        "total_input":     total_input,
        "cache_hit_rate":  cache_hit_rate,
        "duration_ms":     round(duration_ms, 1),
    }

    logger.info("[CACHE] %s", json.dumps(metrics, ensure_ascii=False))


async def create_message(
    agent_name: str,
    model: str,
    system: list[dict],
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 1024,
    **kwargs: Any,
) -> anthropic.types.Message:
    """
    Wrapper instrumenté autour de client.messages.create().

    Log systématiquement les métriques de cache après chaque appel.
    Toute exception se propage normalement (pas de swallow silencieux).

    Paramètres :
        agent_name — nom de l'agent pour le tag [CACHE] dans les logs
        model      — identifiant modèle Anthropic complet
        system     — liste de content blocks system (avec cache_control)
        messages   — liste de messages user/assistant
        tools      — liste de définitions d'outils (avec cache_control sur
                     le dernier, via cache_last_tool())
        max_tokens — limite de tokens en sortie
        **kwargs   — paramètres supplémentaires passés à messages.create()

    Retourne :
        anthropic.types.Message complet (content, usage, stop_reason, etc.)
    """
    client = get_client()

    call_kwargs: dict[str, Any] = {
        "model":      model,
        "system":     system,
        "messages":   messages,
        "max_tokens": max_tokens,
        **kwargs,
    }
    if tools is not None:
        call_kwargs["tools"] = tools

    t0 = time.monotonic()
    response = await client.messages.create(**call_kwargs)
    duration_ms = (time.monotonic() - t0) * 1000

    _log_cache_metrics(agent_name, model, response.usage, duration_ms)

    return response
