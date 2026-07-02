/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/app.js
   Application entry point for index.html.

   Responsibilities (no function declarations — everything is inline
   runtime wiring that executes at load):
     1. Audio element event listeners (timeupdate / ended / error / play
        / pause) that react to playback state on the shared `audio`
        element declared in ui/core/state.js.
     2. Progress bar DOMContentLoaded wiring: click-to-seek and drag.
        The local `move` const inside the drag handler is deliberately
        scoped (Graphify false-positive node — not a top-level function).
     3. App init DOMContentLoaded: fetchPlaylists → initial UI render →
        volume → modal overlay-close listeners → keyboard shortcuts.

   Must be the LAST script loaded by index.html (after all ui/* modules),
   because it references functions from:
     ui/core/dom.js     — showToast, buildAltUrl
     ui/core/storage.js — (indirectly via modal functions)
     ui/player/audio.js — updateTimeDisplay, updatePlayBtn, nextTrack,
                          prevTrack, togglePlay
     ui/panels/playlist.js — closeAll
     ui/panels/mix.js      — renderMixPanel
     ui/modals/auth.js     — renderAuthArea, closeAuthModal
     ui/modals/contact.js  — closeContactModal
     ui/modals/premium.js  — closePremiumModal
     ui/modals/save-mix.js — closeSaveMix
     ui/hub/community.js   — fetchPlaylists, renderCommunityHub
   ───────────────────────────────────────────────────────────────────────── */

// ── PROGRESS BAR — timeupdate (media-session rate-limited) ──────────────────

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

// ── PROGRESS BAR — click-to-seek and drag ──────────────────────────────────

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

// ── APP INIT ────────────────────────────────────────────────────────────────

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
