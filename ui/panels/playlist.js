/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/panels/playlist.js
   Track panel: open/close a playlist, render its tracks, quick-play.

   Reads shared state from ui/core/state.js:
     openedPanelKey, PLAYLISTS, currentPlaylist, currentTrackIdx
   Writes to:
     openedPanelKey

   Calls helpers from:
     ui/core/dom.js     — showToast, fmtTime, fmtTimeLong, fmtPlays
     ui/core/storage.js — getPlayCount
   Cross-module calls (resolved at call time):
     ui/player/audio.js — loadTrack
     ui/panels/mix.js   — closeMixPanel (via closeAll), addToMix (inline onclick)

   Must load after state/dom/storage/audio.
   ───────────────────────────────────────────────────────────────────────── */

// ── 7. TRACK PANEL ──────────────────────────────────────────────────────────

function openPlaylist(key, cardEl) {
  const panel = document.getElementById('trackPanel');
  const list  = document.getElementById('track-list');

  // Déjà ouvert sur la même playlist → fermer
  if (openedPanelKey === key && panel.classList.contains('open')) {
    closePanel();
    return;
  }

  if (!PLAYLISTS[key]) { showToast('Chargement en cours…'); return; }

  // Animation d'entrée sur la carte
  if (cardEl) {
    cardEl.classList.remove('entering');
    void cardEl.offsetWidth; // reflow
    cardEl.classList.add('entering');
    setTimeout(() => cardEl.classList.remove('entering'), 1400);
  }

  openedPanelKey      = key;   // panel UI seulement — currentPlaylist reste inchangé
  const pl            = PLAYLISTS[key];
  panel.dataset.theme = pl.theme;

  document.getElementById('panel-title').textContent = pl.label;
  document.getElementById('panel-sub').textContent   =
    `${pl.tracks.length} titre${pl.tracks.length > 1 ? 's' : ''}`;

  // Durée totale
  const totalDur = pl.total_duration || pl.tracks.reduce((s, t) => s + (t.duration || 0), 0);
  const durEl = document.getElementById('panel-total-dur');
  if (durEl) durEl.textContent = totalDur > 0 ? `Durée totale · ${fmtTimeLong(totalDur)}` : '';

  list.innerHTML = pl.tracks.length
    ? pl.tracks.map((t, i) => `
        <div class="track-item${currentPlaylist === key && currentTrackIdx === i ? ' active' : ''}"
             id="ti-${t.id}" onclick="loadTrack('${key}', ${i})">
          <span class="track-num">${String(i + 1).padStart(2, '0')}</span>
          <div class="track-info">
            <div class="track-name">${t.name}</div>
          </div>
          <div class="track-playing-icon"><span></span><span></span><span></span></div>
          ${t.duration ? `<span class="track-dur">${fmtTime(t.duration)}</span>` : ''}
          <span class="track-plays" id="plays-${t.id}">${fmtPlays(getPlayCount(t.id))} ▶</span>
          <button class="add-to-mix-btn" title="Ajouter à My Mix"
                  onclick="addToMix(event,'${key}',${i})">＋</button>
        </div>
      `).join('')
    : `<div style="padding:32px 28px;font-size:11px;letter-spacing:.25em;color:rgba(136,0,255,.25);text-transform:uppercase">Aucun fichier audio trouvé</div>`;

  panel.classList.add('open');
  document.getElementById('overlay').classList.add('show');
}

// Lance le premier titre d'une playlist SANS ouvrir le panel
function quickPlay(e, key) {
  e.stopPropagation();
  if (!PLAYLISTS[key]) { showToast('Chargement en cours…'); return; }
  const tracks = PLAYLISTS[key].tracks;
  if (!tracks.length) { showToast('Aucun fichier audio trouvé'); return; }
  loadTrack(key, 0);
}

function closePanel() {
  document.getElementById('trackPanel').classList.remove('open');
  document.getElementById('overlay').classList.remove('show');
  openedPanelKey = null;
  // NE PAS nullifier currentPlaylist : la lecture en cours doit continuer
  // et s'enchaîner correctement même panel fermé
}

function closeAll() {
  closePanel();
  closeMixPanel();
  if (typeof closeAgentPanel === 'function') closeAgentPanel();
}
