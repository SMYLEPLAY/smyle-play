#!/usr/bin/env bash
# =============================================================================
# WATT — Renommage du dossier de code "smyleplay-api" -> "watt-api"
# =============================================================================
# Cette opération est DEPLOY-CRITIQUE : elle touche le démarrage Railway et la
# CI. Elle doit être ATOMIQUE (tout dans un seul commit) et validée par la CI
# VERTE avant tout merge sur main.
#
# Aucun import Python ne dépend du nom du dossier (le package importé est `app`),
# donc seuls des CHEMINS changent. Vérifié le 2026-06-29.
#
# PRÉ-REQUIS :
#   1. Le relais de déploiement est au repos (aucune tâche en cours).
#   2. L'arbre git est propre (git status ne montre rien d'important non commité).
#
# UTILISATION (dans le Terminal, depuis la racine du repo) :
#   bash scripts/rename_api_to_watt.sh
# Puis attendre la CI VERTE sur la branche, et seulement après, merger.
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [ ! -d "smyleplay-api" ]; then
  echo "❌ Dossier smyleplay-api introuvable — renommage déjà fait ou mauvais dossier."
  exit 1
fi

echo "→ Création de la branche dédiée…"
git switch -c chore/rename-api-folder-watt

echo "→ Déplacement du dossier (git mv, l'historique est conservé)…"
git mv smyleplay-api watt-api

echo "→ Mise à jour des chemins dans les fichiers concernés…"
FILES=(
  railway.toml
  main.py
  .gitignore
  README.md
  data/seeds/README.md
  scripts/smyle-enqueue.sh
  artiste.js
  .github/workflows/ci.yml
  .github/workflows/e2e.yml
  watt-api/pyproject.toml
)
for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    sed -i '' 's/smyleplay-api/watt-api/g' "$f"
    echo "   ✓ $f"
  fi
done

echo "→ Nettoyage de l'egg-info périmé (régénéré au build)…"
git rm -r --cached --ignore-unmatch watt-api/smyleplay_api.egg-info >/dev/null 2>&1 || true

echo "→ Vérif : plus aucune référence au dossier 'smyleplay-api' (hors logs .relay) ?"
if grep -rl "smyleplay-api" . 2>/dev/null \
   | grep -vE "/\.git/|venv/|egg-info|__pycache__|\.pyc|graphify-out|OBSIDIAN|\.claude/worktrees|/\.relay/" \
   | grep -q .; then
  echo "   ⚠️  Il reste des références — à vérifier avant de committer :"
  grep -rln "smyleplay-api" . 2>/dev/null \
    | grep -vE "/\.git/|venv/|egg-info|__pycache__|\.pyc|graphify-out|OBSIDIAN|\.claude/worktrees|/\.relay/"
else
  echo "   ✓ Aucune référence restante."
fi

echo "→ Commit + push…"
git add -A
git commit -m "chore: rename code folder smyleplay-api -> watt-api"
git push -u origin chore/rename-api-folder-watt

echo ""
echo "✅ Branche poussée : chore/rename-api-folder-watt"
echo "   1) Va sur GitHub Actions et attends que la CI soit VERTE."
echo "   2) Seulement si la CI est verte : merge la branche sur main."
echo "   3) Railway déploiera automatiquement la prod depuis main."
