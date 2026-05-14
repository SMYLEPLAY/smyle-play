#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — scripts/test_cache_hit.py
#
# Smoke test : vérifie que le prompt caching Anthropic fonctionne
# en faisant 2 appels successifs sur dna_classifier et suno_prompt_architect.
#
# Critère de succès :
#   2e appel → cache_read_input_tokens > 0 ET > 70% du total input.
#
# Prérequis :
#   export ANTHROPIC_API_KEY=sk-ant-...
#
# Usage :
#   cd /path/to/Smyleplay
#   python scripts/test_cache_hit.py
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# ── Setup logging pour voir les métriques [CACHE] ─────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Import du module watt_orchestrator ───────────────────────────────────────
# S'assure que le projet est dans le PYTHONPATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from watt_orchestrator.anthropic.client import get_client  # noqa: E402 — après sys.path
from watt_orchestrator.anthropic.cache import (  # noqa: E402
    build_system_blocks,
    cache_last_tool,
    safe_ttl,
)
from watt_orchestrator.agents.dna_classifier import (  # noqa: E402
    _CLASSIFY_TOOL,
    _AGENT_IDENTITY,
    _STABLE_CONTEXT,
    MODEL,
)


# ── Échantillon de tracks de test ────────────────────────────────────────────

TEST_TRACKS = [
    {"name": "Golden Hour Drift", "genre": "tropical house", "bpm": 110},
    {"name": "Midnight Metropolis", "genre": "neo soul jazz", "bpm": 82},
    {"name": "Jungle Ritual", "genre": "afrobeat", "tags": ["kora", "tribal"]},
]


# ── Appel direct avec extraction des métriques usage ─────────────────────────

async def _call_dna_classifier(track: dict, call_index: int) -> dict:
    """Appel direct à messages.create() pour dna_classifier avec extraction des métriques."""
    client = get_client()

    name  = (track.get("name") or "").strip()
    genre = (track.get("genre") or "").strip()
    tags  = track.get("tags", "") or ""
    if isinstance(tags, list):
        tags = ", ".join(str(t) for t in tags)
    bpm = track.get("bpm")

    user_content = f"Titre : {name or '(sans titre)'}"
    if genre:
        user_content += f"\nGenre : {genre}"
    if tags:
        user_content += f"\nTags : {tags}"
    if bpm:
        user_content += f"\nBPM : {bpm}"

    system = build_system_blocks(
        agent_identity=_AGENT_IDENTITY,
        stable_context=_STABLE_CONTEXT,
        model=MODEL,
    )
    tools = cache_last_tool([_CLASSIFY_TOOL], ttl=safe_ttl(MODEL, "1h"))

    response = await client.messages.create(
        model=MODEL,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=tools,
        tool_choice={"type": "tool", "name": "classify_track"},
        max_tokens=256,
    )

    usage = response.usage
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read     = getattr(usage, "cache_read_input_tokens", 0) or 0
    input_tokens   = getattr(usage, "input_tokens", 0) or 0
    total_input    = input_tokens + cache_read + cache_creation
    cache_hit_rate = round(cache_read / total_input, 3) if total_input > 0 else 0.0

    metrics = {
        "call":           call_index,
        "track":          name,
        "input_tokens":   input_tokens,
        "cache_creation": cache_creation,
        "cache_read":     cache_read,
        "total_input":    total_input,
        "cache_hit_rate": cache_hit_rate,
    }
    logger.info("[CACHE] %s", json.dumps(metrics, ensure_ascii=False))
    return metrics


async def run_smoke_test() -> None:
    print("\n" + "=" * 70)
    print("  SMYLE PLAY — Smoke Test Prompt Caching")
    print("  Agent : dna_classifier | Modèle : " + MODEL)
    print("=" * 70)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n❌  ANTHROPIC_API_KEY non définie. Exporte-la et relance.")
        sys.exit(1)

    track = TEST_TRACKS[0]  # Golden Hour Drift

    print(f"\n▶  Appel 1 — attendu : cache_creation > 0, cache_read = 0")
    metrics1 = await _call_dna_classifier(track, call_index=1)

    print(f"\n▶  Appel 2 — attendu : cache_read > 0 et cache_hit_rate > 70%")
    metrics2 = await _call_dna_classifier(track, call_index=2)

    print("\n" + "─" * 70)
    print("  RÉSULTATS")
    print("─" * 70)

    def _row(label: str, v1: object, v2: object) -> None:
        print(f"  {label:<28} Appel 1: {str(v1):<12}  Appel 2: {v2}")

    _row("input_tokens",   metrics1["input_tokens"],   metrics2["input_tokens"])
    _row("cache_creation", metrics1["cache_creation"], metrics2["cache_creation"])
    _row("cache_read",     metrics1["cache_read"],     metrics2["cache_read"])
    _row("total_input",    metrics1["total_input"],    metrics2["total_input"])
    _row("cache_hit_rate", metrics1["cache_hit_rate"], metrics2["cache_hit_rate"])

    print("─" * 70)

    # ── Critères d'acceptation ─────────────────────────────────────────────
    failures = []

    if metrics1["cache_creation"] == 0:
        failures.append("Appel 1 : cache_creation_input_tokens == 0 (le cache n'a pas été créé)")

    if metrics2["cache_read"] == 0:
        failures.append("Appel 2 : cache_read_input_tokens == 0 (pas de hit cache)")

    if metrics2["cache_hit_rate"] < 0.70:
        failures.append(
            f"Appel 2 : cache_hit_rate={metrics2['cache_hit_rate']:.1%} < 70% requis"
        )

    if failures:
        print("\n❌  ÉCHEC — critères non respectés :")
        for f in failures:
            print(f"     • {f}")
        print()
        sys.exit(1)
    else:
        print(f"\n✅  SUCCÈS — cache_hit_rate appel 2 = {metrics2['cache_hit_rate']:.1%}")
        print("    Le prompt caching est opérationnel sur dna_classifier.\n")


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
