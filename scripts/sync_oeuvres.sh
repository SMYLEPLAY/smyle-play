#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# sync_oeuvres.sh — LA BOUCLE : réconcilie TOUT le profil en œuvres.
#
# Pour chaque univers (Night City / Jungle Osmose / Sunset Lover) :
#   1. attache les recettes Suno manquantes aux sons (attach_recipes.py)
#   2. crée les images vendables depuis les covers + les lie aux sons
#      (backfill_oeuvres.py)
#
# 100 % IDEMPOTENT : sons déjà avec recette → skip ; œuvres déjà liées → skip
# (anti-doublon). Relançable à volonté, cron-able. Tout son qui a une musique
# vendable ET une image vendable finit en œuvre scindée + achetable direct.
#
# Pré-requis (env) :
#   WATT_API_BASE   ex: https://web-production-e30c8c.up.railway.app
#   WATT_EMAIL      compte propriétaire des sons (ex: smyletheplan@gmail.com)
#   (mot de passe demandé à l'écran, OU WATT_TOKEN=... pour du non-interactif/cron)
#
# Usage :
#   export WATT_API_BASE="https://web-production-e30c8c.up.railway.app"
#   export WATT_EMAIL="smyletheplan@gmail.com"
#   bash scripts/sync_oeuvres.sh              # dry-run (n'écrit rien)
#   bash scripts/sync_oeuvres.sh --execute    # applique
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

EXEC="${1:-}"
COVERS_BASE="${COVERS_BASE:-/Users/tommio/Desktop/WORK/SMYLE}"
LIB="OBSIDIAN/02_WATT/ADN_VISUEL"
PLAT="${PLAT:-dalle}"
VER="${VER:-GPT-4o}"
PRICE="${PRICE:-30}"

run() { echo; echo "▶ $*"; "$@"; }

# ── 1) Recettes manquantes (Jungle + Sunset ont des JSON ; Night City a déjà
#       ses recettes → pas de JSON, on saute l'attache). ──────────────────────
for U in jungle sunset; do
  if [ -f "data/recipes_backfill_${U}.json" ]; then
    run python3 scripts/attach_recipes.py --recipes "data/recipes_backfill_${U}.json" $EXEC
  fi
done

# ── 2) Covers → images vendables + liaison œuvre, par univers. ───────────────
run python3 scripts/backfill_oeuvres.py \
  --covers "${COVERS_BASE}/cover night city" \
  --library "${LIB}/PROMPT_LIBRARY_Night-City_PUBLIC.md" \
  --platform "$PLAT" --model-version "$VER" --price "$PRICE" $EXEC

run python3 scripts/backfill_oeuvres.py \
  --covers "${COVERS_BASE}/Cover jungle osmose " \
  --library "${LIB}/PROMPT_LIBRARY_Jungle-Osmose_PUBLIC.md" \
  --platform "$PLAT" --model-version "$VER" --price "$PRICE" $EXEC

run python3 scripts/backfill_oeuvres.py \
  --covers "${COVERS_BASE}/Cover sunset lover " \
  --library "${LIB}/PROMPT_LIBRARY_Sunset-Lover_PUBLIC.md" \
  --platform "$PLAT" --model-version "$VER" --price "$PRICE" $EXEC

echo; echo "✅ sync_oeuvres terminé. (dry-run si tu n'as pas passé --execute)"
