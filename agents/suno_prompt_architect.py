# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — agents/suno_prompt_architect.py
#
# Agent de génération de prompts Suno.
# Construit un prompt cohérent avec l'univers ADN pour générer un morceau
# directement dans Suno (https://suno.com).
#
# Structure d'un prompt Suno efficace :
#   [genres principaux], [instruments clés], [mood/ambiance],
#   [tempo indicatif], [éléments sonores distinctifs], [vibe globale]
#
# Usage :
#   from agents.suno_prompt_architect import generate_prompt
#   prompt = generate_prompt("NIGHT_CITY", track_title="Midnight Groove")
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import random
from typing import TypedDict


# ── Types ─────────────────────────────────────────────────────────────────────

class SunoPrompt(TypedDict):
    prompt:       str    # prompt principal à coller dans Suno
    style_tags:   list[str]  # tags de style séparés pour le champ Style
    negative:     str    # éléments à éviter (champ négatif Suno si disponible)
    bpm_hint:     str    # suggestion de tempo
    mood:         str    # résumé du mood en 1 phrase


# ── Bibliothèque de prompts par ADN ──────────────────────────────────────────
# Chaque ADN contient des listes d'éléments tirés au sort pour varier
# les prompts générés tout en restant dans l'univers.

_DNA_LIBRARY: dict[str, dict] = {

    'SUNSET_LOVER': {
        'genres': [
            'tropical house', 'beach house', 'chillout', 'nu disco',
            'melodic house', 'balearic', 'lounge', 'bossa nova',
        ],
        'instruments': [
            'warm electric guitar', 'nylon string guitar', 'marimba',
            'smooth saxophone', 'soft piano', 'congas', 'shakers',
            'steel drum', 'flute', 'muted trumpet',
        ],
        'moods': [
            'golden hour warmth', 'summer nostalgia', 'carefree and dreamy',
            'rooftop at dusk', 'slow motion sunset', 'euphoric melancholy',
            'mediterranean breeze', 'cocktail hour vibes',
        ],
        'textures': [
            'warm analog synth pads', 'vinyl crackle', 'ocean waves in background',
            'soft reverb', 'lush strings', 'gentle plucks', 'breezy atmosphere',
        ],
        'bpm_range': '95–120 BPM',
        'negative':  'aggressive drums, metal, heavy bass, dark atmosphere, industrial',
        'mood_summary': 'Chaleureux, mélodie enveloppante, lumière dorée.',
    },

    'NIGHT_CITY': {
        'genres': [
            'neo soul', 'jazz hop', 'lo-fi jazz', 'cinematic jazz',
            'nu jazz', 'soulful RnB', 'smooth jazz', 'urban jazz',
        ],
        'instruments': [
            'upright bass', 'fretless bass', 'muted trumpet', 'tenor saxophone',
            'electric piano (Rhodes)', 'vinyl drums', 'brushed snare',
            'jazz guitar (clean)', 'Hammond B3 organ', 'vibraphone',
        ],
        'moods': [
            'late night city glow', 'cinematic and introspective',
            'neon reflections on wet asphalt', 'intimate jazz club',
            'noir mystery', 'underground soul session', 'urban melancholy',
            'after midnight groove',
        ],
        'textures': [
            'tape saturation', 'distant city noise', 'rain ambience',
            'low-pass filter warmth', 'vintage reverb', 'subtle lo-fi hiss',
            'deep sidechained kick',
        ],
        'bpm_range': '70–95 BPM',
        'negative':  'tropical, bright, cheerful, electronic rave, heavy metal, distortion',
        'mood_summary': 'Nocturne, cinématique, âme urbaine, néons.',
    },

    'JUNGLE_OSMOSE': {
        'genres': [
            'afrobeat', 'world music', 'tropical fusion', 'ethnic ambient',
            'tribal house', 'reggae dub', 'afro jazz', 'caribbean fusion',
        ],
        'instruments': [
            'kora', 'djembe', 'marimba', 'steel pan', 'talking drum',
            'bass guitar (dub)', 'flute (bamboo)', 'balafon', 'shekere',
            'acoustic guitar (fingerpicking)', 'log drums',
        ],
        'moods': [
            'deep jungle immersion', 'organic and ritualistic',
            'tropical dawn awakening', 'rainforest at night',
            'ancestral and spiritual', 'dancehall energy meets nature',
            'warm Caribbean vibes', 'earthy and grounded',
        ],
        'textures': [
            'rain and nature sounds layered', 'reverb of open space',
            'deep percussive groove', 'humid tropical air feeling',
            'organic bass rumble', 'call-and-response vocal chants',
            'natural resonance',
        ],
        'bpm_range': '90–130 BPM',
        'negative':  'urban, cold, synthetic, industrial, lo-fi, city jazz',
        'mood_summary': 'Organique, tribal, immersif, forêt vivante.',
    },
}

# Template de prompt Suno
_PROMPT_TEMPLATE = (
    "{genres}, {instruments}, {mood}, {texture}, {bpm_range}, "
    "{title_phrase}"
    "cinematic production quality, immersive soundscape"
)


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _pick(lst: list, n: int = 1) -> list:
    """Sélection aléatoire sans répétition."""
    return random.sample(lst, min(n, len(lst)))


def _title_phrase(title: str) -> str:
    """Transforme le titre en indication pour Suno."""
    if not title or not title.strip():
        return ''
    clean = title.strip()
    # Retirer les suffixes techniques courants des fichiers SMYLE PLAY
    for suffix in [' Drift', ' drift', ' copie', ' DRIFT']:
        clean = clean.replace(suffix, '')
    clean = clean.strip()
    if clean:
        return f'inspired by "{clean}", '
    return ''


# ── Fonction principale ───────────────────────────────────────────────────────

def generate_prompt(dna: str, track_title: str = '') -> SunoPrompt:
    """
    Génère un prompt Suno cohérent avec l'ADN donné.

    Paramètres :
        dna         (str) — ex: "SUNSET_LOVER", "NIGHT_CITY", "JUNGLE_OSMOSE"
        track_title (str) — titre du morceau (optionnel, enrichit le prompt)

    Retourne :
        {
            "prompt":     str,        # prompt complet à coller dans Suno
            "style_tags": list[str],  # tags pour le champ Style de Suno
            "negative":   str,        # champ négatif
            "bpm_hint":   str,        # suggestion tempo
            "mood":       str,        # résumé du mood
        }
    """
    lib = _DNA_LIBRARY.get(dna)

    if lib is None:
        # ADN inconnu → prompt générique
        return SunoPrompt(
            prompt='cinematic music, emotional, high production quality',
            style_tags=['cinematic', 'emotional'],
            negative='',
            bpm_hint='100 BPM',
            mood='Universel, cinématique.',
        )

    genres      = ', '.join(_pick(lib['genres'],      3))
    instruments = ', '.join(_pick(lib['instruments'], 4))
    mood        = random.choice(lib['moods'])
    texture     = ', '.join(_pick(lib['textures'],    2))
    title_ph    = _title_phrase(track_title)

    prompt = _PROMPT_TEMPLATE.format(
        genres=genres,
        instruments=instruments,
        mood=mood,
        texture=texture,
        bpm_range=lib['bpm_range'],
        title_phrase=title_ph,
    )

    return SunoPrompt(
        prompt=prompt,
        style_tags=_pick(lib['genres'], 5),
        negative=lib['negative'],
        bpm_hint=lib['bpm_range'],
        mood=lib['mood_summary'],
    )
