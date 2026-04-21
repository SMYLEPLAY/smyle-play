#!/bin/bash
# ── SMYLE PLAY — Déploiement manuel / trigger launchd ────────────────────────
# Usage :
#   ./deploy.sh                 → pipeline + git push
#   ./deploy.sh --cleanup-r2    → + nettoyage R2 (fichiers orphelins)
#   ./deploy.sh --dry-run       → simule sans écrire/pousser
# ─────────────────────────────────────────────────────────────────────────────

set -e

# Aller dans le dossier du script (nécessaire quand lancé par launchd)
cd "$(dirname "$0")"

PROJECT_DIR="$(pwd)"
LOG_DIR="$PROJECT_DIR/.watcher-logs"
mkdir -p "$LOG_DIR"

TS=$(date +"%Y-%m-%d %H:%M:%S")
LOG_FILE="$LOG_DIR/deploy.log"

# Lock pour éviter deux runs simultanés (launchd + cron + manuel)
LOCK="$LOG_DIR/deploy.lock"
if [ -e "$LOCK" ]; then
  PID=$(cat "$LOCK" 2>/dev/null || echo "")
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "[$TS] Déjà un run en cours (PID $PID) — abandon" | tee -a "$LOG_FILE"
    exit 0
  fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

echo "[$TS] ── Deploy start ──" | tee -a "$LOG_FILE"

# ── 1. Pipeline Python (détection + upload R2 + regen tracks.json) ──────────
PIPELINE_ARGS="$@"
set +e
PIPELINE_OUT=$(python3 watcher_pipeline.py $PIPELINE_ARGS 2>&1)
PIPELINE_EXIT=$?
set -e

echo "$PIPELINE_OUT" | tee -a "$LOG_FILE"

if [ $PIPELINE_EXIT -ne 0 ]; then
  echo "[$TS] Pipeline KO (exit $PIPELINE_EXIT)" | tee -a "$LOG_FILE"
  exit $PIPELINE_EXIT
fi

# Dry-run : on s'arrête là
if [[ "$*" == *"--dry-run"* ]]; then
  echo "[$TS] Dry-run terminé — pas de git push" | tee -a "$LOG_FILE"
  exit 0
fi

# ── 2. Git — check, commit, push seulement si changements ────────────────────
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "[$TS] Pas un repo git — skip push" | tee -a "$LOG_FILE"
  exit 0
fi

CHANGES=$(git status --porcelain)
if [ -z "$CHANGES" ]; then
  echo "[$TS] Aucun changement local — rien à pousser" | tee -a "$LOG_FILE"
  exit 0
fi

# Message de commit intelligent en fonction de ce qui a changé
COMMIT_MSG="chore: auto-deploy $(date +%Y-%m-%d)"
if echo "$CHANGES" | grep -q "tracks.json"; then
  COMMIT_MSG="content: update tracks.json ($(date +%Y-%m-%d))"
fi
if echo "$CHANGES" | grep -qE "\.(py|js|html|css)$"; then
  COMMIT_MSG="update: code + content ($(date +%Y-%m-%d))"
fi

git add -A
git commit -m "$COMMIT_MSG" | tee -a "$LOG_FILE" || true

# Push avec retry (réseau flakey, laptop qui se réveille, etc.)
PUSH_OK=0
for attempt in 1 2 3; do
  if git push origin main 2>&1 | tee -a "$LOG_FILE"; then
    PUSH_OK=1
    break
  fi
  echo "[$TS] Push attempt $attempt failed — retry in 5s" | tee -a "$LOG_FILE"
  sleep 5
done

if [ $PUSH_OK -eq 0 ]; then
  echo "[$TS] Push échoué après 3 tentatives" | tee -a "$LOG_FILE"
  exit 1
fi

echo "[$TS] ── Deploy OK ──" | tee -a "$LOG_FILE"
