/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/panels/mix.js
   My Mix panel: add/remove/reorder tracks, drag-and-drop, open/close UI.

   Reads shared state from ui/core/state.js:
     PLAYLISTS, currentPlaylist, currentTrackIdx,
     myMixTracks, mixPlaying, mixIdx, dragSrcIdx
   Writes to:
     myMixTracks, mixPlaying, mixIdx, dragSrcIdx

   Calls helpers from:
     ui/core/dom.js — showToast
   Cross-module calls (resolved at call time):
     ui/panels/playlist.js — closePanel (from toggleMixPanel)
     ui/player/audio.js    — playMixFromIdx (inline onclick in render)

   Must load after state/dom/storage/audio/playlist.
   ───────────────────────────────────────────────────────────────────────── */

// ── 10. MY MIX ──────────────────────────────────────────────────────────────

function toggleMixPanel() {
  const panel = document.getElementById('mixPanel');
  const isOpen = panel.classList.contains('open');
  if (isOpen) {
    closeMixPanel();
  } else {
    closePanel();
    panel.classList.add('open');
    document.getElementById('overlay').classList.add('show');
    // Rafraîchir contenu (dont la section "Mes playlists sauvegardées")
    renderMixPanel();
  }
}

function closeMixPanel() {
  document.getElementById('mixPanel').classList.remove('open');
  document.getElementById('overlay').classList.remove('show');
}

function addToMix(e, playlistKey, trackIdx) {
  e.stopPropagation();
  const track = PLAYLISTS[playlistKey].tracks[trackIdx];
  if (myMixTracks.find(m => m.id === track.id)) {
    showToast('Déjà dans My Mix !');
    return;
  }
  myMixTracks.push({ playlistKey, trackIdx, id: track.id });
  renderMixPanel();
  showToast(`« ${track.name} » ajouté à My Mix`);

  // Marquer visuellement le bouton
  const btn = document.querySelector(`#ti-${track.id} .add-to-mix-btn`);
  if (btn) document.getElementById(`ti-${track.id}`)?.classList.add('in-mix');
}

function renderMixPanel() {
  const list  = document.getElementById('mix-list');
  const sub   = document.getElementById('mix-sub');
  const count = document.getElementById('mix-count');
  const n     = myMixTracks.length;

  // Badge sur le bouton
  if (count) {
    count.textContent = n;
    count.classList.toggle('visible', n > 0);
  }
  if (sub) sub.textContent = `${n} titre${n > 1 ? 's' : ''}`;

  if (!list) return;

  list.innerHTML = n
    ? myMixTracks.map((m, i) => {
        const pl    = PLAYLISTS[m.playlistKey];
        const track = pl.tracks[m.trackIdx];
        return `
          <div class="mix-track-item${mixPlaying && mixIdx === i ? ' active' : ''}"
               data-theme="${pl.theme}"
               draggable="true"
               ondragstart="mixDragStart(event,${i})"
               ondragover="mixDragOver(event,${i})"
               ondrop="mixDrop(event,${i})"
               ondragend="mixDragEnd()"
               onclick="playMixFromIdx(${i})">
            <span class="mix-drag-handle" title="Déplacer">⠿</span>
            <span class="mix-track-num">${String(i + 1).padStart(2, '0')}</span>
            <div class="mix-track-info">
              <div class="mix-track-name">${track.name}</div>
              <div class="mix-track-pl">${pl.label}</div>
            </div>
            <button class="mix-remove-btn" onclick="removeFromMix(event,${i})">✕</button>
          </div>
        `;
      }).join('')
    : `<div class="mix-empty">Ajoute des morceaux<br>depuis n'importe quelle playlist</div>`;

  // Rafraîchir aussi les playlists sauvegardées
  renderSavedPlaylists();
}

// ── SAVED PLAYLISTS (localStorage) ──────────────────────────────────────────
// Affichées sous le mix courant. Cliquer → charge dans MY MIX. Bouton ✕ → supprime.

function renderSavedPlaylists() {
  const wrap  = document.getElementById('mix-saved-wrap');
  const listEl = document.getElementById('mix-saved-list');
  const countEl = document.getElementById('mix-saved-count');
  if (!wrap || !listEl) return;

  const user = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  if (!user) {
    // Non connecté → on cache la section (les playlists sont liées à un user)
    wrap.style.display = 'none';
    return;
  }
  wrap.style.display = '';

  const saved = (typeof getUserPlaylists === 'function') ? getUserPlaylists() : [];
  if (countEl) countEl.textContent = saved.length;

  if (!saved.length) {
    listEl.innerHTML = `<div class="mix-saved-empty">Aucune playlist sauvegardée pour le moment.</div>`;
    return;
  }

  // Tri par date de mise à jour décroissante
  const sorted = [...saved].sort((a, b) => (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0));

  listEl.innerHTML = sorted.map(p => {
    const n = (p.tracks || []).length;
    const safeName = _mixEsc(p.name || 'Sans nom');
    return `
      <div class="mix-saved-item" onclick="loadSavedPlaylist('${_mixEsc(p.id)}')" title="Charger dans MY MIX">
        <div class="mix-saved-item-info">
          <div class="mix-saved-item-name">${safeName}</div>
          <div class="mix-saved-item-meta">${n} titre${n > 1 ? 's' : ''}</div>
        </div>
        <button class="mix-saved-del" onclick="deleteSavedPlaylist(event, '${_mixEsc(p.id)}')" title="Supprimer">✕</button>
      </div>`;
  }).join('');
}

function loadSavedPlaylist(id) {
  const saved = (typeof getUserPlaylists === 'function') ? getUserPlaylists() : [];
  const p = saved.find(x => x.id === id);
  if (!p) { showToast('Playlist introuvable.'); return; }
  if (!p.tracks || !p.tracks.length) { showToast('Cette playlist est vide.'); return; }

  // Remplacement complet du mix courant
  myMixTracks = p.tracks.map(t => ({ ...t }));
  mixPlaying = false;
  mixIdx = 0;
  renderMixPanel();
  showToast(`« ${p.name} » chargée dans MY MIX`);
}

function deleteSavedPlaylist(e, id) {
  if (e) e.stopPropagation();
  if (typeof deleteUserPlaylist !== 'function') return;
  const ok = deleteUserPlaylist(id);
  if (ok) {
    showToast('Playlist supprimée.');
    renderSavedPlaylists();
  } else {
    showToast('Impossible de supprimer cette playlist.');
  }
}

function _mixEsc(s) {
  return String(s || '').replace(/[&<>"'`]/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c]
  ));
}

function removeFromMix(e, idx) {
  e.stopPropagation();
  const removed = myMixTracks.splice(idx, 1)[0];
  // Ôter la classe in-mix du track item si le panel est ouvert
  document.getElementById(`ti-${removed.id}`)?.classList.remove('in-mix');
  renderMixPanel();
}

function clearMix() {
  myMixTracks.forEach(m => document.getElementById(`ti-${m.id}`)?.classList.remove('in-mix'));
  myMixTracks = [];
  mixPlaying  = false;
  mixIdx      = 0;
  renderMixPanel();
}

// ── 14b. ADD CURRENT TRACK TO MIX (bouton + dans le player) ──────────────────

function addCurrentToMix() {
  if (!currentPlaylist || currentTrackIdx < 0) {
    showToast('Lance un morceau d\'abord !');
    return;
  }
  const track = PLAYLISTS[currentPlaylist]?.tracks[currentTrackIdx];
  if (!track) return;

  if (myMixTracks.find(m => m.id === track.id)) {
    showToast('Déjà dans My Mix !');
    return;
  }
  myMixTracks.push({ playlistKey: currentPlaylist, trackIdx: currentTrackIdx, id: track.id });
  renderMixPanel();
  showToast(`« ${track.name} » ajouté à My Mix`);

  // Feedback visuel sur le bouton +
  const btn = document.getElementById('btn-add-mix');
  if (btn) {
    btn.classList.add('added');
    setTimeout(() => btn.classList.remove('added'), 1200);
  }
}

// ── 12. MIX DRAG-AND-DROP ────────────────────────────────────────────────────

function mixDragStart(e, i) {
  dragSrcIdx = i;
  e.dataTransfer.effectAllowed = 'move';
  // Léger délai pour que le navigateur capture bien le fantôme
  setTimeout(() => {
    const items = document.querySelectorAll('.mix-track-item');
    if (items[i]) items[i].classList.add('dragging');
  }, 0);
}

function mixDragOver(e, i) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  if (dragSrcIdx === null || dragSrcIdx === i) return;
  document.querySelectorAll('.mix-track-item').forEach(el => el.classList.remove('drag-over'));
  const items = document.querySelectorAll('.mix-track-item');
  if (items[i]) items[i].classList.add('drag-over');
}

function mixDrop(e, targetIdx) {
  e.preventDefault();
  if (dragSrcIdx === null || dragSrcIdx === targetIdx) { mixDragEnd(); return; }
  const moved = myMixTracks.splice(dragSrcIdx, 1)[0];
  myMixTracks.splice(targetIdx, 0, moved);
  // Recaler l'index de lecture si le mix est en cours
  if (mixPlaying) {
    if      (mixIdx === dragSrcIdx)                          mixIdx = targetIdx;
    else if (dragSrcIdx < mixIdx && targetIdx >= mixIdx)     mixIdx--;
    else if (dragSrcIdx > mixIdx && targetIdx <= mixIdx)     mixIdx++;
  }
  dragSrcIdx = null;
  renderMixPanel();
}

function mixDragEnd() {
  dragSrcIdx = null;
  document.querySelectorAll('.mix-track-item').forEach(el => {
    el.classList.remove('dragging');
    el.classList.remove('drag-over');
  });
}
