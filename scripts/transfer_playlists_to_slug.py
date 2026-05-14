"""
Script : transférer les playlists univers vers le slug officiel (Tom)
=====================================================================

Les playlists Jungle Osmose / Night City / Sunset Lover / Hit Mix
appartiennent à des comptes "univers" (@smyleplay.local).
Ce script les transfère vers le user is_official=TRUE (ton slug /u/smyle).

Usage :
    DATABASE_URL="postgresql://..." python3 scripts/transfer_playlists_to_slug.py --dry-run
    DATABASE_URL="postgresql://..." python3 scripts/transfer_playlists_to_slug.py
"""

import argparse
import os
import sys

import psycopg2
import psycopg2.extras

TARGET_IS_OFFICIAL = True  # on prend le user is_official=TRUE comme cible


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
    print("TRANSFERT playlists univers → slug officiel")
    if args.dry_run:
        print("MODE DRY-RUN")
    print("=" * 60)

    # 1. Trouver le user cible (is_official=TRUE)
    cur.execute("SELECT id, artist_name, email FROM users WHERE is_official = TRUE LIMIT 1")
    target = cur.fetchone()
    if not target:
        print("❌  Aucun user is_official=TRUE trouvé.")
        sys.exit(1)
    target_id = target["id"]
    print(f"✅  Cible : {target['artist_name']} ({target['email']}) id={target_id}")

    # 2. Trouver les playlists appartenant à des comptes @smyleplay.local
    cur.execute("""
        SELECT p.id, p.title, u.email AS owner_email, u.artist_name AS owner_name
        FROM playlists p
        JOIN users u ON u.id = p.owner_id
        WHERE u.email LIKE '%@smyleplay.local'
        ORDER BY p.title
    """)
    playlists = cur.fetchall()

    if not playlists:
        print("⚠️   Aucune playlist @smyleplay.local trouvée.")
        print("     Vérifie les noms des playlists en DB.")
        sys.exit(0)

    print(f"\nPlaylists à transférer ({len(playlists)}) :")
    for p in playlists:
        print(f"  - {p['title']:<25} (owner actuel : {p['owner_email']})")

    if args.dry_run:
        print("\nDry-run terminé. Relance sans --dry-run pour appliquer.")
        cur.close()
        conn.close()
        return

    confirm = input("\nConfirmer le transfert ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("Annulé.")
        sys.exit(0)

    # 3. Transfert
    playlist_ids = [p["id"] for p in playlists]
    cur.execute(
        "UPDATE playlists SET owner_id = %s WHERE id = ANY(%s)",
        (target_id, playlist_ids),
    )
    print(f"\n✅  {cur.rowcount} playlists transférées vers {target['artist_name']}")

    conn.commit()
    print("\n" + "=" * 60)
    print("✅  TRANSFERT RÉUSSI")
    print("   Les playlists apparaissent maintenant sur /u/smyle")
    print("=" * 60)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
