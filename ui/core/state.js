/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/state.js
   Mutable state partagé entre tous les modules UI.
   Doit être chargé AVANT script.js et tout autre module UI dans index.html.
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
// (consommé par le listener audio.addEventListener('timeupdate', …) dans script.js)
let _msUpdateCounter = 0;
