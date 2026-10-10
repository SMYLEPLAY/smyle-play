"""
Génère les icônes de l'application installable (PWA) à partir du LOGO
existant du site : le masque SMYLE dessiné en SVG dans l'en-tête de
index.html (<svg class="header-logo-icon">, perles + yeux + sourire).

Pillow ne lit pas le SVG : le script relève les cercles du logo (centre,
rayon, couleur, opacité) et les redessine en haute définition, avec la même
inclinaison que sur le site (-11°), sur un fond violet de la charte (les
perles du logo sont presque noires : sur fond noir, l'icône serait illisible).

Sorties (ui/pwa/icones/) :
  icone-192.png, icone-512.png          → manifeste (« any »)
  icone-maskable-512.png                → manifeste (« maskable », Android :
                                          logo dans la zone sûre de 80 %)
  apple-touch-icon.png (180 × 180)      → iPhone / iPad, écran d'accueil
  favicon-32.png                        → onglet du navigateur

Usage (depuis la racine du dépôt) :
    python watt-api/tools/generer_icones_pwa.py
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RACINE = Path(__file__).resolve().parents[2]
SORTIE = RACINE / "ui" / "pwa" / "icones"

# Charte (ui/core/tokens.css) : violet #8800ff, fond #050508.
VIOLET_CLAIR = (136, 0, 255)
VIOLET_SOMBRE = (34, 0, 68)
INCLINAISON = -11  # degrés, comme .header-logo-icon (style.css)

_CERCLE = re.compile(r"<circle\s+([^>]*?)/?>", re.S)
_ATTR = re.compile(r'([a-z]+)\s*=\s*"([^"]*)"')


def lire_logo() -> list[dict]:
    """Cercles du logo de l'en-tête de index.html (repère centré du <g>)."""
    html = (RACINE / "index.html").read_text(encoding="utf-8")
    debut = html.index('<svg class="header-logo-icon"')
    fin = html.index("</svg>", debut)
    cercles = []
    for m in _CERCLE.finditer(html[debut:fin]):
        a = dict(_ATTR.findall(m.group(1)))
        cercles.append({
            "x": float(a["cx"]), "y": float(a["cy"]), "r": float(a["r"]),
            "couleur": a.get("fill", "#000000"),
            "opacite": float(a.get("opacity", "1")),
        })
    if len(cercles) < 20:
        sys.exit("Logo introuvable ou incomplet dans index.html")
    return cercles


def _rgb(hexa: str) -> tuple[int, int, int]:
    h = hexa.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def fond(taille: int, *, arrondi: bool) -> Image.Image:
    """Dégradé radial violet (clair au centre, sombre aux bords)."""
    img = Image.new("RGB", (taille, taille))
    px = img.load()
    c = (taille - 1) / 2
    rmax = math.hypot(c, c)
    for y in range(taille):
        for x in range(taille):
            t = min(1.0, math.hypot(x - c, y - c) / rmax) ** 1.2
            px[x, y] = tuple(
                round(VIOLET_CLAIR[i] * (1 - t) + VIOLET_SOMBRE[i] * t) for i in range(3)
            )
    img = img.convert("RGBA")
    if arrondi:
        masque = Image.new("L", (taille, taille), 0)
        ImageDraw.Draw(masque).rounded_rectangle(
            (0, 0, taille - 1, taille - 1), radius=round(taille * 0.22), fill=255
        )
        img.putalpha(masque)
    return img


def dessiner_logo(taille: int, cercles: list[dict], *, part: float) -> Image.Image:
    """Logo seul sur fond transparent ; `part` = diamètre du masque / taille."""
    ss = 4  # sur-échantillonnage pour des bords lisses
    T = taille * ss
    calque = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    # Le masque tient dans un cercle de rayon ~27 unités (perles à 24 + r 2,4).
    echelle = (T * part / 2) / 27.0
    cx = cy = T / 2
    # Halo clair derrière le visage (lisibilité des perles sombres).
    halo = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        (cx - 20 * echelle, cy - 20 * echelle, cx + 20 * echelle, cy + 20 * echelle),
        fill=(200, 150, 255, 70),
    )
    calque = Image.alpha_composite(calque, halo.filter(ImageFilter.GaussianBlur(6 * echelle)))
    d = ImageDraw.Draw(calque, "RGBA")  # mode « RGBA » : les opacités se mélangent
    for c in cercles:
        r, g, b = _rgb(c["couleur"])
        x, y, rr = cx + c["x"] * echelle, cy + c["y"] * echelle, c["r"] * echelle
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(r, g, b, round(255 * c["opacite"])))
    calque = calque.rotate(-INCLINAISON, resample=Image.BICUBIC, center=(cx, cy))
    return calque.resize((taille, taille), Image.LANCZOS)


def icone(taille: int, cercles, *, part: float, arrondi: bool) -> Image.Image:
    img = fond(taille, arrondi=arrondi)
    logo = dessiner_logo(taille, cercles, part=part)
    out = Image.alpha_composite(img, logo)
    if arrondi:
        out.putalpha(img.getchannel("A"))
    return out


def main() -> None:
    cercles = lire_logo()
    SORTIE.mkdir(parents=True, exist_ok=True)
    # « any » : coins arrondis, logo large.
    for t in (192, 512):
        icone(t, cercles, part=0.78, arrondi=True).save(SORTIE / f"icone-{t}.png", optimize=True)
    # « maskable » : fond plein (Android découpe lui-même), logo dans les 80 %.
    icone(512, cercles, part=0.62, arrondi=False).save(
        SORTIE / "icone-maskable-512.png", optimize=True
    )
    # iOS applique ses propres coins : fond plein, pas de transparence.
    icone(180, cercles, part=0.74, arrondi=False).convert("RGB").save(
        SORTIE / "apple-touch-icon.png", optimize=True
    )
    icone(32, cercles, part=0.92, arrondi=True).save(SORTIE / "favicon-32.png", optimize=True)
    for f in sorted(SORTIE.glob("*.png")):
        print(f.relative_to(RACINE), Image.open(f).size)


if __name__ == "__main__":
    main()
