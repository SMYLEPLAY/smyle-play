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
    // Monde IMAGE (curation) — géré par ui/albums.js. Réapplique le mode
    // persisté (mymix_mode) + rafraîchit likées/albums si on est en image.
    if (window.SmyleAlbums && typeof window.SmyleAlbums.applyMixMode === 'function') {
      window.SmyleAlbums.applyMixMode(window.SmyleAlbums.getMixMode());
    }
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

  // S-01 (2026-09-02) — track.name / pl.label viennent du catalogue serveur
  // (/watt/tracks-catalog, /playlists/{id}) : échappés via _esc (ui/core/dom.js).
  list.innerHTML = n
    ? myMixTracks.map((m, i) => {
        const pl    = PLAYLISTS[m.playlistKey];
        const track = pl.tracks[m.trackIdx];
        return `
          <div class="mix-track-item${mixPlaying && mixIdx === i ? ' active' : ''}"
               data-theme="${_esc(pl.theme)}"
               draggable="true"
               ondragstart="mixDragStart(event,${i})"
               ondragover="mixDragOver(event,${i})"
               ondrop="mixDrop(event,${i})"
               ondragend="mixDragEnd()"
               onclick="playMixFromIdx(${i})">
            <span class="mix-drag-handle" title="Déplacer">⠿</span>
            <span class="mix-track-num">${String(i + 1).padStart(2, '0')}</span>
            <div class="mix-track-info">
              <div class="mix-track-name">${_esc(track.name)}</div>
              <div class="mix-track-pl">${_esc(pl.label)}</div>
            </div>
            <button class="mix-remove-btn" onclick="removeFromMix(event,${i})">✕</button>
          </div>
        `;
      }).join('')
    : `<div class="mix-empty">Ajoute des morceaux<br>depuis n'importe quelle playlist</div>`;

  // Rafraîchir aussi les playlists sauvegardées
  renderSavedPlaylists();
}

// ── SAVED PLAYLISTS (DB-backed avec fallback localStorage) ─────────────────
// Charge depuis l'API /playlists/me si l'user est authentifié, sinon depuis
// localStorage (legacy). Wishlist (♥ Mes Likes) toujours affichée en
// première position (auto-créée backend, regroupe les tracks likés).
// Cliquer une playlist → fetch ses tracks + load dans MY MIX (via virtual
// PLAYLISTS entry pour que le player principal puisse les jouer).

function _mixAuthHeaders() {
  const h = { 'Accept': 'application/json' };
  if (typeof getAuthToken === 'function') {
    const t = getAuthToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
  }
  return h;
}

async function renderSavedPlaylists() {
  const wrap  = document.getElementById('mix-saved-wrap');
  const listEl = document.getElementById('mix-saved-list');
  const countEl = document.getElementById('mix-saved-count');
  if (!wrap || !listEl) return;

  const user = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  if (!user) {
    wrap.style.display = 'none';
    return;
  }
  wrap.style.display = '';
  listEl.innerHTML = `<div class="mix-saved-empty">Chargement…</div>`;

  // 1) Récup wishlist (♥ Mes Likes) — toujours en tête
  let wishlist = null;
  try {
    const r = await fetch('/playlists/wishlist', { credentials: 'same-origin', headers: _mixAuthHeaders() });
    if (r.ok) wishlist = await r.json();
  } catch (_) {}

  // 2) Récup mes playlists DB
  let mine = [];
  try {
    const r = await fetch('/playlists/me', { credentials: 'same-origin', headers: _mixAuthHeaders() });
    if (r.ok) mine = await r.json();
  } catch (_) {}

  // 3) Fallback localStorage pour les sauvegardes legacy (pre-migration)
  const legacy = (typeof getUserPlaylists === 'function') ? getUserPlaylists() : [];

  // 4) Combiner : wishlist en tête, puis playlists DB (en excluant la wishlist
  //    pour éviter doublon), puis legacy localStorage
  const dbList = mine.filter(p => !wishlist || p.id !== wishlist.id);
  const totalCount = (wishlist ? 1 : 0) + dbList.length + legacy.length;
  if (countEl) countEl.textContent = totalCount;

  if (totalCount === 0) {
    listEl.innerHTML = `<div class="mix-saved-empty">Aucune playlist sauvegardée pour le moment.</div>`;
    return;
  }

  // Sort DB par date desc (created_at vient au format ISO)
  dbList.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));

  const html = [];

  // Wishlist row (toujours en premier)
  if (wishlist) {
    html.push(`
      <div class="mix-saved-item mix-saved-wishlist" onclick="loadSavedPlaylist('${_mixEsc(wishlist.id)}')" title="Mes Likes (wishlist)">
        <div class="mix-saved-item-info">
          <div class="mix-saved-item-name">♥ Mes Likes</div>
          <div class="mix-saved-item-meta">Auto · tracks aimés</div>
        </div>
      </div>
    `);
  }

  // DB playlists
  for (const p of dbList) {
    const badge = p.visibility === 'public' ? '🌐' : '🔒';
    html.push(`
      <div class="mix-saved-item" onclick="loadSavedPlaylist('${_mixEsc(p.id)}')" title="Charger dans MY MIX">
        <div class="mix-saved-item-info">
          <div class="mix-saved-item-name">${_mixEsc(p.title || 'Sans nom')}</div>
          <div class="mix-saved-item-meta">${badge} ${p.visibility === 'public' ? 'Publique' : 'Privée'}</div>
        </div>
        <button class="mix-saved-del" onclick="deleteSavedPlaylist(event, '${_mixEsc(p.id)}')" title="Supprimer">✕</button>
      </div>
    `);
  }

  // Legacy localStorage
  const sortedLegacy = [...legacy].sort((a, b) => (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0));
  for (const p of sortedLegacy) {
    const n = (p.tracks || []).length;
    html.push(`
      <div class="mix-saved-item mix-saved-legacy" onclick="loadSavedPlaylist('${_mixEsc(p.id)}', true)" title="Charger dans MY MIX (legacy)">
        <div class="mix-saved-item-info">
          <div class="mix-saved-item-name">${_mixEsc(p.name || 'Sans nom')}</div>
          <div class="mix-saved-item-meta">${n} titre${n > 1 ? 's' : ''} · local</div>
        </div>
        <button class="mix-saved-del" onclick="deleteSavedPlaylist(event, '${_mixEsc(p.id)}', true)" title="Supprimer">✕</button>
      </div>
    `);
  }

  listEl.innerHTML = html.join('');
}

async function loadSavedPlaylist(id, isLegacy) {
  // Legacy localStorage : reprend l'ancien comportement
  if (isLegacy === true) {
    const saved = (typeof getUserPlaylists === 'function') ? getUserPlaylists() : [];
    const p = saved.find(x => x.id === id);
    if (!p) { showToast('Playlist introuvable.'); return; }
    if (!p.tracks || !p.tracks.length) { showToast('Cette playlist est vide.'); return; }
    myMixTracks = p.tracks.map(t => ({ ...t }));
    mixPlaying = false;
    mixIdx = 0;
    renderMixPanel();
    showToast(`« ${p.name} » chargée dans MY MIX`);
    return;
  }

  // DB playlist : fetch détail puis register virtual PLAYLISTS entry
  try {
    const r = await fetch('/playlists/' + encodeURIComponent(id), {
      credentials: 'same-origin', headers: _mixAuthHeaders()
    });
    if (!r.ok) { showToast('Playlist introuvable.'); return; }
    const pl = await r.json();
    const tracks = pl.tracks || [];
    if (!tracks.length) { showToast('Cette playlist est vide.'); return; }

    // Register virtual PLAYLISTS entry pour que le player principal sache lire
    const virtualKey = 'db_' + pl.id;
    if (typeof PLAYLISTS !== 'undefined') {
      PLAYLISTS[virtualKey] = {
        theme: 'mix',
        label: pl.title || 'Playlist',
        folder: '',
        tracks: tracks.map(t => ({
          id: t.id,
          name: t.title || t.name || 'Sans titre',
          url: t.audio_url || t.stream_url || t.streamUrl || (t.r2_key ? '/watt/stream/' + t.r2_key : '') || '',
          file: (t.title || t.name || 'track') + '.wav'
        }))
      };
    }
    myMixTracks = tracks.map((t, idx) => ({
      playlistKey: virtualKey,
      trackIdx: idx,
      id: t.id,
      name: t.title || t.name,
      url: t.audio_url || t.stream_url || t.streamUrl || (t.r2_key ? '/watt/stream/' + t.r2_key : '') || ''
    }));
    mixPlaying = false;
    mixIdx = 0;
    renderMixPanel();
    showToast(`« ${pl.title} » chargée dans MY MIX`);
  } catch (e) {
    showToast('Erreur de chargement : ' + (e && e.message || 'inconnue'));
  }
}

async function deleteSavedPlaylist(e, id, isLegacy) {
  if (e) e.stopPropagation();

  if (isLegacy === true) {
    if (typeof deleteUserPlaylist !== 'function') return;
    const ok = deleteUserPlaylist(id);
    if (ok) {
      showToast('Playlist supprimée.');
      renderSavedPlaylists();
    } else {
      showToast('Impossible de supprimer cette playlist.');
    }
    return;
  }

  if (!confirm('Supprimer cette playlist ? Action irréversible.')) return;
  try {
    const r = await fetch('/playlists/' + encodeURIComponent(id), {
      method: 'DELETE', credentials: 'same-origin', headers: _mixAuthHeaders()
    });
    if (r.ok || r.status === 204) {
      showToast('Playlist supprimée.');
      await renderSavedPlaylists();
    } else {
      showToast('Suppression impossible.');
    }
  } catch (_) {
    showToast('Erreur réseau.');
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
