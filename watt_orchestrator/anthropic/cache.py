# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — watt_orchestrator/anthropic/cache.py
#
# Helper centralisé pour le prompt caching Anthropic.
#
# Stratégie de breakpoints (4 max par requête, 2 stables + 1 dynamique) :
#   BP1 — Tools        : cache_last_tool() sur le dernier outil de la liste.
#   BP2 — System static: bloc rôle + règles + contexte projet WATT → 1h.
#   BP3 — System dyn   : bloc état session (optionnel) → 5m.
#
# TTL 1h supporté uniquement sur Opus 4.5 / Sonnet 4.5 / Haiku 4.5.
# safe_ttl() fait le fallback automatique vers "5m" sur les modèles plus anciens.
#
# Usage :
#   from watt_orchestrator.anthropic.cache import cache_last_tool, with_cache, safe_ttl
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from typing import Literal, TypedDict


# ── Types ─────────────────────────────────────────────────────────────────────

class CacheControl(TypedDict):
    type: Literal["ephemeral"]
    ttl: Literal["5m", "1h"]


EPHEMERAL_5M: CacheControl = {"type": "ephemeral", "ttl": "5m"}
EPHEMERAL_1H: CacheControl = {"type": "ephemeral", "ttl": "1h"}

# Modèles supportant le TTL étendu (1h).
# Ceux-ci sont vérifiés par substring pour tolérer les suffixes de date
# (ex. "claude-haiku-4-5-20251001" matche "claude-haiku-4-5").
MODELS_SUPPORTING_1H: frozenset[str] = frozenset({
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_ttl(model: str, requested: Literal["5m", "1h"]) -> Literal["5m", "1h"]:
    """
    Retourne le TTL demandé si le modèle le supporte, sinon "5m".

    Paramètres :
        model     — identifiant complet du modèle Anthropic
                    (ex: "claude-haiku-4-5-20251001")
        requested — TTL souhaité ("5m" ou "1h")

    Retourne :
        "1h" si modèle compatible ET requested == "1h", sinon "5m".
    """
    if requested == "1h":
        model_lower = model.lower()
        supported = any(m in model_lower for m in MODELS_SUPPORTING_1H)
        if not supported:
            return "5m"
    return requested  # type: ignore[return-value]


def with_cache(block: dict, ttl: Literal["5m", "1h"] = "5m") -> dict:
    """
    Ajoute cache_control à un content block existant.

    Paramètres :
        block — dict représentant un content block Anthropic
                (ex: {"type": "text", "text": "..."})
        ttl   — durée de cache ("5m" ou "1h")

    Retourne :
        Nouveau dict avec la clé "cache_control" ajoutée.
    """
    return {**block, "cache_control": {"type": "ephemeral", "ttl": ttl}}


def cache_last_tool(
    tools: list[dict],
    ttl: Literal["5m", "1h"] = "5m",
) -> list[dict]:
    """
    Place un breakpoint de cache sur le dernier tool de la liste.

    Anthropic recommande de cacher toute la liste d'outils en plaçant
    le cache_control sur le DERNIER outil : le cache préfixe s'applique
    alors à l'intégralité de la liste jusqu'à ce breakpoint.

    Paramètres :
        tools — liste de définitions d'outils Anthropic
        ttl   — durée de cache ("5m" ou "1h")

    Retourne :
        Même liste avec cache_control ajouté sur le dernier outil.
        Retourne la liste inchangée si elle est vide.
    """
    if not tools:
        return tools
    return [*tools[:-1], with_cache(tools[-1], ttl)]


def build_system_blocks(
    agent_identity: str,
    stable_context: str,
    session_context: str | None = None,
    model: str = "claude-haiku-4-5-20251001",
) -> list[dict]:
    """
    Construit la liste de blocs system avec breakpoints de cache optimaux.

    Structure :
        Bloc 1 (pas de cache) : identité + rôle de l'agent (court, change peu)
        Bloc 2 (cache 1h)     : règles stables + contexte projet WATT
        Bloc 3 (cache 5m)     : contexte session, si fourni

    Paramètres :
        agent_identity  — identité et rôle de l'agent (non caché)
        stable_context  — règles métier + contexte WATT stable (caché 1h)
        session_context — contexte session dynamique optionnel (caché 5m)
        model           — identifiant modèle pour safe_ttl()

    Retourne :
        Liste de content blocks prête pour le paramètre `system` de
        client.messages.create().
    """
    blocks: list[dict] = [
        {"type": "text", "text": agent_identity},
        with_cache(
            {"type": "text", "text": stable_context},
            ttl=safe_ttl(model, "1h"),
        ),
    ]
    if session_context:
        blocks.append(
            with_cache(
                {"type": "text", "text": session_context},
                ttl=safe_ttl(model, "5m"),
            )
        )
    return blocks
