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

  // Mettre à jour les compteurs sur les cartes officielles
  Object.keys(PLAYLISTS).forEach(key => {
    const el = document.getElementById(`count-${key}`);
    if (el) {
      const n = (PLAYLISTS[key]?.tracks || []).length;
      el.textContent = `${n} titre${n > 1 ? 's' : ''}`;
    }
  });

  // Sprint D — Injecter les sons communautaires WATT dans le player
  injectCommunityPlaylist();
}

// ── 2b. INJECTION PLAYLIST COMMUNAUTAIRE (Sprint D) ──────────────────────────

function injectCommunityPlaylist() {
  const wattTracks = JSON.parse(localStorage.getItem('smyle_watt_tracks') || '[]');
  const profile    = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
  if (!wattTracks.length) return;

  const artistName = profile?.artistName || 'Artiste WATT';

  // Convertir les tracks WATT au format PLAYLISTS compatible avec le player
  const converted = wattTracks.map(t => ({
    id:       t.id,
    file:     t.file || '',
    name:     t.name || 'Sans titre',
    duration: 0,
    url:      t.streamUrl || null,   // URL R2 pour streaming (null = pas streamable depuis l'accueil)
    genre:    t.genre || '',
    artist:   artistName,
    coverDataUrl: t.coverDataUrl || null,
    watt:     true,                  // flag pour distinguer les tracks communautaires
  }));

  // N'ajouter que les tracks avec une URL streamable
  const streamable = converted.filter(t => t.url);

  if (streamable.length) {
    PLAYLISTS['watt-community'] = {
      label:          'WATT Community',
      folder:         'WATT',
      theme:          'watt-community',
      tracks:         streamable,
      total_duration: 0,
    };
  }
}

// Jouer un son communautaire depuis le hub (identifié par son id)
function playWattTrack(trackId) {
  // Chercher d'abord dans la playlist watt-community injectée
  const wattPl = PLAYLISTS['watt-community'];
  if (wattPl) {
    const idx = wattPl.tracks.findIndex(t => t.id === trackId);
    if (idx >= 0) { loadTrack('watt-community', idx); return; }
  }

  // Fallback : chercher dans localStorage et lire directement si URL disponible
  const wattTracks = JSON.parse(localStorage.getItem('smyle_watt_tracks') || '[]');
  const t = wattTracks.find(t => t.id === trackId);
  if (t && t.streamUrl) {
    // Injection à la volée pour ce track
    if (!PLAYLISTS['watt-community']) {
      PLAYLISTS['watt-community'] = { label: 'WATT Community', folder: 'WATT', theme: 'watt-community', tracks: [], total_duration: 0 };
    }
    const profile    = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
    const artistName = profile?.artistName || 'Artiste WATT';
    const converted  = { id: t.id, file: t.file || '', name: t.name, duration: 0, url: t.streamUrl, genre: t.genre || '', artist: artistName, coverDataUrl: t.coverDataUrl || null, watt: true };
    PLAYLISTS['watt-community'].tracks.push(converted);
    loadTrack('watt-community', PLAYLISTS['watt-community'].tracks.length - 1);
  } else {
    showToast('Ce son n\'est pas encore disponible en streaming.');
  }
}

// ── 3. ENCODE FILE PATH ──────────────────────────────────────────────────────
// → `encodeFilePath()` moved to ui/core/dom.js

// ── 4. PLAY COUNTER (localStorage) ──────────────────────────────────────────
// → `getPlayCount()` and `incrementPlay()` moved to ui/core/storage.js

// → `fmtPlays()` moved to ui/core/dom.js

// ── 5. AUTH ──────────────────────────────────────────────────────────────────
// → `getUsers()`, `saveUsers()`, `getCurrentUser()`, `setCurrentUser()`,
//    `clearCurrentUser()` moved to ui/core/storage.js

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

// → `saveUserPlaylist()` moved to ui/core/storage.js

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
// → `mixDragStart()`, `mixDragOver()`, `mixDrop()`, `mixDragEnd()`
//   moved to ui/panels/mix.js

// ── 13. LOOP ─────────────────────────────────────────────────────────────────
// → `toggleLoop()` moved to ui/player/audio.js

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
// → `addCurrentToMix()` moved to ui/panels/mix.js

// ── 14c. COMMUNITY HUB — chargé depuis l'API ─────────────────────────────────

function renderCommunityHub() {
  _renderHubFromAPI();   // async — gère ses propres états
}

async function _renderHubFromAPI() {
  let artists = [];

  try {
    const res  = await fetch('/api/artists');
    const json = await res.json();
    artists = json.artists || [];
  } catch (_) {
    // Fallback localStorage si l'API est indisponible
    const profile = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
    const tracks  = JSON.parse(localStorage.getItem('smyle_watt_tracks')  || '[]');
    if (profile && profile.artistName) {
      artists = [{
        artistName: profile.artistName,
        slug:       profile.slug || '',
        plays:      tracks.reduce((s, t) => s + (t.plays || 0), 0),
        trackCount: tracks.length,
      }];
    }
  }

  // Stats
  const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const totalTracks = artists.reduce((s, a) => s + (a.trackCount || 0), 0);
  const totalPlays  = artists.reduce((s, a) => s + (a.plays || 0), 0);
  setVal('hub-nb-artists', artists.length);
  setVal('hub-nb-tracks',  totalTracks);
  setVal('hub-nb-plays',   _fmtHub(totalPlays));

  // Top 3
  const el = document.getElementById('hub-top3');
  if (!el) return;

  if (!artists.length) {
    el.innerHTML = `<div class="hub-t3-empty">Aucun artiste pour l'instant · <a href="/watt" class="hub-t3-empty-link">Rejoindre WATT →</a></div>`;
    return;
  }

  const src    = [...artists].sort((a, b) => (b.plays || 0) - (a.plays || 0)).slice(0, 3);
  const medals = ['🥇', '🥈', '🥉'];

  el.innerHTML = src.map((a, i) => {
    const slug = a.slug || _slugify(a.artistName);
    const url  = slug ? `/artiste/${slug}` : '/watt';
    return `<div class="hub-t3-row" onclick="window.location.href='${url}'"
                 role="button" tabindex="0"
                 onkeydown="if(event.key==='Enter')window.location.href='${url}'">
      <span class="hub-t3-medal">${medals[i]}</span>
      <span class="hub-t3-name">${_esc(a.artistName)}</span>
      <span class="hub-t3-plays">${_fmtHub(a.plays || 0)}&thinsp;▶</span>
    </div>`;
  }).join('');
}

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
