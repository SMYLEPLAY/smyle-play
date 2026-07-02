#!/bin/bash
# ── SMYLE PLAY — Setup interactif du watcher ─────────────────────────────────
# Usage : double-clique ou ./setup_watcher.sh
# Ce script t'aide à configurer .env, installer les dépendances, et tester.
# ─────────────────────────────────────────────────────────────────────────────

set -e

# Aller dans le dossier du script
cd "$(dirname "$0")"

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
RESET="\033[0m"

print_header() {
  echo
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${BOLD}${CYAN}  $1${RESET}"
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo
}

ok()    { echo -e "${GREEN}✓${RESET} $1"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $1"; }
err()   { echo -e "${RED}✗${RESET} $1"; }
ask()   { echo -ne "${BOLD}$1${RESET} "; }

# ── ÉTAPE 1 : Vérifier Python 3 ──────────────────────────────────────────────
print_header "ÉTAPE 1/6 — Vérification de Python 3"

if ! command -v python3 &>/dev/null; then
  err "Python 3 n'est pas installé. Installe-le depuis https://www.python.org"
  exit 1
fi
PY_VERSION=$(python3 --version)
ok "$PY_VERSION trouvé"

# ── ÉTAPE 2 : Créer / mettre à jour le .env ──────────────────────────────────
print_header "ÉTAPE 2/6 — Configuration du fichier .env"

if [ -f ".env" ]; then
  warn "Un .env existe déjà."
  ask "Veux-tu le remplacer ? (o/N)"
  read -r replace_env
  if [[ "$replace_env" != "o" && "$replace_env" != "O" ]]; then
    ok "On garde le .env existant"
    SKIP_ENV=1
  fi
fi

if [ -z "$SKIP_ENV" ]; then
  echo "Pour récupérer tes clés R2 :"
  echo "  → Railway → projet smyle-play → Variables → copie chaque valeur"
  echo
  echo "Appuie sur Entrée pour laisser une valeur par défaut ou vide."
  echo

  ask "R2_ACCOUNT_ID :"
  read -r R2_ACCOUNT_ID

  ask "R2_ACCESS_KEY :"
  read -r R2_ACCESS_KEY

  ask "R2_SECRET_KEY :"
  read -r R2_SECRET_KEY

  ask "R2_BUCKET [smyle-play-audio] :"
  read -r R2_BUCKET
  R2_BUCKET=${R2_BUCKET:-smyle-play-audio}

  ask "CLOUD_AUDIO_BASE_URL [https://pub-5d7696b1acd74214b3314fdcab40121f.r2.dev] :"
  read -r CLOUD_AUDIO_BASE_URL
  CLOUD_AUDIO_BASE_URL=${CLOUD_AUDIO_BASE_URL:-https://pub-5d7696b1acd74214b3314fdcab40121f.r2.dev}

  cat > .env <<EOF
# SMYLE PLAY — .env local (jamais commité, voir .gitignore)
# Généré par setup_watcher.sh le $(date +"%Y-%m-%d %H:%M:%S")

# ── Cloudflare R2 ────────────────────────────────────────────────────────────
R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
R2_ACCESS_KEY=${R2_ACCESS_KEY}
R2_SECRET_KEY=${R2_SECRET_KEY}
R2_BUCKET=${R2_BUCKET}
CLOUD_AUDIO_BASE_URL=${CLOUD_AUDIO_BASE_URL}

# ── Serveur (optionnel en local) ─────────────────────────────────────────────
PORT=8080
DEBUG=true
FLASK_ENV=development
EOF

  chmod 600 .env
  ok ".env créé (permissions 600 — lisible par toi seul)"
fi

# ── ÉTAPE 3 : Dépendances Python ─────────────────────────────────────────────
print_header "ÉTAPE 3/6 — Installation des dépendances Python"

MISSING=""
python3 -c "import boto3" 2>/dev/null || MISSING="$MISSING boto3"
python3 -c "import dotenv" 2>/dev/null || MISSING="$MISSING python-dotenv"

if [ -n "$MISSING" ]; then
  echo "Packages manquants :$MISSING"
  ask "Installer maintenant via pip3 ? (O/n)"
  read -r install_deps
  if [[ "$install_deps" != "n" && "$install_deps" != "N" ]]; then
    pip3 install --user $MISSING
    ok "Dépendances installées"
  else
    warn "Dépendances non installées — le watcher ne pourra pas tourner"
  fi
else
  ok "boto3 et python-dotenv déjà présents"
fi

# ── ÉTAPE 4 : Test du pipeline ───────────────────────────────────────────────
print_header "ÉTAPE 4/6 — Test du watcher_pipeline.py"

echo "Exécution de python3 watcher_pipeline.py…"
echo
if python3 watcher_pipeline.py; then
  echo
  ok "Pipeline OK — lecture du résultat ci-dessus"
else
  err "Pipeline en erreur — vérifie les messages ci-dessus"
  echo "Les causes les plus fréquentes :"
  echo "  • .env incomplet ou erroné (vérifie R2_ACCESS_KEY et R2_SECRET_KEY)"
  echo "  • boto3 pas installé (relance l'étape 3)"
  echo "  • Bucket R2 inaccessible (vérifie dans Cloudflare)"
  exit 1
fi

# ── ÉTAPE 5 : Installer la détection instantanée (launchd) ───────────────────
print_header "ÉTAPE 5/6 — Détection instantanée via launchd (optionnel)"

PLIST_SRC="$(pwd)/com.smyleplay.watcher.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.smyleplay.watcher.plist"

if [ ! -f "$PLIST_SRC" ]; then
  warn "com.smyleplay.watcher.plist introuvable dans le projet — étape ignorée"
else
  echo "La détection instantanée déclenche un push dans les secondes qui suivent"
  echo "un dépôt de fichier (au lieu d'attendre le cron 1min)."
  ask "Installer le LaunchAgent maintenant ? (O/n)"
  read -r install_plist
  if [[ "$install_plist" != "n" && "$install_plist" != "N" ]]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    cp "$PLIST_SRC" "$PLIST_DST"

    # Décharger avant charger (idempotent)
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    launchctl load "$PLIST_DST"
    ok "LaunchAgent chargé — la détection instantanée est active"
    echo "    Fichier : $PLIST_DST"
    echo "    Pour désactiver : launchctl unload \"$PLIST_DST\""
  else
    warn "LaunchAgent non installé — la détection reste via le cron 1min"
  fi
fi

# ── ÉTAPE 6 : Suno Router (auto-routage ~/Downloads → playlist) ──────────────
print_header "ÉTAPE 6/6 — Suno Router (auto-routage des téléchargements)"

SUNO_SRC="$(pwd)/com.smyleplay.suno-router.plist"
SUNO_DST="$HOME/Library/LaunchAgents/com.smyleplay.suno-router.plist"

if [ ! -f "$SUNO_SRC" ]; then
  warn "com.smyleplay.suno-router.plist introuvable — étape ignorée"
else
  echo "Le Suno Router surveille ~/Downloads et déplace automatiquement"
  echo "les nouveaux WAV/MP3 Suno dans le bon dossier playlist :"
  echo "  • Breadcrumb (add_breadcrumb.py)  → routage parfait"
  echo "  • DNA classifier par nom          → routage heuristique"
  echo "  • A_CLASSER/                      → triage manuel si confiance basse"
  echo
  ask "Installer le Suno Router maintenant ? (O/n)"
  read -r install_suno
  if [[ "$install_suno" != "n" && "$install_suno" != "N" ]]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    cp "$SUNO_SRC" "$SUNO_DST"
    launchctl unload "$SUNO_DST" 2>/dev/null || true
    launchctl load "$SUNO_DST"
    ok "Suno Router chargé — surveille ~/Downloads"
    echo "    Fichier : $SUNO_DST"
    echo "    Pour désactiver : launchctl unload \"$SUNO_DST\""
  else
    warn "Suno Router non installé — tu peux le lancer manuellement : python3 suno_router.py"
  fi
fi

# ── Fin ──────────────────────────────────────────────────────────────────────
print_header "SETUP TERMINÉ"

echo "Workflow quotidien :"
echo "  1. Tu déposes un WAV dans SUNSET LOVER / NIGHT CITY / JUNGLE OSMOSE / HIT MIX"
echo "  2. Détection automatique → upload R2 → regen tracks.json → push GitHub"
echo "  3. Railway redéploie (~2-5 min) → visible en ligne"
echo
echo "Pour forcer un run immédiat depuis Claude :"
echo "  → \"Lance watt-deploy-watcher maintenant\""
echo
echo "Pour lancer le pipeline manuellement :"
echo "  → ./deploy.sh"
echo
ok "Tout est prêt."./
