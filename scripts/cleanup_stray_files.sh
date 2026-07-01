#!/usr/bin/env bash
# =============================================================================
# WATT — Nettoyage des fichiers traînants embarqués par erreur (git add -A)
# =============================================================================
# Le commit de renommage a aspiré des fichiers non suivis. On les sort du repo.
# Aucun impact runtime (ce sont des images/docs non référencées par le code).
#
# - assets/glass/  : design "verre/éclats" ABANDONNÉ (gardé sur ton disque, sorti du repo)
# - Clippings/     : clipping web Obsidian (gardé sur disque, sorti du repo)
# - Sans titre.*   : fichiers Obsidian vides (supprimés)
# - _unlink_test_5 : artefact de test vide (supprimé)
#
# UTILISATION (Terminal, depuis la racine du repo) :
#   bash scripts/cleanup_stray_files.sh
# =============================================================================
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "→ Branche dédiée…"
git switch -c chore/cleanup-stray-files

echo "→ Sortie du repo (gardés sur le disque) : assets/glass, Clippings…"
git rm -r --cached --ignore-unmatch "assets/glass" "Clippings" >/dev/null 2>&1 || true

echo "→ Suppression des fichiers vides/junk…"
git rm --ignore-unmatch "Sans titre.base" "Sans titre.canvas" "_unlink_test_5" >/dev/null 2>&1 || true

echo "→ Mise à jour du .gitignore…"
cat >> .gitignore <<'EOF'

# Nettoyage 2026-06-29 — design abandonné + fichiers Obsidian traînants
assets/glass/
Clippings/
Sans titre.base
Sans titre.canvas
_unlink_test_*
EOF

echo "→ Commit + push…"
git add -A
git commit -m "chore: sortir du repo les fichiers traînants (design abandonné, junk Obsidian)"
git push -u origin chore/cleanup-stray-files

echo ""
echo "✅ Branche poussée : chore/cleanup-stray-files"
echo "   Dis à Claude que c'est poussé — il enchaîne PR + CI + merge."
