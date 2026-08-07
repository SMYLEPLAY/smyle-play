# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — watt_orchestrator/agents/suno_prompt_architect.py
#
# Agent LLM de génération de prompts Suno.
# Remplace la version template random de agents/suno_prompt_architect.py
# par un appel Claude qui génère un prompt cohérent et créatif.
#
# Interface : identique à agents.suno_prompt_architect.generate_prompt()
#   generate_prompt(dna: str, track_title: str = "") -> SunoPrompt
#
# Stratégie de cache :
#   BP1 — Tool "generate_suno_prompt" (seul outil) → caché 1h
#   BP2 — Bloc system stable (rôle + bibliothèque ADN + règles) → caché 1h
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

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

class SunoPrompt(TypedDict):
    prompt:     str
    style_tags: list[str]
    negative:   str
    bpm_hint:   str
    mood:       str


# ── Définition du tool (stable → caché 1h) ───────────────────────────────────

_GENERATE_TOOL = {
    "name": "generate_suno_prompt",
    "description": (
        "Génère un prompt Suno optimisé et cohérent avec l'ADN WATT donné. "
        "Inclut les genres, instruments, mood, texture et tempo. "
        "Toujours appeler cet outil — ne pas répondre en texte libre."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Prompt complet à coller dans Suno. Format : "
                    "'genre1, genre2, instrument1, instrument2, mood, texture, BPM_range, "
                    "cinematic production quality, immersive soundscape'"
                ),
            },
            "style_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3 à 5 tags de style pour le champ Style de Suno.",
            },
            "negative": {
                "type": "string",
                "description": "Éléments à éviter, séparés par des virgules.",
            },
            "bpm_hint": {
                "type": "string",
                "description": "Plage de tempo recommandée, ex: '95-120 BPM'.",
            },
            "mood": {
                "type": "string",
                "description": "Résumé du mood en 1 courte phrase descriptive.",
            },
        },
        "required": ["prompt", "style_tags", "negative", "bpm_hint", "mood"],
    },
}

# ── System prompt (stable → caché 1h) ────────────────────────────────────────

_AGENT_IDENTITY = "Tu es l'architecte de prompts Suno de SMYLE PLAY."

_STABLE_CONTEXT = """
## Rôle
Tu génères des prompts Suno de haute qualité qui correspondent exactement
à l'univers ADN WATT demandé. Tu appelles TOUJOURS l'outil generate_suno_prompt.

## Structure d'un prompt Suno efficace
[genres principaux], [instruments clés], [mood/ambiance],
[texture sonore], [plage BPM], [éléments distinctifs],
cinematic production quality, immersive soundscape

## Bibliothèque ADN WATT

### SUNSET_LOVER
Genres : tropical house, beach house, chillout, nu disco, melodic house, balearic, bossa nova
Instruments : warm electric guitar, nylon string guitar, marimba, smooth saxophone,
  soft piano, congas, shakers, steel drum, flute, muted trumpet
Moods : golden hour warmth, summer nostalgia, carefree and dreamy, rooftop at dusk,
  slow motion sunset, euphoric melancholy, mediterranean breeze, cocktail hour vibes
Textures : warm analog synth pads, vinyl crackle, ocean waves in background,
  soft reverb, lush strings, gentle plucks, breezy atmosphere
BPM : 95-120 BPM
Négatif : aggressive drums, metal, heavy bass, dark atmosphere, industrial
Mood summary : Chaleureux, mélodie enveloppante, lumière dorée.

### NIGHT_CITY
Genres : neo soul, jazz hop, lo-fi jazz, cinematic jazz, nu jazz, soulful RnB, smooth jazz
Instruments : upright bass, fretless bass, muted trumpet, tenor saxophone,
  electric piano (Rhodes), vinyl drums, brushed snare, jazz guitar (clean),
  Hammond B3 organ, vibraphone
Moods : late night city glow, cinematic and introspective, neon reflections on wet asphalt,
  intimate jazz club, noir mystery, underground soul session, urban melancholy,
  after midnight groove
Textures : tape saturation, distant city noise, rain ambience,
  low-pass filter warmth, vintage reverb, subtle lo-fi hiss, deep sidechained kick
BPM : 70-95 BPM
Négatif : tropical, bright, cheerful, electronic rave, heavy metal, distortion
Mood summary : Nocturne, cinématique, âme urbaine, néons.

### JUNGLE_OSMOSE
Genres : afrobeat, world music, tropical fusion, ethnic ambient, tribal house, reggae dub
Instruments : kora, djembe, marimba, steel pan, talking drum, bass guitar (dub),
  flute (bamboo), balafon, shekere, acoustic guitar (fingerpicking), log drums
Moods : deep jungle immersion, organic and ritualistic, tropical dawn awakening,
  rainforest at night, ancestral and spiritual, dancehall energy meets nature,
  warm Caribbean vibes, earthy and grounded
Textures : rain and nature sounds layered, reverb of open space, deep percussive groove,
  humid tropical air feeling, organic bass rumble, call-and-response vocal chants,
  natural resonance
BPM : 90-130 BPM
Négatif : urban, cold, synthetic, industrial, lo-fi, city jazz
Mood summary : Organique, tribal, immersif, forêt vivante.

## Règles de génération
1. Sélectionne 2-3 genres, 3-4 instruments, 1 mood et 1-2 textures de la bibliothèque.
2. Varie les combinaisons — ne pas toujours prendre les mêmes éléments en premier.
3. Si un titre de morceau est fourni, l'intégrer comme inspiration :
   'inspired by "<titre>",' dans le prompt.
4. Le prompt final ne dépasse pas 200 caractères.
5. NE PAS répondre en texte libre. TOUJOURS appeler generate_suno_prompt.
"""


# ── Fonction principale ───────────────────────────────────────────────────────

async def generate_prompt(dna: str, track_title: str = "") -> SunoPrompt:
    """
    Génère un prompt Suno via Claude + prompt caching.

    Paramètres :
        dna         — ex: "SUNSET_LOVER", "NIGHT_CITY", "JUNGLE_OSMOSE"
        track_title — titre du morceau (optionnel, enrichit le prompt)

    Retourne un SunoPrompt avec prompt, style_tags, negative, bpm_hint, mood.
    """
    # Fallback si ADN inconnu
    if dna not in ("SUNSET_LOVER", "NIGHT_CITY", "JUNGLE_OSMOSE"):
        logger.warning("[suno_prompt_architect] ADN inconnu '%s' — prompt générique", dna)
        return SunoPrompt(
            prompt="cinematic music, emotional, high production quality",
            style_tags=["cinematic", "emotional"],
            negative="",
            bpm_hint="100 BPM",
            mood="Universel, cinématique.",
        )

    # ── Message user (dynamique, pas de cache)
    user_content = f"ADN : {dna}"
    if track_title and track_title.strip():
        user_content += f"\nTitre du morceau : {track_title.strip()}"

    # ── System avec caching
    system = build_system_blocks(
        agent_identity=_AGENT_IDENTITY,
        stable_context=_STABLE_CONTEXT,
        model=MODEL,
    )

    # ── Tools avec caching sur le dernier (unique) outil
    tools = cache_last_tool([_GENERATE_TOOL], ttl=safe_ttl(MODEL, "1h"))

    # ── Appel Claude
    response = await create_message(
        agent_name="suno_prompt_architect",
        model=MODEL,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=tools,
        tool_choice={"type": "tool", "name": "generate_suno_prompt"},
        max_tokens=512,
    )

    # ── Extraction du tool_use
    for block in response.content:
        if block.type == "tool_use" and block.name == "generate_suno_prompt":
            inp = block.input
            return SunoPrompt(
                prompt=str(inp.get("prompt", "")),
                style_tags=list(inp.get("style_tags", [])),
                negative=str(inp.get("negative", "")),
                bpm_hint=str(inp.get("bpm_hint", "")),
                mood=str(inp.get("mood", "")),
            )

    logger.warning("[suno_prompt_architect] Aucun tool_use — prompt fallback")
    return SunoPrompt(
        prompt="cinematic music, emotional, high production quality",
        style_tags=["cinematic", "emotional"],
        negative="",
        bpm_hint="100 BPM",
        mood="Universel, cinématique.",
    )
