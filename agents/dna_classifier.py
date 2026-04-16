# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — agents/dna_classifier.py
#
# Agent de classification ADN musical.
# Analyse un morceau (nom, genre, tags, bpm) et lui attribue un univers ADN.
#
# ADN disponibles :
#   SUNSET_LOVER   — golden hour, chaleur, mélodie, plage, lumière
#   NIGHT_CITY     — nuit urbaine, jazz, soul, cinématic, néons
#   JUNGLE_OSMOSE  — tropical, organique, ritual, forêt, nature immersive
#
# Usage :
#   from agents.dna_classifier import classify_track
#   result = classify_track({"name": "Golden Hour Drift", "genre": "lofi"})
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import re
from typing import TypedDict

# ── Types ─────────────────────────────────────────────────────────────────────

class DNAResult(TypedDict):
    dna:        str
    confidence: float          # 0.0 → 1.0
    scores:     dict[str, float]
    method:     str            # 'keyword' | 'bpm' | 'genre' | 'mixed'


# ── Dictionnaire de mots-clés par ADN ────────────────────────────────────────
# Construit à partir des titres réels des playlists SMYLE PLAY.
# Chaque entrée a un poids (1 = normal, 2 = fort signal, 3 = signal dominant).

_DNA_KEYWORDS: dict[str, dict[str, int]] = {

    'SUNSET_LOVER': {
        # Titres réels de la playlist SUNSET LOVER
        'golden': 3, 'amber': 3, 'sunset': 3, 'soleil': 3,
        'ibiza': 2, 'rooftop': 2, 'plage': 2, 'beach': 2,
        'summer': 2, 'cocktails': 2, 'yacht': 2, 'yatch': 2, 'mirage': 2,
        'nylon': 2, 'moonlight': 2, 'riding': 1, 'smooth': 2,
        'senorita': 2, 'levitation': 2, 'minimal': 1, 'dance': 1,
        'private': 1, 'open water': 2, 'water': 1, 'liquide': 2,
        'chrome': 1, 'red': 1, 'party': 1, 'plane': 1,
        # Genres / moods associés
        'tropical house': 3, 'chillout': 2, 'beach house': 3,
        'afro': 2, 'deep house': 1, 'melodic': 2, 'warm': 2,
        'bossa': 2, 'nu jazz': 1, 'lounge': 2, 'soulful': 1,
        'marimba': 1, 'guitar': 1, 'acoustic': 1,
    },

    'NIGHT_CITY': {
        # Titres réels de la playlist NIGHT CITY
        'night': 3, 'midnight': 3, 'nocturne': 3, 'city': 2,
        'jazz': 3, 'soul': 2, 'lofi': 2, 'groove': 2,
        'funk': 2, 'transmission': 2, 'cinematics': 3, 'cinematic': 3,
        'metropolis': 3, 'soulful': 2, 'elevation': 2,
        'lowride': 2, 'rendez vous': 2, 'modern': 1, 'echo': 1,
        'minimal attention': 2, 'clear': 1, 'business': 1,
        'arrested': 2, 'fretless': 2, 'journey': 1,
        'under the moon': 3, 'moon': 2, 'sexy': 1, 'flirt': 1,
        'sweet conversation': 2, 'speak french': 2,
        'study': 1, 'lofi soul': 3, 'hope': 1,
        # Genres / moods associés
        'neo soul': 3, 'jazz hop': 3, 'lo-fi': 3, 'lofi': 3,
        'boom bap': 2, 'urban': 2, 'hip hop': 2, 'rnb': 2,
        'r&b': 2, 'nu soul': 3, 'chill': 1, 'saxophone': 2,
        'bass': 1, 'drums': 1, 'electric': 1, 'keys': 1,
    },

    'JUNGLE_OSMOSE': {
        # Titres réels de la playlist JUNGLE OSMOSE
        'jungle': 3, 'osmose': 3, 'tropical': 3, 'corps tropical': 3,
        'foret': 3, 'forêt': 3, 'rain': 2, 'calm rain': 3,
        'dancehall': 3, 'ritual': 3, 'marimba ritual': 3,
        'caraibes': 3, 'kora': 3, 'nuit kora': 3,
        'lever': 2, 'wake': 2, 'light': 1,
        'blue light': 2, 'neon canopy': 3, 'canopy': 3,
        'forever': 1, 'unforgettable': 1, 'remember': 1,
        'lady': 1, 'happy': 1, 'comprendo': 2, 'mexicana': 2,
        'cold reflexion': 2, 'reflexion': 1,
        'fly': 1, 'cry': 1, 'way': 1, 'instant': 1,
        'jungle fever': 3, 'jungle opening': 3,
        # Genres / moods associés
        'afrobeat': 3, 'world': 3, 'ethnic': 3, 'tribal': 3,
        'organic': 3, 'reggae': 2, 'dub': 2, 'caribbean': 3,
        'percussions': 2, 'percussion': 2, 'nature': 3,
        'ambient': 1, 'binaural': 2, 'immersive': 2,
        'african': 3, 'afro': 2, 'flute': 1,
    },
}

# ── Plages BPM caractéristiques ───────────────────────────────────────────────
# Chaque ADN a ses plages BPM privilégiées (min, max, score_si_dans_plage)

_DNA_BPM_RANGES: dict[str, list[tuple[float, float, float]]] = {
    'SUNSET_LOVER':  [(95, 128, 0.8), (80, 95, 0.5)],
    'NIGHT_CITY':    [(70, 95, 0.9), (60, 70, 0.6), (95, 115, 0.4)],
    'JUNGLE_OSMOSE': [(90, 110, 0.8), (110, 140, 0.6), (70, 90, 0.4)],
}


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Mise en minuscules + suppression caractères spéciaux pour matching."""
    if not text:
        return ''
    text = text.lower()
    text = re.sub(r'[_\-–—]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _score_keywords(tokens: str, dna: str) -> float:
    """
    Score de correspondance mots-clés pour un ADN donné.
    Retourne un score brut (somme des poids des mots-clés trouvés).
    """
    score = 0.0
    for keyword, weight in _DNA_KEYWORDS[dna].items():
        if keyword in tokens:
            score += weight
    return score


def _score_bpm(bpm: float | None, dna: str) -> float:
    """Score BPM pour un ADN (0.0 si pas de BPM ou hors plage)."""
    if bpm is None or bpm <= 0:
        return 0.0
    for bpm_min, bpm_max, score in _DNA_BPM_RANGES[dna]:
        if bpm_min <= bpm <= bpm_max:
            return score
    return 0.0


# ── Fonction principale ───────────────────────────────────────────────────────

def classify_track(track: dict) -> DNAResult:
    """
    Classifie un morceau et retourne son ADN musical.

    Paramètres attendus dans `track` :
        name   (str)  — titre du morceau
        genre  (str)  — genre déclaré par l'artiste (optionnel)
        tags   (str | list) — tags libres (optionnel)
        bpm    (float | int) — BPM si disponible (optionnel)

    Retourne :
        {
            "dna":        "SUNSET_LOVER" | "NIGHT_CITY" | "JUNGLE_OSMOSE",
            "confidence": float,   # 0.0 → 1.0
            "scores":     {"SUNSET_LOVER": float, ...},
            "method":     str
        }
    """
    # ── Construire le corpus de texte à analyser
    name   = _normalize(track.get('name', '') or '')
    genre  = _normalize(track.get('genre', '') or '')
    tags   = track.get('tags', '') or ''
    if isinstance(tags, list):
        tags = ' '.join(tags)
    tags = _normalize(tags)

    corpus = f"{name} {genre} {tags}"

    bpm = track.get('bpm')
    try:
        bpm = float(bpm) if bpm is not None else None
    except (TypeError, ValueError):
        bpm = None

    # ── Calculer les scores bruts par ADN
    dna_list = list(_DNA_KEYWORDS.keys())
    raw_kw  = {d: _score_keywords(corpus, d) for d in dna_list}
    raw_bpm = {d: _score_bpm(bpm, d)         for d in dna_list}

    # ── Score combiné (keywords ×3 + bpm ×1)
    combined = {
        d: raw_kw[d] * 3.0 + raw_bpm[d]
        for d in dna_list
    }

    total = sum(combined.values())

    # ── Normaliser en probabilités (0→1)
    if total > 0:
        scores = {d: round(combined[d] / total, 4) for d in dna_list}
    else:
        # Aucun signal → distribution uniforme
        scores = {d: round(1 / len(dna_list), 4) for d in dna_list}

    # ── ADN gagnant
    best_dna = max(scores, key=lambda d: scores[d])
    confidence = scores[best_dna]

    # ── Méthode utilisée (transparence)
    kw_used  = any(v > 0 for v in raw_kw.values())
    bpm_used = bpm is not None
    if kw_used and bpm_used:
        method = 'mixed'
    elif kw_used:
        method = 'keyword'
    elif bpm_used:
        method = 'bpm'
    else:
        method = 'default'

    return DNAResult(
        dna=best_dna,
        confidence=round(confidence, 4),
        scores=scores,
        method=method,
    )
