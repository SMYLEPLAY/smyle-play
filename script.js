/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — script.js
   Playlists chargées dynamiquement via GET /api/tracks (server.py).
   ───────────────────────────────────────────────────────────────────────── */

// ── 1. STATE ─────────────────────────────────────────────────────────────────
// State variables moved to ui/core/state.js (loaded before this file via index.html).
// Shared lexical-scope vars: PLAYLISTS, currentPlaylist, openedPanelKey,
// currentTrackIdx, currentTheme, audio, isPlaying, myMixTracks, mixPlaying,
// mixIdx, progressDragging, loopMode, dragSrcIdx, _msUpdateCounter.

// ── 2. CHARGEMENT DYNAMIQUE DES PLAYLISTS ────────────────────────────────────
// → `fetchPlaylists()`, `injectCommunityPlaylist()`, `playWattTrack()` moved
//   to ui/hub/community.js

// ── 3. ENCODE FILE PATH ──────────────────────────────────────────────────────
// → `encodeFilePath()` moved to ui/core/dom.js

// ── 4. PLAY COUNTER (localStorage) ──────────────────────────────────────────
// → `getPlayCount()` and `incrementPlay()` moved to ui/core/storage.js

// → `fmtPlays()` moved to ui/core/dom.js

// ── 5. AUTH ──────────────────────────────────────────────────────────────────
// → `getUsers()`, `saveUsers()`, `getCurrentUser()`, `setCurrentUser()`,
//    `clearCurrentUser()` moved to ui/core/storage.js
// → `doSignup()`, `doLogin()`, `doLogout()` moved to ui/modals/auth.js
// → `saveUserPlaylist()` moved to ui/core/storage.js

// ── 6. AUTH UI ───────────────────────────────────────────────────────────────
// → `renderAuthArea()`, `openAuthModal()`, `closeAuthModal()`,
//   `switchAuthTab()`, `submitLogin()`, `submitSignup()` moved to ui/modals/auth.js

// ── 7. TRACK PANEL ───────────────────────────────────────────────────────────
// → `openPlaylist()`, `quickPlay()`, `closePanel()`, `closeAll()`
//   moved to ui/panels/playlist.js

// ── 8. AUDIO PLAYER ──────────────────────────────────────────────────────────
// → `showPlayerUI()`, `loadTrack()`, `togglePlay()`, `updatePlayBtn()`,
//   `nextTrack()`, `prevTrack()` moved to ui/player/audio.js

// ── 9. PROGRESS BAR (div-based) ──────────────────────────────────────────────

// Compteur de timeupdate pour limiter les updates Media Session (coûteux)
// → `_msUpdateCounter` is declared in ui/core/state.js
audio.addEventListener('timeupdate', () => {
  if (progressDragging || !audio.duration) return;
  const pct = (audio.currentTime / audio.duration) * 100;
  document.getElementById('progressFill').style.width = pct + '%';
  updateTimeDisplay();

  // Media Session position state — 1 update / 5 événements (évite trop de CPU)
  if ('mediaSession' in navigator && ++_msUpdateCounter % 5 === 0) {
    try {
      navigator.mediaSession.setPositionState({
        duration:     audio.duration,
        position:     audio.currentTime,
        playbackRate: audio.playbackRate || 1,
      });
    } catch(e) { /* setPositionState pas supporté sur tous les navigateurs */ }
  }
});

audio.addEventListener('ended', () => {
  if (loopMode) { audio.currentTime = 0; audio.play().catch(() => {}); return; }
  nextTrack();
});

// Gestion d'erreur : fichier introuvable ou non lisible sur R2
audio.addEventListener('error', () => {
  const failedUrl = audio.src;
  const code = audio.error ? audio.error.code : '?';
  console.error('[SMYLE] Audio error code=' + code + ' url=' + failedUrl);

  // Tentative avec URL alternative (variante espace devant le dossier)
  // ex: JUNGLE%20OSMOSE/ → %20JUNGLE%20OSMOSE/
  if (!audio._retried && audio._trackRef) {
    const track   = audio._trackRef;
    const altUrl  = track.url_alt || buildAltUrl(failedUrl);
    if (altUrl && altUrl !== failedUrl) {
      console.warn('[SMYLE] Retry with alt URL:', altUrl);
      audio._retried = true;
      audio.src = altUrl;
      audio.play().catch(() => {});
      return;
    }
  }

  // Échec définitif
  console.error('[SMYLE] Both URLs failed:', failedUrl);
  showToast('⚠ Fichier indisponible — passage au suivant');
  isPlaying = false;
  updatePlayBtn();
  setTimeout(() => { if (!isPlaying) nextTrack(); }, 1500);
});

// → `buildAltUrl()` moved to ui/core/dom.js

audio.addEventListener('play',  () => {
  isPlaying = true;
  updatePlayBtn();
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing';
});
audio.addEventListener('pause', () => {
  isPlaying = false;
  updatePlayBtn();
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'paused';
});

// Clic sur la barre de progression pour se déplacer
document.addEventListener('DOMContentLoaded', () => {
  const bar = document.getElementById('progressBar');
  if (bar) {
    bar.addEventListener('click', e => {
      if (!audio.duration) return;
      const rect = bar.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });

    // Drag sur la progress bar
    bar.addEventListener('mousedown', e => {
      progressDragging = true;
      const move = ev => {
        const rect = bar.getBoundingClientRect();
        const pct  = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
        document.getElementById('progressFill').style.width = (pct * 100) + '%';
        if (audio.duration) audio.currentTime = pct * audio.duration;
        updateTimeDisplay();
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', () => {
        progressDragging = false;
        document.removeEventListener('mousemove', move);
      }, { once: true });
    });
  }
});

// → `updateTimeDisplay()` moved to ui/player/audio.js

// → `fmtTime()` and `fmtTimeLong()` moved to ui/core/dom.js

// ── 10. MY MIX ───────────────────────────────────────────────────────────────
// → `toggleMixPanel()`, `closeMixPanel()`, `addToMix()`, `renderMixPanel()`,
//   `removeFromMix()`, `clearMix()` moved to ui/panels/mix.js
// → `playMixFromIdx()`, `loadMixTrack()`, `nextMixTrack()`, `prevMixTrack()`
//   moved to ui/player/audio.js

// ── 11. SAVE MIX MODAL ───────────────────────────────────────────────────────
// → `openSaveMix()`, `closeSaveMix()`, `confirmSaveMix()` moved to
//   ui/modals/save-mix.js

// ── 12. MIX DRAG-AND-DROP ────────────────────────────────────────────────────
// → `mixDragStart()`, `mixDragOver()`, `mixDrop()`, `mixDragEnd()`
//   moved to ui/panels/mix.js

// ── 13. LOOP ─────────────────────────────────────────────────────────────────
// → `toggleLoop()` moved to ui/player/audio.js

// ── 14. CONTACT MODAL ────────────────────────────────────────────────────────
// → `openContactModal()`, `closeContactModal()`, `submitContact()` moved to
//   ui/modals/contact.js

// ── 14a. PREMIUM MODAL ───────────────────────────────────────────────────────
// → `openPremiumModal()`, `closePremiumModal()`, `submitPremiumInterest()`
//   moved to ui/modals/premium.js

// ── 14b. ADD CURRENT TRACK TO MIX (bouton + dans le player) ──────────────────
// → `addCurrentToMix()` moved to ui/panels/mix.js

// ── 14c. COMMUNITY HUB — chargé depuis l'API ────────────────────────────────
// → `renderCommunityHub()` and `_renderHubFromAPI()` (with its protected
//   local `setVal` closure) moved to ui/hub/community.js

// → `_fmtHub()`, `_esc()`, `_slugify()` and `showToast()` moved to ui/core/dom.js

// ── 13. INIT ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Charger les playlists depuis le serveur
  await fetchPlaylists();

  // 2. UI initiale
  renderAuthArea();
  renderMixPanel();
  updatePlayBtn();
  renderCommunityHub();

  // 3. Volume initial
  audio.volume = 0.8;

  // 4. Fermeture modales sur clic overlay
  document.getElementById('authModal').addEventListener('click', e => {
    if (e.target === document.getElementById('authModal')) closeAuthModal();
  });
  document.getElementById('saveMixModal').addEventListener('click', e => {
    if (e.target === document.getElementById('saveMixModal')) closeSaveMix();
  });
  document.getElementById('contactModal').addEventListener('click', e => {
    if (e.target === document.getElementById('contactModal')) closeContactModal();
  });
  document.getElementById('premiumModal').addEventListener('click', e => {
    if (e.target === document.getElementById('premiumModal')) closePremiumModal();
  });

  // 5. Raccourcis clavier
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.code === 'Space')      { e.preventDefault(); togglePlay(); }
    if (e.code === 'ArrowRight') nextTrack();
    if (e.code === 'ArrowLeft')  prevTrack();
    if (e.code === 'Escape')     closeAll();
  });
});
