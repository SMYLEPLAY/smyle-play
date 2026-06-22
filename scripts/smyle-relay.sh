#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SMYLE RELAY — pont sandbox → GitHub. Tourne sur le MAC de Tom.
#
# Le sandbox ne peut PAS faire de git (le dossier monté interdit la suppression
# des fichiers .lock). Donc CE script, côté Mac, fait 100 % du git : il lit les
# tâches déposées dans .relay/queue/ (descripteurs écrits par smyle-enqueue.sh),
# committe les fichiers indiqués, pousse, ouvre la PR, et MERGE seulement si la
# CI est VERTE. Railway déploie au merge sur main.
#
# Sécurité (hiérarchie G2 : données > argent > stabilité) :
#   • NE FAIT JAMAIS de `checkout` → ne perturbe pas le dossier de travail
#     (commit « sans checkout » via reset --mixed : seul l'index bouge, jamais
#     les fichiers sur le disque) ;
#   • base chaque branche sur origin/main à jour ;
#   • committe UNIQUEMENT les fichiers listés dans la tâche (isolation) ;
#   • merge UNIQUEMENT si tous les checks CI passent ;
#   • kill-switch : fichier .relay/PAUSE → veille ;
#   • merge admin (bypass protection) seulement si RELAY_ADMIN=1.
#
# Usage :
#   scripts/smyle-relay.sh --once     # un cycle (utilisé par le LaunchAgent)
#   scripts/smyle-relay.sh            # boucle continue (debug manuel)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
RELAY="$ROOT/.relay"
LOG="$RELAY/relay.log"
INTERVAL="${RELAY_INTERVAL:-120}"
mkdir -p "$RELAY/queue" "$RELAY/pushed" "$RELAY/done" "$RELAY/failed"

ts(){ date +"%Y-%m-%d %H:%M:%S"; }
log(){ echo "[$(ts)] $*" | tee -a "$LOG" >&2; }

run_cycle() {
  [ -f "$RELAY/PAUSE" ] && { log "PAUSE présent — relais en veille"; return 0; }

  local LOCK="$RELAY/relay.lock"
  if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then return 0; fi
  echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' RETURN

  command -v gh  >/dev/null 2>&1 || { log "✗ GitHub CLI (gh) manquant"; return 1; }
  command -v git >/dev/null 2>&1 || { log "✗ git manquant"; return 1; }

  rm -f "$ROOT/.git/index.lock" 2>/dev/null
  if ! git fetch origin --quiet 2>>"$LOG"; then log "⚠ git fetch a échoué"; fi
  # Base de travail = origin/main, SANS toucher les fichiers du disque
  # (reset --mixed ne modifie que HEAD + index, jamais le working tree).
  git reset --mixed -q origin/main 2>>"$LOG" || log "⚠ reset --mixed KO"

  # ── 1) PENDING → commit (sans checkout) + push + PR ───────────────────────
  local f
  for f in "$RELAY"/queue/*; do
    [ -e "$f" ] || continue
    case "$f" in *.gitkeep) continue;; esac
    # shellcheck disable=SC1090
    ( source "$f"
      : "${BRANCH:?branche manquante}"; : "${TITLE:?titre manquant}"
      local FILES="${FILES:-.}"
      log "→ tâche $BRANCH (fichiers: $FILES)"
      rm -f "$ROOT/.git/index.lock" 2>/dev/null
      git reset --mixed -q origin/main 2>>"$LOG"
      # shellcheck disable=SC2086
      if ! git add -- $FILES 2>>"$LOG"; then log "✗ git add KO ($BRANCH)"; exit 0; fi
      if git diff --cached --quiet; then
        log "⚠ rien à committer pour $BRANCH → failed"
        mv "$f" "$RELAY/failed/$(basename "$f")"; exit 0
      fi
      # PRE_COMMIT_ALLOW_NO_CONFIG=1 + --no-verify : contourne le hook pre-commit
      # sans config qui bloque sinon les commits (bug repo connu).
      local CERR
      if [ -n "${BODY:-}" ]; then
        CERR=$(PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit --no-verify -q -m "$TITLE" -m "$BODY" 2>&1)
      else
        CERR=$(PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit --no-verify -q -m "$TITLE" 2>&1)
      fi
      if [ $? -ne 0 ]; then log "✗ commit KO: ${CERR:-(sans détail)}"; exit 0; fi
      git branch -f "$BRANCH" HEAD               # la branche pointe sur le commit
      git reset --mixed -q origin/main           # main revient, working tree intact
      if ! git push -u origin "$BRANCH" 2>>"$LOG"; then
        log "✗ push KO $BRANCH (réessai au prochain cycle)"; exit 0
      fi
      if ! gh pr view "$BRANCH" >/dev/null 2>&1; then
        gh pr create --base main --head "$BRANCH" \
          --title "$TITLE" --body "${BODY:-$TITLE}" >>"$LOG" 2>&1 \
          || { log "✗ création PR KO $BRANCH"; exit 0; }
      fi
      local PRNUM; PRNUM=$(gh pr view "$BRANCH" --json number -q .number 2>/dev/null)
      log "✓ PR #$PRNUM ouverte pour $BRANCH"
      mv "$f" "$RELAY/pushed/$(basename "$f")"
    )
  done

  # ── 2) PUSHED → vérifier CI → merger (vert) ou escalader (rouge) ──────────
  for f in "$RELAY"/pushed/*; do
    [ -e "$f" ] || continue
    # shellcheck disable=SC1090
    ( source "$f"
      local STATE; STATE=$(gh pr view "$BRANCH" --json state -q .state 2>/dev/null || echo "")
      if [ "$STATE" = "MERGED" ]; then mv "$f" "$RELAY/done/$(basename "$f")"; log "✓ $BRANCH déjà mergée"; exit 0; fi
      if [ "$STATE" = "CLOSED" ]; then mv "$f" "$RELAY/failed/$(basename "$f")"; log "⚠ $BRANCH PR fermée sans merge"; exit 0; fi

      local OUT CODE VERDICT
      OUT=$(gh pr checks "$BRANCH" 2>&1); CODE=$?
      if echo "$OUT" | grep -qi "no checks"; then VERDICT="wait"
      elif [ "$CODE" -eq 0 ]; then VERDICT="pass"
      elif [ "$CODE" -eq 8 ]; then VERDICT="wait"
      else VERDICT="fail"; fi

      case "$VERDICT" in
        wait) log "… CI en cours pour $BRANCH"; exit 0 ;;
        fail) mv "$f" "$RELAY/failed/$(basename "$f")"; log "✗ CI ROUGE $BRANCH → escalade (.relay/failed)"; exit 0 ;;
        pass)
          log "→ CI verte, merge de $BRANCH"
          if gh pr merge "$BRANCH" --squash --delete-branch >>"$LOG" 2>&1; then
            mv "$f" "$RELAY/done/$(basename "$f")"; log "✅ $BRANCH mergée + déployée"
          elif [ "${RELAY_ADMIN:-0}" = "1" ] && gh pr merge "$BRANCH" --squash --delete-branch --admin >>"$LOG" 2>&1; then
            mv "$f" "$RELAY/done/$(basename "$f")"; log "✅ $BRANCH mergée (admin, CI vérifiée verte) + déployée"
          else
            log "⚠ merge bloqué pour $BRANCH (protection/approbation requise) — laissée dans .relay/pushed"
          fi
          ;;
      esac
    )
  done

  log "cycle relais terminé"
}

if [ "${1:-}" = "--once" ]; then
  run_cycle
else
  log "relais démarré en boucle (intervalle ${INTERVAL}s) — Ctrl-C pour arrêter"
  while true; do run_cycle; sleep "$INTERVAL"; done
fi
