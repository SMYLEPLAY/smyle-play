# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — tests/test_cache.py
#
# Tests unitaires pour watt_orchestrator/anthropic/cache.py
# Aucun appel réseau, aucune dépendance Anthropic.
#
# Lance avec :
#   pytest tests/test_cache.py -v
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import pytest
from watt_orchestrator.anthropic.cache import (
    EPHEMERAL_1H,
    EPHEMERAL_5M,
    MODELS_SUPPORTING_1H,
    build_system_blocks,
    cache_last_tool,
    safe_ttl,
    with_cache,
)


# ── safe_ttl ──────────────────────────────────────────────────────────────────

class TestSafeTtl:
    def test_5m_always_allowed(self):
        """5m est toujours retourné, quel que soit le modèle."""
        assert safe_ttl("claude-opus-3", "5m") == "5m"
        assert safe_ttl("claude-haiku-4-5-20251001", "5m") == "5m"
        assert safe_ttl("gpt-4", "5m") == "5m"

    def test_1h_on_supported_models(self):
        """1h est retourné sur les modèles haiku/sonnet/opus 4.5."""
        assert safe_ttl("claude-haiku-4-5-20251001", "1h") == "1h"
        assert safe_ttl("claude-sonnet-4-5", "1h") == "1h"
        assert safe_ttl("claude-opus-4-5", "1h") == "1h"
        # Insensible à la casse
        assert safe_ttl("Claude-Haiku-4-5-20251001", "1h") == "1h"

    def test_1h_fallback_on_old_models(self):
        """1h → fallback 5m sur les modèles anciens."""
        assert safe_ttl("claude-3-haiku-20240307", "1h") == "5m"
        assert safe_ttl("claude-3-5-sonnet-20241022", "1h") == "5m"
        assert safe_ttl("claude-opus-3", "1h") == "5m"

    def test_supported_models_set_non_empty(self):
        """Le set des modèles supportant 1h n'est pas vide."""
        assert len(MODELS_SUPPORTING_1H) > 0


# ── with_cache ────────────────────────────────────────────────────────────────

class TestWithCache:
    def test_adds_cache_control_5m(self):
        block = {"type": "text", "text": "hello"}
        result = with_cache(block, ttl="5m")
        assert result["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
        assert result["type"] == "text"
        assert result["text"] == "hello"

    def test_adds_cache_control_1h(self):
        block = {"type": "text", "text": "stable context"}
        result = with_cache(block, ttl="1h")
        assert result["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_does_not_mutate_original(self):
        """with_cache ne doit pas modifier le dict original."""
        block = {"type": "text", "text": "immutable"}
        _ = with_cache(block)
        assert "cache_control" not in block

    def test_default_ttl_is_5m(self):
        block = {"type": "text", "text": "default"}
        result = with_cache(block)
        assert result["cache_control"]["ttl"] == "5m"

    def test_constants_match_structure(self):
        assert EPHEMERAL_5M == {"type": "ephemeral", "ttl": "5m"}
        assert EPHEMERAL_1H == {"type": "ephemeral", "ttl": "1h"}


# ── cache_last_tool ───────────────────────────────────────────────────────────

class TestCacheLastTool:
    def test_single_tool_gets_cache(self):
        tools = [{"name": "my_tool", "description": "does stuff"}]
        result = cache_last_tool(tools, ttl="5m")
        assert len(result) == 1
        assert result[0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}

    def test_only_last_tool_gets_cache(self):
        tools = [
            {"name": "tool_a"},
            {"name": "tool_b"},
            {"name": "tool_c"},
        ]
        result = cache_last_tool(tools)
        assert "cache_control" not in result[0]
        assert "cache_control" not in result[1]
        assert "cache_control" in result[2]

    def test_empty_list_returns_empty(self):
        assert cache_last_tool([]) == []

    def test_does_not_mutate_original_list(self):
        tools = [{"name": "tool_a"}, {"name": "tool_b"}]
        result = cache_last_tool(tools)
        assert "cache_control" not in tools[-1], "L'original ne doit pas être muté"

    def test_1h_ttl_applied_correctly(self):
        tools = [{"name": "stable_tool"}]
        result = cache_last_tool(tools, ttl="1h")
        assert result[0]["cache_control"]["ttl"] == "1h"

    def test_preserves_tool_fields(self):
        tools = [{"name": "classify", "description": "classifie", "input_schema": {}}]
        result = cache_last_tool(tools, ttl="5m")
        assert result[0]["name"] == "classify"
        assert result[0]["description"] == "classifie"
        assert result[0]["input_schema"] == {}


# ── build_system_blocks ───────────────────────────────────────────────────────

class TestBuildSystemBlocks:
    def test_two_blocks_without_session(self):
        blocks = build_system_blocks(
            agent_identity="Je suis un agent.",
            stable_context="Contexte stable.",
        )
        assert len(blocks) == 2
        assert blocks[0]["text"] == "Je suis un agent."
        assert "cache_control" not in blocks[0], "Le 1er bloc (identité) ne doit pas être caché"
        assert blocks[1]["cache_control"]["type"] == "ephemeral"

    def test_three_blocks_with_session(self):
        blocks = build_system_blocks(
            agent_identity="Agent X",
            stable_context="Règles stables",
            session_context="Créateur ID=42",
        )
        assert len(blocks) == 3
        assert blocks[2]["text"] == "Créateur ID=42"
        assert blocks[2]["cache_control"]["ttl"] == "5m"

    def test_stable_bloc_gets_1h_on_supported_model(self):
        blocks = build_system_blocks(
            agent_identity="Agent",
            stable_context="Contexte",
            model="claude-haiku-4-5-20251001",
        )
        assert blocks[1]["cache_control"]["ttl"] == "1h"

    def test_stable_bloc_falls_back_5m_on_old_model(self):
        blocks = build_system_blocks(
            agent_identity="Agent",
            stable_context="Contexte",
            model="claude-3-haiku-20240307",
        )
        assert blocks[1]["cache_control"]["ttl"] == "5m"
