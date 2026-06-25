#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SMYLE SYNC — (MAC uniquement) recale la branche locale `main` sur origin/main
# SANS rien supprimer du dossier de travail (reset --mixed : seul l'index bouge,
# les fichiers du disque ne sont jamais touchés).
#
# ⚠️ À lancer sur le Mac, pas dans le sandbox (le sandbox ne peut pas écrire git).
# Le relais fait déjà ce recalage à chaque cycle ; ce script est un dépannage
# manuel.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

rm -f .git/index.lock 2>/dev/null || true
if ! git fetch origin --quiet; then echo "✗ git fetch a échoué (réseau ?)"; exit 1; fi
git reset --mixed -q origin/main
echo "✓ main recalé sur origin/main ($(git rev-parse --short origin/main)) — fichiers du disque intacts"
