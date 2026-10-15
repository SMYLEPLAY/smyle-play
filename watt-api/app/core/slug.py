"""
Dérivation du slug public d'un artiste (URL /artiste/<slug>).

Règle (alignée avec watt_compat._derive_artist_slug) :
  - User-univers (email '<slug>@smyleplay.local')  → slug = local-part
  - Autre user                                      → slug = slugify(artist_name)
  - Sans nom d'artiste                              → `membre-<8 car. de l'id>` (Lot I, RGPD)
"""
from __future__ import annotations

import re
import unicodedata


def slugify(name: str) -> str:
    """Port du _slugify Flask (models.py) — stable et ASCII only."""
    s = unicodedata.normalize("NFD", name or "")
    s = s.encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = s.strip()
    s = re.sub(r"[\s-]+", "-", s)
    return s[:80]


def derive_artist_slug(user) -> str:
    """Slug public d'un artiste (même logique que watt_compat)."""
    email = getattr(user, "email", None) or ""
    if email.endswith("@smyleplay.local"):
        return email.split("@", 1)[0]
    artist_name = getattr(user, "artist_name", None)
    if artist_name and slugify(artist_name):
        return slugify(artist_name)
    # Lot I (RGPD) : plus jamais dérivé de l'email — identifiant neutre.
    uid = getattr(user, "id", None)
    return f"membre-{uid.hex[:8]}" if uid is not None else "membre"
