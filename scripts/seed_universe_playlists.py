"""
Script : créer les playlists univers en DB et les attacher au profil officiel
==============================================================================

Jungle Osmose / Night City / Sunset Lover / Hit Mix sont des groupements
virtuels côté marketplace. Ce script les matérialise en vraies playlists
dans la table `playlists`, owned by is_official=TRUE (Tom / /u/smyle),
avec tous les tracks correspondants ajoutés via playlist_tracks.

Idempotent : si une playlist avec ce titre appartenant déjà au user cible
existe, elle est ignorée (pas de doublon).

Usage :
    DATABASE_URL="postgresql://..." python3 scripts/seed_universe_playlists.py --dry-run
    DATABASE_URL="postgresql://..." python3 scripts/seed_universe_playlists.py
"""

import argparse
import os
import sys
import uuid

import psycopg2
import psycopg2.extras

UNIVERSES = [
    {"slug": "jungle-osmose",  "title": "JUNGLE OSMOSE"},
    {"slug": "night-city",     "title": "NIGHT CITY"},
    {"slug": "sunset-lover",   "title": "SUNSET LOVER"},
    {"slug": "hit-mix",        "title": "HIT MIX"},
]


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

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("=" * 60)
    print("SEED : playlists univers → profil officiel")
    if args.dry_run:
        print("MODE DRY-RUN")
    print("=" * 60)

    # 1. User cible
    cur.execute("SELECT id, artist_name, email FROM users WHERE is_official = TRUE LIMIT 1")
    target = cur.fetchone()
    if not target:
        print("❌  Aucun user is_official=TRUE trouvé.")
        sys.exit(1)
    target_id = target["id"]
    print(f"✅  Cible : {target['artist_name']} ({target['email']})")

    print()
    total_created = 0
    total_tracks  = 0

    for univ in UNIVERSES:
        slug  = univ["slug"]
        title = univ["title"]

        # Tracks de cet univers
        cur.execute(
            "SELECT id, title FROM tracks WHERE universe = %s ORDER BY title",
            (slug,),
        )
        tracks = cur.fetchall()
        print(f"  {title:<20} → {len(tracks)} tracks")

        if not tracks:
            print(f"    (aucun track — playlist ignorée)")
            continue

        # Vérifier si la playlist existe déjà pour ce user
        cur.execute(
            "SELECT id FROM playlists WHERE owner_id = %s AND title = %s LIMIT 1",
            (target_id, title),
        )
        existing = cur.fetchone()
        if existing:
            print(f"    (playlist déjà existante — ignorée)")
            continue

        if args.dry_run:
            total_created += 1
            total_tracks  += len(tracks)
            continue

        # Créer la playlist
        playlist_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO playlists (id, owner_id, title, visibility)
            VALUES (%s, %s, %s, 'public')
            """,
            (playlist_id, target_id, title),
        )

        # Ajouter les tracks
        for idx, t in enumerate(tracks):
            cur.execute(
                """
                INSERT INTO playlist_tracks (playlist_id, track_id, position)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (playlist_id, t["id"], idx),
            )

        print(f"    ✅  Créée (id={playlist_id}) — {len(tracks)} tracks ajoutés")
        total_created += 1
        total_tracks  += len(tracks)

    if args.dry_run:
        print(f"\nDry-run : {total_created} playlists à créer, {total_tracks} tracks au total.")
        print("Relance sans --dry-run pour appliquer.")
    else:
        conn.commit()
        print()
        print("=" * 60)
        print(f"✅  {total_created} playlists créées — {total_tracks} tracks insérés")
        print(f"   Visibles sur /u/smyle et dans le WATT BOARD")
        print("=" * 60)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
