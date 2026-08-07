"""
Script de migration : profil Smyle officiel → slug smyle-xo (Tom)
=================================================================

Ce script :
1. Trouve le profil officiel (smyle@smyleplay.com)
2. Trouve le profil cible (slug smyle-xo, artist_name contient "xo")
3. Transfère TOUS les contenus : tracks, playlists, adns, dnas, voices, prompts
4. Passe le profil cible en is_official=TRUE + renomme en "Smyle" (slug = smyle)
5. Désactive l'ancien compte officiel (is_official=FALSE)

Usage :
    DATABASE_URL="postgresql://..." python scripts/migrate_smyleoff_to_slug.py

    # Mode dry-run (aucune modif, juste afficher ce qui serait fait) :
    DATABASE_URL="postgresql://..." python scripts/migrate_smyleoff_to_slug.py --dry-run
"""

import argparse
import sys
import uuid

import psycopg2
import psycopg2.extras

# ── Config ──────────────────────────────────────────────────────────────────
SMYLE_OFFICIAL_EMAIL = "smyle@smyleplay.com"
TARGET_ARTIST_NAME_CONTAINS = "xo"          # smyle xo
NEW_ARTIST_NAME = "Smyle"                   # slug final = "smyle"

TABLES_WITH_ARTIST_ID = ["tracks", "adns", "dnas", "voices", "prompts"]
TABLES_WITH_OWNER_ID  = ["playlists"]
# ────────────────────────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    import re, unicodedata
    s = unicodedata.normalize("NFD", name or "")
    s = s.encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = s.strip()
    s = re.sub(r"[\s-]+", "-", s)
    return s[:80]


def main():
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Aucune écriture en DB")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌  DATABASE_URL manquant. Exemple :")
        print("   DATABASE_URL='postgresql://...' python scripts/migrate_smyleoff_to_slug.py")
        sys.exit(1)

    # psycopg2 veut postgresql:// pas postgres://
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("=" * 60)
    print("MIGRATION : Smyle Officiel → slug smyle-xo")
    if args.dry_run:
        print("MODE DRY-RUN : aucune modification ne sera appliquée")
    print("=" * 60)

    # ── 1. Trouver les deux users ────────────────────────────────────────
    cur.execute("SELECT id, email, artist_name, is_official FROM users WHERE email = %s",
                (SMYLE_OFFICIAL_EMAIL,))
    official = cur.fetchone()
    if not official:
        print(f"❌  Profil officiel introuvable (email: {SMYLE_OFFICIAL_EMAIL})")
        sys.exit(1)
    official_id = official["id"]
    print(f"✅  Profil officiel trouvé : {official['artist_name']} (id={official_id})")

    cur.execute(
        "SELECT id, email, artist_name, is_official FROM users WHERE LOWER(artist_name) LIKE %s",
        (f"%{TARGET_ARTIST_NAME_CONTAINS.lower()}%",),
    )
    targets = cur.fetchall()
    if not targets:
        print(f"❌  Aucun user avec artist_name contenant '{TARGET_ARTIST_NAME_CONTAINS}'")
        sys.exit(1)
    if len(targets) > 1:
        print(f"⚠️   Plusieurs candidats trouvés :")
        for t in targets:
            print(f"     - {t['artist_name']} ({t['email']}) id={t['id']}")
        print("Édite la variable TARGET_ARTIST_NAME_CONTAINS pour affiner.")
        sys.exit(1)
    target = targets[0]
    target_id = target["id"]
    print(f"✅  Profil cible trouvé : {target['artist_name']} ({target['email']}) id={target_id}")

    if str(official_id) == str(target_id):
        print("❌  Les deux profils sont le même user. Rien à faire.")
        sys.exit(0)

    # ── 2. Compter le contenu à migrer ──────────────────────────────────
    print()
    print("Contenu à migrer :")
    migration_map = {}

    for table in TABLES_WITH_ARTIST_ID:
        try:
            cur.execute(f"SELECT COUNT(*) as n FROM {table} WHERE artist_id = %s", (official_id,))
            row = cur.fetchone()
            count = row["n"] if row else 0
            migration_map[table] = {"col": "artist_id", "count": count}
            print(f"  {table:<20} artist_id  : {count} lignes")
        except psycopg2.errors.UndefinedTable:
            conn.rollback()  # reset after error
            print(f"  {table:<20} (table absente — ignorée)")
            conn.autocommit = False

    for table in TABLES_WITH_OWNER_ID:
        try:
            cur.execute(f"SELECT COUNT(*) as n FROM {table} WHERE owner_id = %s", (official_id,))
            row = cur.fetchone()
            count = row["n"] if row else 0
            migration_map[table] = {"col": "owner_id", "count": count}
            print(f"  {table:<20} owner_id   : {count} lignes")
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            print(f"  {table:<20} (table absente — ignorée)")
            conn.autocommit = False

    # Cas ADN : UNIQUE constraint sur artist_id — vérifier conflit
    cur.execute("SELECT id FROM adns WHERE artist_id = %s", (target_id,))
    target_has_adn = cur.fetchone() is not None
    if target_has_adn and migration_map.get("adns", {}).get("count", 0) > 0:
        print()
        print("⚠️   CONFLIT ADN : le profil cible a déjà un ADN.")
        print("     L'ADN de l'officiel NE SERA PAS transféré (UNIQUE constraint).")
        print("     Tu devras fusionner manuellement si besoin.")
        migration_map["adns"]["skip_conflict"] = True

    print()
    if args.dry_run:
        print("Dry-run terminé. Relance sans --dry-run pour appliquer.")
        cur.close()
        conn.close()
        return

    confirm = input("Confirmer la migration ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("Annulé.")
        sys.exit(0)

    # ── 3. Migration ─────────────────────────────────────────────────────
    try:
        for table, meta in migration_map.items():
            col = meta["col"]
            if meta.get("count", 0) == 0:
                continue
            if meta.get("skip_conflict"):
                print(f"  SKIP {table} (conflit ADN)")
                continue
            cur.execute(
                f"UPDATE {table} SET {col} = %s WHERE {col} = %s",
                (target_id, official_id),
            )
            print(f"  ✅  {table} → {cur.rowcount} lignes mises à jour")

        # Passer le profil cible en is_official=TRUE + renommer
        cur.execute(
            "UPDATE users SET is_official = TRUE, artist_name = %s WHERE id = %s",
            (NEW_ARTIST_NAME, target_id),
        )
        print(f"  ✅  users (cible) → is_official=TRUE, artist_name='{NEW_ARTIST_NAME}'")

        # Désactiver l'ancien compte officiel
        cur.execute(
            "UPDATE users SET is_official = FALSE WHERE id = %s",
            (official_id,),
        )
        print(f"  ✅  users (officiel) → is_official=FALSE")

        conn.commit()
        print()
        print("=" * 60)
        new_slug = slugify(NEW_ARTIST_NAME)
        print(f"✅  MIGRATION RÉUSSIE")
        print(f"   Ton profil est maintenant accessible sur /u/{new_slug}")
        print(f"   is_official=TRUE → il apparaît en tête de la marketplace")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"❌  ERREUR — rollback effectué : {e}")
        raise

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
