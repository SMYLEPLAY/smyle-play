#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — Script de push initial vers GitHub
# Lance ce fichier UNE SEULE FOIS depuis ton Mac pour connecter le repo.
#
# Usage : bash "PUSH_TO_GITHUB.sh"  (depuis le dossier du projet)
# ─────────────────────────────────────────────────────────────────────────────

set -e  # stoppe le script à la première erreur

echo ""
echo "  ┌──────────────────────────────────────────────┐"
echo "  │  SMYLE PLAY — Push initial vers GitHub       │"
echo "  └──────────────────────────────────────────────┘"
echo ""

# Aller dans le dossier du script (où se trouve le projet)
cd "$(dirname "$0")"

# Installer les dépendances Python
echo "  [1/5] Installation des dépendances Python..."
pip3 install -r requirements.txt --break-system-packages -q || pip3 install -r requirements.txt -q
echo "        ✓ Dépendances installées"

# Initialiser git si pas déjà fait
echo "  [2/5] Initialisation Git..."
if [ ! -d ".git" ]; then
  git init
  git branch -M main
else
  # Supprimer le lock file si présent
  rm -f .git/index.lock
  git branch -M main 2>/dev/null || true
fi
echo "        ✓ Git prêt"

# Configurer l'identité (ajuste si besoin)
git config user.email "tom.lecomte1@gmail.com"
git config user.name  "Tom"

# Connecter au remote GitHub
echo "  [3/5] Connexion au repository GitHub..."
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/SOURIRE/sourire-jouer.git
echo "        ✓ Remote configuré"

# Commit initial
echo "  [4/5] Commit initial..."
git add .
git commit -m "SMYLE PLAY v1.0 — Flask + PostgreSQL + Cloudflare R2

Architecture complète :
- app.py: Flask REST API (tracks, auth, plays, feedback, /health)
- config.py: configuration centralisée env vars
- models.py: SQLAlchemy — User, PlayCount, SavedMix, Feedback
- scanner.py: scan local + scan R2 bucket (prod sans fichiers locaux)
- index.html / style.css / script.js: interface SMYLE PLAY
- Procfile: gunicorn prêt Railway/Render
- railway.toml: healthcheck + restart policy
- upload_to_r2.py: script upload audio vers R2
- Fix auto-avance: openedPanelKey séparé de currentPlaylist
- Animations: Jungle gauche-droite délicate, Night City route perspective" 2>/dev/null || echo "        (rien à committer — déjà à jour)"

# Push vers GitHub
echo "  [5/5] Push vers GitHub (authentification requise)..."
echo ""
echo "  ℹ️  GitHub va te demander ton nom d'utilisateur et ton mot de passe."
echo "     Utilise un Personal Access Token (PAT) comme mot de passe :"
echo "     → github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens"
echo "     → Permissions : Contents (Read & Write)"
echo ""
git push -u origin main

echo ""
echo "  ✅  Code poussé sur https://github.com/SOURIRE/sourire-jouer"
echo ""
echo "  Prochaines étapes :"
echo "  1. Railway → New Project → Deploy from GitHub → sourire-jouer"
echo "  2. Railway → Variables → ajouter CLOUD_AUDIO_BASE_URL, DATABASE_URL..."
echo "  3. python3 upload_to_r2.py  (pour uploader les fichiers audio)"
echo ""
