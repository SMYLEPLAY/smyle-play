/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/state.js
   Mutable state partagé entre tous les modules UI.
   Doit être chargé AVANT tout autre module UI dans index.html.
   ───────────────────────────────────────────────────────────────────────── */

// ── 1. STATE ─────────────────────────────────────────────────────────────────

let PLAYLISTS       = {};
let currentPlaylist = null;   // playlist EN COURS DE LECTURE (ne jamais nullifier côté UI)
let openedPanelKey  = null;   // playlist dont le panel est ouvert (séparé du playback)
let currentTrackIdx = -1;
let currentTheme    = null;
let audio           = new Audio();
let isPlaying       = false;
let myMixTracks     = [];
let mixPlaying      = false;
let mixIdx          = 0;
let progressDragging = false;
let loopMode         = false;
let dragSrcIdx       = null;

// Compteur de timeupdate pour limiter les updates Media Session (coûteux)
// (consommé par le listener audio.addEventListener('timeupdate', …) dans ui/app.js)
let _msUpdateCounter = 0;

// ── 2. EXPOSITION GLOBALE ────────────────────────────────────────────────────
// window.smyleAudio : permet au mini-bar (et aux futurs modules) de s'attacher
// à l'unique instance Audio singleton sans dépendance directe sur ce fichier.
if (typeof window !== 'undefined') {
  window.smyleAudio = audio;
}
