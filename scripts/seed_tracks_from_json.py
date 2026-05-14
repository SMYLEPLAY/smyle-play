"""
Script : seed des 81 tracks depuis tracks.json → DB + création playlists univers
=================================================================================

Ce script :
1. Lit tracks.json à la racine du projet
2. Insère chaque track dans la table `tracks` (idempotent via legacy_id)
3. Crée les 4 playlists univers sur le compte is_official=TRUE
4. Lie les tracks à leur playlist via playlist_tracks

Champs mappés :
  tracks.json         → DB
  id                  → legacy_id  (clé d'idempotence)
  name                → title
  duration            → duration_seconds
  url                 → audio_url  (URL R2 publique directe)
  url[path part]      → r2_key     (pour le proxy /watt/stream/)
  universe (parent)   → universe

Usage :
    cd ~/Desktop/WORK/Smyleplay
    DATABASE_URL="postgresql://..." python3 scripts/seed_tracks_from_json.py --dry-run
    DATABASE_URL="postgresql://..." python3 scripts/seed_tracks_from_json.py
"""

import argparse
import json
import os
import sys
import uuid
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

TRACKS_JSON = os.path.join(os.path.dirname(__file__), "..", "tracks.json")

UNIVERSE_TITLES = {
    "sunset-lover":  "SUNSET LOVER",
    "jungle-osmose": "JUNGLE OSMOSE",
    "night-city":    "NIGHT CITY",
    "hit-mix":       "HIT MIX",
}


def r2_key_from_url(url: str) -> str:
    """Extrait la r2_key depuis l'URL publique R2 (chemin sans le leading slash)."""
    path = urlparse(url).path          # ex: /SUNSET%20LOVER/sw-001%20...wav
    path = unquote(path)               # ex: /SUNSET LOVER/sw-001 — AMBER...wav
    return path.lstrip("/")            # ex: SUNSET LOVER/sw-001 — AMBER...wav


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("❌  DATABASE_URL manquant.")
        sys.exit(1)
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]

    # Charger tracks.json
    tracks_path = os.path.abspath(TRACKS_JSON)
    if not os.path.exists(tracks_path):
        print(f"❌  tracks.json introuvable : {tracks_path}")
        sys.exit(1)
    with open(tracks_path) as f:
        raw = json.load(f)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("=" * 60)
    print("SEED : tracks.json → DB + playlists univers")
    if args.dry_run:
        print("MODE DRY-RUN")
    print("=" * 60)

    # 1. User cible
    cur.execute("SELECT id, artist_name, email FROM users WHERE is_official = TRUE LIMIT 1")
    owner = cur.fetchone()
    if not owner:
        print("❌  Aucun user is_official=TRUE trouvé.")
        sys.exit(1)
    owner_id = owner["id"]
    print(f"✅  Propriétaire : {owner['artist_name']} ({owner['email']})")
    print()

    # 2. Parcourir tracks.json et préparer les inserts
    all_tracks_by_universe = {}
    total_new = 0
    total_existing = 0

    for univ_slug, meta in raw.items():
        tracks_in_univ = meta.get("tracks", [])
        all_tracks_by_universe[univ_slug] = []

        for t in tracks_in_univ:
            legacy_id  = t.get("id", "")
            title      = t.get("name") or t.get("title") or legacy_id
            audio_url  = t.get("url", "")
            duration   = t.get("duration")
            r2_key     = r2_key_from_url(audio_url) if audio_url else None

            # Vérifier si déjà en DB
            cur.execute("SELECT id FROM tracks WHERE legacy_id = %s", (legacy_id,))
            existing = cur.fetchone()

            if existing:
                total_existing += 1
                all_tracks_by_universe[univ_slug].append(existing["id"])
                continue

            # Nouveau track
            new_id = uuid.uuid4()
            all_tracks_by_universe[univ_slug].append(new_id)
            total_new += 1

            if not args.dry_run:
                cur.execute(
                    """
                    INSERT INTO tracks
                        (id, title, audio_url, artist_id, universe,
                         duration_seconds, r2_key, legacy_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (str(new_id), title, audio_url, str(owner_id), univ_slug,
                     duration, r2_key, legacy_id),
                )

        print(f"  {UNIVERSE_TITLES.get(univ_slug, univ_slug):<20} "
              f"{len(tracks_in_univ)} tracks "
              f"({sum(1 for t in tracks_in_univ if not cur.execute('SELECT 1 FROM tracks WHERE legacy_id=%s',(t.get('id',''),)) or True)} à vérifier)")

    # Re-scan pour afficher les stats proprement
    print()
    print(f"  Tracks à insérer  : {total_new}")
    print(f"  Déjà en DB        : {total_existing}")

    if args.dry_run:
        print()
        print("Dry-run terminé. Relance sans --dry-run pour appliquer.")
        cur.close()
        conn.close()
        return

    # 3. Créer les playlists + lier les tracks
    print()
    print("Création des playlists :")
    for univ_slug, track_ids in all_tracks_by_universe.items():
        title = UNIVERSE_TITLES.get(univ_slug, univ_slug.upper())

        # Idempotent : vérifier si la playlist existe
        cur.execute(
            "SELECT id FROM playlists WHERE owner_id = %s AND title = %s LIMIT 1",
            (owner_id, title),
        )
        existing_pl = cur.fetchone()

        if existing_pl:
            playlist_id = existing_pl["id"]
            print(f"  {title:<20} playlist existante — mise à jour des tracks")
        else:
            playlist_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO playlists (id, owner_id, title, visibility) VALUES (%s,%s,%s,'public')",
                (str(playlist_id), str(owner_id), title),
            )
            print(f"  {title:<20} ✅  playlist créée")

        # Lier les tracks (ON CONFLICT DO NOTHING = idempotent)
        for pos, track_id in enumerate(track_ids):
            cur.execute(
                """
                INSERT INTO playlist_tracks (playlist_id, track_id, position)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (str(playlist_id), str(track_id), pos),
            )

        print(f"    → {len(track_ids)} tracks liés")

    conn.commit()
    print()
    print("=" * 60)
    print(f"✅  SEED TERMINÉ")
    print(f"   {total_new} tracks insérés, {total_existing} déjà présents")
    print(f"   4 playlists disponibles sur /u/smyle")
    print(f"   Ajoute les prompts depuis le WATT BOARD pour vendre les recettes")
    print("=" * 60)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
