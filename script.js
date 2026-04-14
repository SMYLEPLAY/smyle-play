/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — script.js
   Playlists chargées dynamiquement via GET /api/tracks (server.py).
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

// ── 2. CHARGEMENT DYNAMIQUE DES PLAYLISTS ────────────────────────────────────

async function fetchPlaylists() {
  // Charge directement /tracks.json (catalogue statique avec URLs R2 intégrées)
  // Plus fiable que /api/tracks sur Railway (pas de scan filesystem)
  try {
    const res = await fetch('/tracks.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    PLAYLISTS = await res.json();
  } catch (err) {
    // Fallback : essayer /api/tracks si tracks.json inaccessible
    console.warn('[SMYLE] /tracks.json erreur, essai /api/tracks :', err.message);
    try {
      const res2 = await fetch('/api/tracks');
      if (res2.ok) PLAYLISTS = await res2.json();
    } catch (e2) {
      console.error('[SMYLE] Impossible de charger les playlists :', e2);
    }
  }

  // Mettre à jour les compteurs sur les cartes
  Object.keys(PLAYLISTS).forEach(key => {
    const el = document.getElementById(`count-${key}`);
    if (el) {
      const n = (PLAYLISTS[key]?.tracks || []).length;
      el.textContent = `${n} titre${n > 1 ? 's' : ''}`;
    }
  });
}

// ── 3. ENCODE FILE PATH ──────────────────────────────────────────────────────

function encodeFilePath(folder, filename) {
  return folder.split('/').map(encodeURIComponent).join('/') + '/' + encodeURIComponent(filename);
}

// ── 4. PLAY COUNTER (localStorage) ──────────────────────────────────────────

function getPlayCount(id) {
  return parseInt(localStorage.getItem(`smyle_plays_${id}`) || '0', 10);
}

function incrementPlay(id) {
  const n = getPlayCount(id) + 1;
  localStorage.setItem(`smyle_plays_${id}`, n);
  return n;
}

function fmtPlays(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return n.toString();
}

// ── 5. AUTH ──────────────────────────────────────────────────────────────────

function getUsers()        { return JSON.parse(localStorage.getItem('smyle_users') || '[]'); }
function saveUsers(u)      { localStorage.setItem('smyle_users', JSON.stringify(u)); }
function getCurrentUser()  { return JSON.parse(localStorage.getItem('smyle_current_user') || 'null'); }
function setCurrentUser(u) { localStorage.setItem('smyle_current_user', JSON.stringify(u)); }
function clearCurrentUser(){ localStorage.removeItem('smyle_current_user'); }

function doSignup(email, password, name) {
  const users = getUsers();
  if (users.find(u => u.email === email)) return { ok: false, msg: 'Email déjà utilisé.' };
  const user = { id: Date.now(), email, password, name, playlists: [] };
  users.push(user);
  saveUsers(users);
  setCurrentUser(user);
  return { ok: true };
}

function doLogin(email, password) {
  const users = getUsers();
  const user  = users.find(u => u.email === email && u.password === password);
  if (!user) return { ok: false, msg: 'Email ou mot de passe incorrect.' };
  setCurrentUser(user);
  return { ok: true };
}

function doLogout() {
  clearCurrentUser();
  renderAuthArea();
}

function saveUserPlaylist(name, tracks) {
  const user = getCurrentUser();
  if (!user) return false;
  const users = getUsers();
  const idx   = users.findIndex(u => u.id === user.id);
  if (idx === -1) return false;
  users[idx].playlists = users[idx].playlists || [];
  users[idx].playlists.push({ name, tracks, createdAt: Date.now() });
  saveUsers(users);
  setCurrentUser(users[idx]);
  return true;
}

// ── 6. AUTH UI ────────────────────────────────────────────────────────────────

function renderAuthArea() {
  const user = getCurrentUser();
  const area = document.getElementById('authArea');
  if (!area) return;

  if (user) {
    const initials = user.name.slice(0, 2).toUpperCase();
    area.innerHTML = `
      <div class="user-badge" onclick="openAuthModal('login')">
        <div class="user-avatar">${initials}</div>
        <span class="user-name">${user.name}</span>
      </div>
      <button class="auth-btn" onclick="doLogout()" style="margin-left:10px">Déco</button>
    `;
  } else {
    area.innerHTML = `
      <button class="auth-btn" onclick="openAuthModal('login')">Connexion</button>
      <button class="auth-btn" onclick="openAuthModal('signup')" style="margin-left:6px">S'inscrire</button>
    `;
  }
}

function openAuthModal(tab) {
  document.getElementById('authModal').classList.add('open');
  switchAuthTab(tab);
}

function closeAuthModal() {
  document.getElementById('authModal').classList.remove('open');
  document.getElementById('authMsg').textContent = '';
}

function switchAuthTab(tab) {
  document.getElementById('tab-login').classList.toggle('active',  tab === 'login');
  document.getElementById('tab-signup').classList.toggle('active', tab === 'signup');
  document.getElementById('form-login').style.display  = tab === 'login'  ? '' : 'none';
  document.getElementById('form-signup').style.display = tab === 'signup' ? '' : 'none';
  document.getElementById('authMsg').textContent = '';
}

function submitLogin() {
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const result   = doLogin(email, password);
  if (result.ok) { closeAuthModal(); renderAuthArea(); }
  else document.getElementById('authMsg').textContent = result.msg;
}

function submitSignup() {
  const name     = document.getElementById('signup-name').value.trim();
  const email    = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  if (!name || !email || !password) {
    document.getElementById('authMsg').textContent = 'Tous les champs sont requis.';
    return;
  }
  const result = doSignup(email, password, name);
  if (result.ok) { closeAuthModal(); renderAuthArea(); }
  else document.getElementById('authMsg').textContent = result.msg;
}

// ── 7. TRACK PANEL ────────────────────────────────────────────────────────────

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
}

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
  audio.src = primaryUrl;
  console.log('[SMYLE] Loading:', primaryUrl);
  audio.load();
  audio.play().catch(e => console.warn('[SMYLE] play():', e.message));
  isPlaying = true;

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

// ── 9. PROGRESS BAR (div-based) ──────────────────────────────────────────────

audio.addEventListener('timeupdate', () => {
  if (progressDragging || !audio.duration) return;
  const pct = (audio.currentTime / audio.duration) * 100;
  document.getElementById('progressFill').style.width = pct + '%';
  updateTimeDisplay();
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
      audio.load();
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

function buildAltUrl(url) {
  // Si l'URL contient /JUNGLE%20OSMOSE/, essayer /%20JUNGLE%20OSMOSE/
  if (url.includes('/JUNGLE%20OSMOSE/'))
    return url.replace('/JUNGLE%20OSMOSE/', '/%20JUNGLE%20OSMOSE/');
  // Si déjà avec espace, essayer sans
  if (url.includes('/%20JUNGLE%20OSMOSE/'))
    return url.replace('/%20JUNGLE%20OSMOSE/', '/JUNGLE%20OSMOSE/');
  return null;
}

audio.addEventListener('play',  () => { isPlaying = true;  updatePlayBtn(); });
audio.addEventListener('pause', () => { isPlaying = false; updatePlayBtn(); });

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

function updateTimeDisplay() {
  const c = document.getElementById('time-current');
  const d = document.getElementById('time-duration');
  if (c) c.textContent = fmtTime(audio.currentTime);
  if (d) d.textContent = fmtTime(audio.duration || 0);
}

function fmtTime(s) {
  if (!s || isNaN(s)) return '0:00';
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function fmtTimeLong(s) {
  if (!s || isNaN(s)) return '';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m} min ${String(sec).padStart(2,'0')} sec`;
  return `${sec} sec`;
}

// ── 10. MY MIX ────────────────────────────────────────────────────────────────

function toggleMixPanel() {
  const panel = document.getElementById('mixPanel');
  const isOpen = panel.classList.contains('open');
  if (isOpen) {
    closeMixPanel();
  } else {
    closePanel();
    panel.classList.add('open');
    document.getElementById('overlay').classList.add('show');
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
  audio.src    = track.url || encodeFilePath(pl.folder, track.file);
  audio.load();
  audio.play().catch(() => {});
  isPlaying = true;

  document.getElementById('player').dataset.theme          = pl.theme;
  document.getElementById('player-track-name').textContent = track.name;
  document.getElementById('player-playlist-name').textContent = 'MY MIX';

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

// ── 11. SAVE MIX MODAL ────────────────────────────────────────────────────────

function openSaveMix() {
  if (!getCurrentUser()) { openAuthModal('login'); return; }
  if (!myMixTracks.length) { showToast('Aucun morceau dans My Mix.'); return; }
  document.getElementById('saveMixModal').classList.add('open');
  document.getElementById('mix-save-name').value = '';
  document.getElementById('saveMixMsg').textContent = '';
}

function closeSaveMix() {
  document.getElementById('saveMixModal').classList.remove('open');
}

function confirmSaveMix() {
  const name = document.getElementById('mix-save-name').value.trim();
  if (!name) { document.getElementById('saveMixMsg').textContent = 'Entre un nom.'; return; }
  const ok = saveUserPlaylist(name, myMixTracks.map(m => ({ ...m })));
  if (ok) {
    showToast(`Playlist « ${name} » sauvegardée !`);
    closeSaveMix();
  } else {
    document.getElementById('saveMixMsg').textContent = 'Erreur lors de la sauvegarde.';
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

// ── 13. LOOP ──────────────────────────────────────────────────────────────────

function toggleLoop() {
  loopMode = !loopMode;
  const btn = document.getElementById('btn-loop');
  if (btn) btn.classList.toggle('loop-active', loopMode);
  showToast(loopMode ? 'Boucle activée ↺' : 'Boucle désactivée');
}

// ── 14. CONTACT MODAL ────────────────────────────────────────────────────────

function openContactModal() {
  document.getElementById('contactModal').classList.add('open');
  document.getElementById('contact-success').textContent = '';
  document.getElementById('contact-form').reset();
}

function closeContactModal() {
  document.getElementById('contactModal').classList.remove('open');
}

function submitContact() {
  const name    = document.getElementById('contact-name').value.trim();
  const email   = document.getElementById('contact-email').value.trim();
  const type    = document.getElementById('contact-type').value;
  const msg     = document.getElementById('contact-msg').value.trim();

  if (!msg) {
    document.getElementById('contact-success').style.color = '#ff5555';
    document.getElementById('contact-success').textContent = 'Merci d\'écrire un message.';
    return;
  }

  // Sauvegarder dans localStorage (log local)
  const feedbacks = JSON.parse(localStorage.getItem('smyle_feedback') || '[]');
  feedbacks.push({ name, email, type, msg, date: new Date().toISOString() });
  localStorage.setItem('smyle_feedback', JSON.stringify(feedbacks));

  // Ouvrir le client mail de l'utilisateur en fallback
  const subject = encodeURIComponent(`[SMYLE PLAY] ${type} — ${name || 'Anonyme'}`);
  const body    = encodeURIComponent(`Catégorie : ${type}\nNom : ${name || '—'}\nEmail : ${email || '—'}\n\n${msg}`);
  const mailto  = `mailto:smyletheplan@gmail.com?subject=${subject}&body=${body}`;
  window.location.href = mailto;

  document.getElementById('contact-success').style.color = '#44cc88';
  document.getElementById('contact-success').textContent = 'Message enregistré — merci pour ton retour !';
  setTimeout(closeContactModal, 2200);
}

// ── 14a. PREMIUM MODAL ───────────────────────────────────────────────────────

function openPremiumModal() {
  document.getElementById('premiumModal').classList.add('open');
  document.getElementById('premiumMsg').textContent = '';
}

function closePremiumModal() {
  document.getElementById('premiumModal').classList.remove('open');
}

function submitPremiumInterest() {
  const user = getCurrentUser();
  // Sauvegarder l'intérêt en localStorage
  const interests = JSON.parse(localStorage.getItem('smyle_premium_interests') || '[]');
  const email = user ? user.email : 'anonyme';
  if (!interests.includes(email)) {
    interests.push(email);
    localStorage.setItem('smyle_premium_interests', JSON.stringify(interests));
  }
  const msg = document.getElementById('premiumMsg');
  msg.style.color = '#ffd700';
  msg.textContent = '✓ Noté ! Tu seras averti(e) à l\'ouverture de l\'espace artiste.';
  // Ouvrir client mail pour notifier l'équipe
  if (user) {
    const subject = encodeURIComponent('[SMYLE PLAY] Intérêt Premium Artiste');
    const body = encodeURIComponent(`Utilisateur intéressé : ${user.name} <${user.email}>`);
    setTimeout(() => { window.location.href = `mailto:smyletheplan@gmail.com?subject=${subject}&body=${body}`; }, 1200);
  }
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

// ── 14c. WATT RANKING ─────────────────────────────────────────────────────────

function renderWattRanking() {
  const container = document.getElementById('watt-ranking-list');
  if (!container) return;

  // Agréger les écoutes par playlist (simulation classement artiste)
  // Dans la version premium, chaque artiste aura ses propres tracks
  // Ici on affiche les playlists comme "artistes" avec leur total d'écoutes
  const wattArtists = JSON.parse(localStorage.getItem('smyle_watt_artists') || '[]');

  if (!wattArtists.length) {
    container.innerHTML = `
      <div class="watt-artist-row watt-placeholder">
        <span class="watt-rank">—</span>
        <div class="watt-artist-info">
          <div class="watt-artist-name">Aucun artiste inscrit pour l'instant</div>
          <div class="watt-artist-stats">Sois le premier à rejoindre WATT</div>
        </div>
        <div class="watt-artist-plays">— ▶</div>
      </div>`;
    return;
  }

  // Tri : 1. par écoutes totales, 2. par abonnés
  const sorted = [...wattArtists].sort((a, b) => {
    if (b.totalPlays !== a.totalPlays) return b.totalPlays - a.totalPlays;
    return (b.followers || 0) - (a.followers || 0);
  });

  container.innerHTML = sorted.map((artist, i) => `
    <div class="watt-artist-row">
      <span class="watt-rank">${String(i + 1).padStart(2, '0')}</span>
      <div class="watt-artist-info">
        <div class="watt-artist-name">${artist.name}</div>
        <div class="watt-artist-stats">${artist.followers || 0} abonnés · ${artist.trackCount || 0} sons</div>
      </div>
      <div class="watt-artist-plays">${fmtPlays(artist.totalPlays || 0)} ▶</div>
    </div>
  `).join('');
}

// ── 15. TOAST ─────────────────────────────────────────────────────────────────

function showToast(msg) {
  let t = document.getElementById('smyle-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'smyle-toast';
    Object.assign(t.style, {
      position:'fixed', bottom:'96px', left:'50%', transform:'translateX(-50%)',
      background:'rgba(15,5,30,.95)', border:'1px solid rgba(136,0,255,.3)',
      color:'rgba(200,160,255,.9)', fontSize:'11px', letterSpacing:'.2em',
      textTransform:'uppercase', padding:'10px 22px', borderRadius:'3px',
      zIndex:'9999', transition:'opacity .3s, transform .3s',
      opacity:'0', pointerEvents:'none', whiteSpace:'nowrap',
    });
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1';
  t.style.transform = 'translateX(-50%) translateY(0)';
  clearTimeout(t._tmr);
  t._tmr = setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateX(-50%) translateY(6px)';
  }, 2600);
}

// ── 13. INIT ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Charger les playlists depuis le serveur
  await fetchPlaylists();

  // 2. UI initiale
  renderAuthArea();
  renderMixPanel();
  updatePlayBtn();
  renderWattRanking();

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
