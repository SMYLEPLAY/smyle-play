# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — watt_orchestrator/agents/dna_classifier.py
#
# Agent LLM de classification ADN musical.
# Remplace la version keyword-based de agents/dna_classifier.py par un
# appel Claude avec prompt caching sur tools + system stable.
#
# Interface : identique à agents.dna_classifier.classify_track()
#   classify_track(track: dict) -> DNAResult
#
# Stratégie de cache :
#   BP1 — Tool "classify_track" (seul outil) → caché 1h
#   BP2 — Bloc system stable (rôle + ADN descriptions + règles) → caché 1h
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import logging
from typing import TypedDict

from watt_orchestrator.anthropic.cache import (
    build_system_blocks,
    cache_last_tool,
    safe_ttl,
)
from watt_orchestrator.anthropic.client import create_message

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"


# ── Types ─────────────────────────────────────────────────────────────────────

class DNAResult(TypedDict):
    dna:        str
    confidence: float
    scores:     dict[str, float]
    method:     str


# ── Définition du tool (stable → caché 1h) ───────────────────────────────────

_CLASSIFY_TOOL = {
    "name": "classify_track",
    "description": (
        "Classifie un morceau musical et retourne son ADN parmi les 3 univers "
        "WATT définis. Toujours appeler cet outil avec des scores pour les 3 ADN."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dna": {
                "type": "string",
                "enum": ["SUNSET_LOVER", "NIGHT_CITY", "JUNGLE_OSMOSE"],
                "description": "ADN dominant du morceau.",
            },
            "confidence": {
                "type": "number",
                "description": "Score de confiance de 0.0 à 1.0 pour l'ADN dominant.",
            },
            "scores": {
                "type": "object",
                "description": "Scores normalisés (somme = 1.0) pour les 3 ADN.",
                "properties": {
                    "SUNSET_LOVER":  {"type": "number"},
                    "NIGHT_CITY":    {"type": "number"},
                    "JUNGLE_OSMOSE": {"type": "number"},
                },
                "required": ["SUNSET_LOVER", "NIGHT_CITY", "JUNGLE_OSMOSE"],
            },
            "method": {
                "type": "string",
                "description": "Méthode de classification utilisée.",
                "enum": ["llm", "llm_low_confidence"],
            },
        },
        "required": ["dna", "confidence", "scores", "method"],
    },
}

# ── System prompt (stable → caché 1h) ────────────────────────────────────────

_AGENT_IDENTITY = "Tu es l'agent de classification ADN de SMYLE PLAY."

_STABLE_CONTEXT = """
## Rôle
Tu analyses un morceau musical (titre, genre, tags, BPM) et tu lui attribues
un ADN parmi les 3 univers WATT. Tu appelles TOUJOURS l'outil classify_track.

## Les 3 univers ADN WATT

### SUNSET_LOVER
Ambiance : golden hour, lumière chaude, plage, rooftop, été, chaleur mélodie.
Genres clés : tropical house, beach house, chillout, nu disco, balearic, bossa nova.
Instruments typiques : guitare nylon, marimba, saxophone smooth, congas, flûte.
BPM caractéristique : 95-128 BPM.
Mots-clés forts : golden, amber, sunset, soleil, ibiza, rooftop, plage, summer,
cocktails, yacht, moonlight, smooth, warm, beach, tropical, melodic.

### NIGHT_CITY
Ambiance : nuit urbaine, néons, cinéma noir, jazz soul, introspection, âme urbaine.
Genres clés : neo soul, jazz hop, lo-fi jazz, cinematic jazz, nu jazz, soulful RnB.
Instruments typiques : contrebasse, trompette bouchée, sax ténor, Rhodes, batterie brushed.
BPM caractéristique : 70-95 BPM.
Mots-clés forts : night, midnight, nocturne, city, jazz, soul, lofi, cinematic,
metropolis, groove, funk, neons, moon, urban, soulful.

### JUNGLE_OSMOSE
Ambiance : forêt tropicale, tribal, organique, Caribbean, rituel, nature immersive.
Genres clés : afrobeat, world music, tribal house, reggae dub, afro jazz, caribbean.
Instruments typiques : kora, djembe, marimba, steel pan, talking drum, balafon.
BPM caractéristique : 90-130 BPM.
Mots-clés forts : jungle, osmose, tropical, forêt, dancehall, ritual, marimba,
caraibes, kora, canopy, afrobeat, ethnic, tribal, organic, caribbean.

## Règles de classification
1. Un seul ADN dominant par morceau. Les scores des 3 ADN doivent sommer à 1.0.
2. confidence = score de l'ADN dominant.
3. Si le titre est vague ou générique, base-toi sur le genre/tags.
4. En cas de doute total, attribue SUNSET_LOVER (ADN le plus universel).
5. method = "llm_low_confidence" si confidence < 0.50, sinon "llm".
6. NE PAS répondre en texte libre. TOUJOURS appeler classify_track.
"""


# ── Fonction principale ───────────────────────────────────────────────────────

async def classify_track(track: dict) -> DNAResult:
    """
    Classifie un morceau via Claude + prompt caching.

    Paramètres attendus dans `track` :
        name   (str)  — titre du morceau
        genre  (str)  — genre déclaré (optionnel)
        tags   (str | list) — tags libres (optionnel)
        bpm    (float)  — BPM si disponible (optionnel)

    Retourne un DNAResult avec dna, confidence, scores, method.
    """
    name  = (track.get("name") or "").strip()
    genre = (track.get("genre") or "").strip()
    tags  = track.get("tags", "") or ""
    if isinstance(tags, list):
        tags = ", ".join(str(t) for t in tags)
    bpm = track.get("bpm")

    # ── Construction du message user
    user_content = f"Titre : {name or '(sans titre)'}"
    if genre:
        user_content += f"\nGenre : {genre}"
    if tags:
        user_content += f"\nTags : {tags}"
    if bpm:
        user_content += f"\nBPM : {bpm}"

    # ── System avec caching
    system = build_system_blocks(
        agent_identity=_AGENT_IDENTITY,
        stable_context=_STABLE_CONTEXT,
        model=MODEL,
    )

    # ── Tools avec caching sur le dernier (unique) outil
    tools = cache_last_tool([_CLASSIFY_TOOL], ttl=safe_ttl(MODEL, "1h"))

    # ── Appel Claude
    response = await create_message(
        agent_name="dna_classifier",
        model=MODEL,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=tools,
        tool_choice={"type": "tool", "name": "classify_track"},
        max_tokens=256,
    )

    # ── Extraction du tool_use
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_track":
            inp = block.input
            return DNAResult(
                dna=inp["dna"],
                confidence=round(float(inp["confidence"]), 4),
                scores={
                    "SUNSET_LOVER":  round(float(inp["scores"].get("SUNSET_LOVER", 0)), 4),
                    "NIGHT_CITY":    round(float(inp["scores"].get("NIGHT_CITY", 0)), 4),
                    "JUNGLE_OSMOSE": round(float(inp["scores"].get("JUNGLE_OSMOSE", 0)), 4),
                },
                method=inp.get("method", "llm"),
            )

    # Fallback si tool_use absent (ne devrait pas arriver avec tool_choice forcé)
    logger.warning("[dna_classifier] Aucun tool_use dans la réponse — fallback SUNSET_LOVER")
    return DNAResult(
        dna="SUNSET_LOVER",
        confidence=0.0,
        scores={"SUNSET_LOVER": 1.0, "NIGHT_CITY": 0.0, "JUNGLE_OSMOSE": 0.0},
        method="fallback",
    )
