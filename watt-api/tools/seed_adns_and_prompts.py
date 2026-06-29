"""
Phase 3.1 + 3.2 — Seed des 4 DNA Playlist (Adn) + 82 Prompts (1 par track).

Architecture 3 couches actee :
  - Niveau 1 : Prompt     → recette Suno exacte d'UN morceau (1 par track)
  - Niveau 2 : Adn        → signature d'une DNA Playlist (1 par univers)
  - Niveau 3 : DNA global → identite artiste (a creer ulterieurement)

Idempotent :
  - Adn match par artist_id (UNIQUE constraint)
  - Prompt match par (artist_id, title)

Usage (depuis `smyleplay-api/`) :

    docker-compose run --rm api python tools/seed_adns_and_prompts.py
    # ou
    docker-compose run --rm api python tools/seed_adns_and_prompts.py --dry-run

Les prompt_text sont des PLACEHOLDERS realistes, generes depuis le titre du
morceau + la signature sonore de son univers. Ils seront remplaces par les
vrais prompts Suno via une UI d'edition dans le dashboard artiste (backlog).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.adn import Adn  # noqa: E402
from app.models.prompt import Prompt  # noqa: E402
from app.models.track import Track  # noqa: E402
from app.models.user import User  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# Contenu DNA Playlist (4 univers)
# ──────────────────────────────────────────────────────────────────────────

ADN_CONTENT: dict[str, dict] = {
    "sunset-lover@smyleplay.local": {
        "description": (
            "L'ADN SUNSET LOVER capture l'instant ou le soleil glisse sur l'horizon "
            "et ou la nuit commence a se frayer un chemin entre les palmiers. "
            "C'est un univers de deep house chaude, de nu-disco tropicale et de "
            "groove organique, fait pour les terrasses, les rooftops et les "
            "dancefloors a ciel ouvert. Rythmique lente mais magnetique, textures "
            "analogiques, et basslines qui caressent plus qu'elles ne frappent."
        ),
        "usage_guide": (
            "Ideal pour : bandes-son de cocktails, playlists de golden hour, "
            "intros de podcasts lifestyle, fonds sonores de contenu voyage. "
            "BPM cible 108-118. Ambiance : solaire, feutree, sensuelle. "
            "A eviter : mixes cardio, musique d'etude seche."
        ),
        "example_outputs": (
            "22 morceaux references dans l'univers SUNSET LOVER sur Smyle Play, "
            "dont 'Amber Drive Drift', 'Golden Hour Groove', 'Palmiers de Miami'."
        ),
        "price_credits": 300,
    },
    "jungle-osmose@smyleplay.local": {
        "description": (
            "JUNGLE OSMOSE est une signature sonore nee de la rencontre entre les "
            "percussions afrobeat, l'energie du tropical moderne et les basses "
            "profondes de la house sud-africaine. C'est une foret rythmique vivante "
            "ou chaque couche (shakers, kalimbas, synthes tribaux) respire et pulse "
            "comme un organisme. Pense pour faire bouger les corps sans jamais forcer."
        ),
        "usage_guide": (
            "Parfait pour : soirees afro-house, contenus sportifs a energie montante, "
            "videos de voyage intertropicales, sets DJ open-air. "
            "BPM cible 118-126. Ambiance : vivante, vegetale, communautaire. "
            "A eviter : contextes intimistes ou tres feutres."
        ),
        "example_outputs": (
            "30 morceaux references dans l'univers JUNGLE OSMOSE sur Smyle Play, "
            "dont 'Amazonia Drum', 'Afrohouse Canopy', 'Tropicale Osmose'."
        ),
        "price_credits": 300,
    },
    "night-city@smyleplay.local": {
        "description": (
            "NIGHT CITY, c'est la ville a 3h du matin vue depuis le 42e etage. "
            "Un univers lo-fi jazz ou les samples de piano feutre, les claviers "
            "electriques et les grooves paresseux racontent les neons qui clignotent "
            "et les rues vides. Batteries cassees, basses rondes, melancolie urbaine "
            "assumee. Une bande-son pour penser en regardant par la fenetre."
        ),
        "usage_guide": (
            "Ideal pour : playlists d'etude et de focus, podcasts narratifs, "
            "videos cinematiques nocturnes, bandes-son de jeux d'enquete. "
            "BPM cible 72-92. Ambiance : nocturne, introspective, sophistiquee. "
            "A eviter : contextes dynamiques ou festifs."
        ),
        "example_outputs": (
            "20 morceaux references dans l'univers NIGHT CITY sur Smyle Play, "
            "dont 'Low Light', 'Triste', 'Late Night Jazz'."
        ),
        "price_credits": 300,
    },
    "hit-mix@smyleplay.local": {
        "description": (
            "HIT MIX rassemble le meilleur de tous les univers : du beat electro "
            "qui fait mouche, des hooks pop dansants, et cette signature WATT qui "
            "transforme un banger en marque de fabrique. C'est l'ADN qu'on choisit "
            "quand on veut etre diffuse partout : radio, TikTok, trailers, "
            "publicites. Production lechee, impact immediat, refrains qui collent."
        ),
        "usage_guide": (
            "Parfait pour : bandes-son TikTok/Reels, trailers publicitaires, "
            "teasers de marque, playlists club crossover. "
            "BPM cible 120-130. Ambiance : punchy, universelle, accessible. "
            "A eviter : contextes ultra-niche ou experimentaux."
        ),
        "example_outputs": (
            "10 morceaux references dans l'univers HIT MIX sur Smyle Play, "
            "dont 'My Love', 'Triste', 'Late Night'."
        ),
        "price_credits": 300,
    },
}


# ──────────────────────────────────────────────────────────────────────────
# Signature par univers → utilisee pour construire des prompt_text realistes
# ──────────────────────────────────────────────────────────────────────────

UNIVERSE_SIGNATURE: dict[str, dict] = {
    "sunset-lover": {
        "style": "deep house / nu-disco / tropical",
        "bpm": "110-118 BPM",
        "keywords": (
            "warm analog bassline, Rhodes chords, soft shakers and congas, "
            "golden-hour atmosphere, side-chained pads, sunset terrace mood, "
            "laid-back groove, vintage VHS saturation"
        ),
    },
    "jungle-osmose": {
        "style": "afrobeat / afro house / tropical tribal",
        "bpm": "118-126 BPM",
        "keywords": (
            "live congas and shekere, kalimba melody, deep sub-bass, "
            "atmospheric pads, tribal percussion polyrhythms, jungle ambience, "
            "organic rhythm section, communal energy"
        ),
    },
    "night-city": {
        "style": "lo-fi jazz / neo-soul / electric jazz",
        "bpm": "72-92 BPM",
        "keywords": (
            "dusty piano sample, broken boom-bap drums, warm upright bass, "
            "vinyl crackle, muted trumpet loop, late-night rain ambience, "
            "soulful vocal chops, melancholic and introspective mood"
        ),
    },
    "hit-mix": {
        "style": "electro pop / jersey club / dance pop",
        "bpm": "120-130 BPM",
        "keywords": (
            "punchy kick, hard-hitting snare, catchy vocal chop hook, "
            "bright lead synth, sidechain pumping bass, radio-ready mix, "
            "anthem-level pop energy, universal dancefloor appeal"
        ),
    },
}


def build_prompt_text(track_title: str, universe_slug: str) -> str:
    """
    Construit un prompt Suno realiste en placeholder.

    Format :
      "<style>, <bpm>, inspired by <title>. <keywords>. <mood tag>."

    Garantit toujours entre 100 et 1000 chars (bornes resserrees en 0019
    pour coller au plafond d'entree de Suno) grace a la combinaison
    style + bpm + title + keywords + suffixe universe.
    """
    sig = UNIVERSE_SIGNATURE[universe_slug]
    return (
        f"{sig['style']}, {sig['bpm']}, inspired by '{track_title}'. "
        f"{sig['keywords']}. Signature sound of the {universe_slug.upper().replace('-', ' ')} "
        f"universe on Smyle Play."
    )


def build_prompt_title(track_title: str) -> str:
    """
    Genere un titre de Prompt unique a partir du titre du morceau.

    Contrainte DB : title >= 5 chars.
    """
    base = (track_title or "Untitled").strip()
    # Nettoyage simple : on garde la casse, on ajoute un suffixe si trop court
    if len(base) < 5:
        base = f"{base} recipe"
    return base[:190]  # Column max 200


# ──────────────────────────────────────────────────────────────────────────
# Helpers DB
# ──────────────────────────────────────────────────────────────────────────

async def get_universe_user(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_adn(
    session: AsyncSession,
    artist: User,
    content: dict,
    dry_run: bool = False,
) -> str:
    stmt = select(Adn).where(Adn.artist_id == artist.id)
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        if dry_run:
            return "updated"
        existing.description = content["description"]
        existing.usage_guide = content["usage_guide"]
        existing.example_outputs = content["example_outputs"]
        existing.price_credits = content["price_credits"]
        existing.is_published = True
        return "updated"

    if dry_run:
        return "created"

    adn = Adn(
        artist_id=artist.id,
        description=content["description"],
        usage_guide=content["usage_guide"],
        example_outputs=content["example_outputs"],
        price_credits=content["price_credits"],
        is_published=True,
    )
    session.add(adn)
    return "created"


async def upsert_prompt_for_track(
    session: AsyncSession,
    track: Track,
    artist_id,
    dry_run: bool = False,
) -> str:
    """Cree ou met a jour un Prompt a partir d'une Track. Match par artist_id+title."""
    title = build_prompt_title(track.title)
    prompt_text = build_prompt_text(track.title, track.universe or "hit-mix")
    description = f"Recette IA du morceau '{track.title}'."

    stmt = select(Prompt).where(
        (Prompt.artist_id == artist_id) & (Prompt.title == title)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        if dry_run:
            return "updated"
        existing.description = description
        existing.prompt_text = prompt_text
        existing.price_credits = 80
        existing.is_published = True
        return "updated"

    if dry_run:
        return "created"

    prompt = Prompt(
        artist_id=artist_id,
        title=title,
        description=description,
        prompt_text=prompt_text,
        price_credits=80,
        is_published=True,
        pack_eligible=True,
    )
    session.add(prompt)
    return "created"


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

async def run(dry_run: bool) -> int:
    adn_created = adn_updated = 0
    prompt_created = prompt_updated = 0
    missing_users: list[str] = []

    async with SessionLocal() as session:
        # 1) DNA Playlists (niveau 2)
        print("── DNA Playlists (niveau 2) ──")
        for email, content in ADN_CONTENT.items():
            artist = await get_universe_user(session, email)
            if artist is None:
                missing_users.append(email)
                print(f"   ❌ user {email} introuvable — lance d'abord seed_from_tracks_json.py")
                continue

            outcome = await upsert_adn(session, artist, content, dry_run)
            if outcome == "created":
                adn_created += 1
                print(f"   ✓ ADN created  : {artist.artist_name}")
            elif outcome == "updated":
                adn_updated += 1
                print(f"   ↻ ADN updated  : {artist.artist_name}")

        if missing_users:
            print("\n⚠️  users manquants, abandon avant prompts.")
            await session.rollback()
            return 2

        await session.flush()

        # 2) Prompts (niveau 1) — 1 par track
        print("\n── Prompts (niveau 1) — un par morceau ──")
        tracks_stmt = (
            select(Track)
            .where(Track.universe.is_not(None))
            .order_by(Track.universe, Track.title)
        )
        tracks = (await session.execute(tracks_stmt)).scalars().all()

        by_universe: dict[str, int] = {}
        for track in tracks:
            outcome = await upsert_prompt_for_track(session, track, track.artist_id, dry_run)
            if outcome == "created":
                prompt_created += 1
            elif outcome == "updated":
                prompt_updated += 1
            by_universe[track.universe] = by_universe.get(track.universe, 0) + 1

        for univ, n in sorted(by_universe.items()):
            print(f"   ✓ {univ:<14} : {n} prompts traites")

        if dry_run:
            print("\n[dry-run] rollback (aucun changement persiste)")
            await session.rollback()
        else:
            await session.commit()

    print("\n" + "=" * 50)
    print(f"DNA Playlists créés : {adn_created:<3}  MAJ : {adn_updated}")
    print(f"Prompts       créés : {prompt_created:<3}  MAJ : {prompt_updated}")
    print("=" * 50)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="N'ecrit rien.")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.dry_run)))


if __name__ == "__main__":
    main()
