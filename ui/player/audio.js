/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/player/audio.js
   Audio player: load/play/next/prev for playlist AND mix mode.

   Reads shared state from ui/core/state.js:
     PLAYLISTS, currentPlaylist, currentTrackIdx, currentTheme,
     audio, isPlaying, myMixTracks, mixPlaying, mixIdx, loopMode
   Writes to:
     currentPlaylist, currentTrackIdx, currentTheme, isPlaying,
     mixPlaying, mixIdx, loopMode, audio.{src,_trackRef,_retried}

   Calls helpers from:
     ui/core/dom.js     — encodeFilePath, fmtPlays, showToast
     ui/core/storage.js — incrementPlay, getPlayCount
   Cross-module calls (resolved at call time via shared global scope):
     ui/panels/mix.js   — renderMixPanel (called from loadMixTrack)

   Must load after ui/core/state.js, dom.js, storage.js.
   ───────────────────────────────────────────────────────────────────────── */

// ── 8. AUDIO PLAYER ──────────────────────────────────────────────────────────

function showPlayerUI() {
  document.getElementById('player-empty').style.display    = 'none';
  document.getElementById('player-info').style.display     = '';
  document.getElementById('player-controls').style.display = '';
  document.getElementById('player-progress').style.display = '';
}

function loadTrack(playlistKey, idx) {
  const pl    = PLAYLISTS[playlistKey];
  if (!pl) return;
  const track = pl.tracks[idx];
  if (!track) return;

  currentPlaylist = playlistKey;
  currentTrackIdx = idx;
  currentTheme    = pl.theme;
  mixPlaying      = false;

  // URL cloud R2 si disponible, sinon chemin local
  const primaryUrl = track.url || encodeFilePath(pl.folder, track.file);
  audio._trackRef  = track;          // garde une référence pour le retry
  audio._retried   = false;

  // NE PAS appeler audio.load() — sur iOS Safari, load() brise la permission
  // de lecture automatique. Changer audio.src suffit ; play() déclenche le
  // chargement. Sans load() l'auto-avance fonctionne dans les événements 'ended'.
  audio.src = primaryUrl;
  console.log('[SMYLE] Loading:', primaryUrl);
  audio.play().catch(e => console.warn('[SMYLE] play():', e.message));
  isPlaying = true;

  // ── Media Session API (lock screen / écouteurs iOS + Android) ──────────────
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title:  track.name  || 'Titre inconnu',
      artist: pl.label    || 'SMYLE PLAY',
      album:  'SMYLE PLAY',
    });
    navigator.mediaSession.setActionHandler('play',          () => { audio.play().catch(() => {}); isPlaying = true;  updatePlayBtn(); });
    navigator.mediaSession.setActionHandler('pause',         () => { audio.pause(); isPlaying = false; updatePlayBtn(); });
    navigator.mediaSession.setActionHandler('nexttrack',     () => nextTrack());
    navigator.mediaSession.setActionHandler('previoustrack', () => prevTrack());
    navigator.mediaSession.setActionHandler('seekto', details => {
      if (audio.duration && details.seekTime != null) audio.currentTime = details.seekTime;
    });
  }

  // Thème du player
  document.getElementById('player').dataset.theme          = pl.theme;
  document.getElementById('player-track-name').textContent = track.name;
  document.getElementById('player-playlist-name').textContent = pl.label;

  // Afficher l'UI du player
  showPlayerUI();

  // Mode tag (effacer MY MIX si on revient sur une playlist normale)
  const modeTag = document.getElementById('player-mode-tag');
  modeTag.textContent = '';
  modeTag.classList.remove('visible');

  // Surligner la piste active dans le panel
  document.querySelectorAll('.track-item').forEach(el => el.classList.remove('active'));
  const el = document.getElementById(`ti-${track.id}`);
  if (el) { el.classList.add('active'); el.scrollIntoView({ block: 'nearest' }); }

  updatePlayBtn();
  incrementPlay(track.id);

  const playsEl = document.getElementById(`plays-${track.id}`);
  if (playsEl) playsEl.textContent = `${fmtPlays(getPlayCount(track.id))} ▶`;
}

function togglePlay() {
  if (audio.paused) { audio.play().catch(() => {}); isPlaying = true; }
  else               { audio.pause(); isPlaying = false; }
  updatePlayBtn();
}

function updatePlayBtn() {
  const btn = document.getElementById('btn-play');
  if (!btn) return;
  btn.innerHTML = isPlaying
    ? `<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`
    : `<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>`;
}

function nextTrack() {
  if (mixPlaying) { nextMixTrack(); return; }
  if (!currentPlaylist) return;
  const pl = PLAYLISTS[currentPlaylist];
  loadTrack(currentPlaylist, (currentTrackIdx + 1) % pl.tracks.length);
}

function prevTrack() {
  if (mixPlaying) { prevMixTrack(); return; }
  if (!currentPlaylist) return;
  const pl = PLAYLISTS[currentPlaylist];
  loadTrack(currentPlaylist, (currentTrackIdx - 1 + pl.tracks.length) % pl.tracks.length);
}

// ── TIME DISPLAY ─────────────────────────────────────────────────────────────

function updateTimeDisplay() {
  const c = document.getElementById('time-current');
  const d = document.getElementById('time-duration');
  if (c) c.textContent = fmtTime(audio.currentTime);
  if (d) d.textContent = fmtTime(audio.duration || 0);
}

// ── 10. MY MIX — PLAYBACK ────────────────────────────────────────────────────

function playMixFromIdx(i) {
  if (!myMixTracks.length) return;
  mixPlaying = true;
  mixIdx     = i;
  loadMixTrack();
}

function loadMixTrack() {
  if (!myMixTracks.length) return;
  const m     = myMixTracks[mixIdx];
  const pl    = PLAYLISTS[m.playlistKey];
  const track = pl.tracks[m.trackIdx];

  currentTheme = pl.theme;
  // Pas de audio.load() — voir commentaire dans loadTrack()
  audio.src    = track.url || encodeFilePath(pl.folder, track.file);
  audio.play().catch(() => {});
  isPlaying = true;

  document.getElementById('player').dataset.theme          = pl.theme;
  document.getElementById('player-track-name').textContent = track.name;
  document.getElementById('player-playlist-name').textContent = 'MY MIX';

  // Media Session pour MY MIX
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title:  track.name || 'Titre inconnu',
      artist: 'MY MIX',
      album:  'SMYLE PLAY',
    });
    navigator.mediaSession.setActionHandler('nexttrack',     () => nextMixTrack());
    navigator.mediaSession.setActionHandler('previoustrack', () => prevMixTrack());
    navigator.mediaSession.setActionHandler('play',          () => { audio.play().catch(() => {}); isPlaying = true;  updatePlayBtn(); });
    navigator.mediaSession.setActionHandler('pause',         () => { audio.pause(); isPlaying = false; updatePlayBtn(); });
  }

  showPlayerUI();

  const modeTag = document.getElementById('player-mode-tag');
  modeTag.textContent = 'MY MIX';
  modeTag.classList.add('visible');

  updatePlayBtn();
  incrementPlay(track.id);
  renderMixPanel(); // mettre à jour active
}

function nextMixTrack() {
  mixIdx = (mixIdx + 1) % myMixTracks.length;
  loadMixTrack();
}

function prevMixTrack() {
  mixIdx = (mixIdx - 1 + myMixTracks.length) % myMixTracks.length;
  loadMixTrack();
}

// ── 13. LOOP ─────────────────────────────────────────────────────────────────

function toggleLoop() {
  loopMode = !loopMode;
  const btn = document.getElementById('btn-loop');
  if (btn) btn.classList.toggle('loop-active', loopMode);
  showToast(loopMode ? 'Boucle activée ↺' : 'Boucle désactivée');
}
