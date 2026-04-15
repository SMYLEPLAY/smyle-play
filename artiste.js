/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — artiste.js
   Page artiste publique · /artiste/[slug]
   Chargement via API PostgreSQL (/api/artists/<slug>)
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s || '');
  return d.innerHTML;
}

function fmtTime(sec) {
  if (!sec || isNaN(sec) || sec < 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function setEl(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(v ?? '');
}
function getEl(id) { return document.getElementById(id); }

function fmtPlays(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n || 0);
}


/* ── URL slug ────────────────────────────────────────────────────────────── */

function getSlugFromUrl() {
  const m = window.location.pathname.match(/\/artiste\/([^/]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}


/* ── Chargement depuis l'API ─────────────────────────────────────────────── */

let _artistData = null;   // { artist: {…}, tracks: […], rank: N }

async function loadAndRender() {
  const slug = getSlugFromUrl();
  if (!slug) { showNotFound(); return; }

  try {
    const res = await fetch(`/api/artists/${encodeURIComponent(slug)}`);

    if (res.status === 404) { showNotFound(); return; }
    if (!res.ok) { showNotFound(); return; }

    const json = await res.json();
    if (!json.artist) { showNotFound(); return; }

    _artistData = json.artist;
    renderPage(_artistData);

  } catch (err) {
    console.error('[artiste.js] Erreur API :', err);
    showNotFound();
  }
}


/* ── Render page ─────────────────────────────────────────────────────────── */

function renderPage(artist) {
  const tracks = artist.tracks || [];

  // Title / OG
  const pageTitle = `${artist.artistName} · SMYLE PLAY`;
  document.title  = pageTitle;
  _updateMeta('og:title',             pageTitle);
  _updateMeta('og:description',       artist.bio || `Découvre les créations musicales IA de ${artist.artistName} sur SMYLE PLAY`);
  _updateMeta('twitter:title',        pageTitle);
  _updateMeta('twitter:description',  artist.bio || 'Musique IA · SMYLE PLAY');

  // Avatar
  const avatarEl = getEl('ap-avatar');
  if (avatarEl) {
    const initial = (artist.artistName || '?')[0].toUpperCase();
    const color   = artist.avatarColor || '#8800ff';
    avatarEl.textContent    = initial;
    avatarEl.style.background = color;
  }

  // Nom, genre, bio
  setEl('ap-artist-name', artist.artistName || 'Artiste WATT');

  const genreEl = getEl('ap-genre-tag');
  if (genreEl) {
    if (artist.genre) {
      genreEl.textContent  = artist.genre;
      genreEl.style.display = 'inline-block';
    } else {
      genreEl.style.display = 'none';
    }
  }

  const bioEl = getEl('ap-bio');
  if (bioEl) {
    if (artist.bio) {
      bioEl.textContent  = artist.bio;
      bioEl.style.display = 'block';
    } else {
      bioEl.style.display = 'none';
    }
  }

  // Ville
  const cityEl = getEl('ap-city');
  if (cityEl) {
    if (artist.city) {
      cityEl.textContent  = '📍 ' + artist.city;
      cityEl.style.display = 'block';
    } else {
      cityEl.style.display = 'none';
    }
  }

  // Réseaux sociaux
  renderSocials(artist);

  // Stats
  setEl('ap-nb-tracks', tracks.length);
  setEl('ap-nb-plays',  fmtPlays(artist.plays || 0));

  // Classement WATT
  const rankStr = artist.rank ? `#${artist.rank}` : '#—';
  setEl('ap-watt-rank', rankStr);
  setEl('ap-rank-num',  rankStr);

  // Collab button — cacher si c'est mon propre profil
  _checkIfMyProfile(artist.userId);

  // Liste des sons
  renderTracks(tracks, artist.artistName);

  // Share URL
  const urlEl = getEl('ap-share-url');
  if (urlEl) urlEl.textContent = window.location.href;

  // Afficher le profil
  const profileEl = getEl('ap-profile');
  if (profileEl) profileEl.style.display = 'block';
}

function _updateMeta(property, content) {
  const el = document.querySelector(`[property="${property}"]`) ||
             document.querySelector(`[name="${property}"]`);
  if (el) el.setAttribute('content', content);
}

function _checkIfMyProfile(artistUserId) {
  // Vérifier si l'utilisateur connecté est le propriétaire du profil
  fetch('/api/auth/me')
    .then(r => r.json())
    .then(data => {
      const collabBtn = getEl('ap-collab-btn');
      if (!collabBtn) return;
      if (data.user && data.user.id === artistUserId) {
        // C'est mon profil — remplacer par un lien vers le dashboard
        collabBtn.textContent  = '⚙ Mon dashboard';
        collabBtn.onclick      = () => { window.location.href = '/dashboard'; };
      }
    })
    .catch(() => {});
}


/* ── Réseaux sociaux ─────────────────────────────────────────────────────── */

function renderSocials(artist) {
  const el = getEl('ap-socials');
  if (!el) return;

  const links = [];

  if (artist.soundcloud) {
    const url = artist.soundcloud.startsWith('http') ? artist.soundcloud : `https://soundcloud.com/${artist.soundcloud}`;
    links.push(`<a href="${esc(url)}" class="ap-social-link" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12">
        <path d="M1.175 12.225c-.056 0-.094.038-.1.094l-.233 2.154.233 2.105c.006.05.044.088.1.088.05 0 .088-.038.1-.088l.262-2.105-.262-2.154c-.012-.056-.05-.094-.1-.094m-.899.828c-.069 0-.119.05-.125.119L0 14.479l.151 1.307c.006.069.056.119.125.119s.119-.05.125-.119l.169-1.307-.169-1.307c-.006-.069-.056-.119-.125-.119m1.82-.398c-.075 0-.131.056-.138.131l-.2 1.693.2 1.662c.006.075.063.131.138.131.075 0 .131-.056.138-.131l.225-1.662-.225-1.693c-.007-.075-.063-.131-.138-.131m.921-.284c-.087 0-.156.069-.162.156l-.175 1.977.175 1.937c.006.087.075.156.162.156.087 0 .156-.069.162-.156l.2-1.937-.2-1.977c-.006-.087-.075-.156-.162-.156"/>
      </svg>
      SoundCloud
    </a>`);
  }

  if (artist.instagram) {
    const handle = artist.instagram.replace('@', '');
    const url    = handle.startsWith('http') ? handle : `https://instagram.com/${handle}`;
    links.push(`<a href="${esc(url)}" class="ap-social-link" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="12" height="12">
        <rect x="2" y="2" width="20" height="20" rx="5"/>
        <circle cx="12" cy="12" r="4"/>
        <circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/>
      </svg>
      Instagram
    </a>`);
  }

  if (artist.youtube) {
    const url = artist.youtube.startsWith('http') ? artist.youtube : `https://youtube.com/@${artist.youtube}`;
    links.push(`<a href="${esc(url)}" class="ap-social-link" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12">
        <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46A2.78 2.78 0 0 0 1.46 6.42 29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58A2.78 2.78 0 0 0 3.41 19.6C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.95-1.95A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58zM9.75 15.02V8.98L15.5 12l-5.75 3.02z"/>
      </svg>
      YouTube
    </a>`);
  }

  el.innerHTML = links.join('');
}


/* ── Tracks list ─────────────────────────────────────────────────────────── */

let _tracksSorted = [];

function renderTracks(tracks, artistName) {
  _tracksSorted = [...tracks].sort((a, b) => (b.uploadedAt || 0) - (a.uploadedAt || 0));

  const el      = getEl('ap-tracks-list');
  if (!el) return;

  const countEl = getEl('ap-tracks-count');
  if (countEl) {
    countEl.textContent = tracks.length ? `${tracks.length} son${tracks.length > 1 ? 's' : ''}` : '';
  }

  if (!_tracksSorted.length) {
    el.innerHTML = `<div class="ap-tracks-empty">
      Aucun son publié pour l'instant<br>
      <span style="font-size:9px;opacity:.5;margin-top:6px;display:block">
        Upload tes créations depuis le Dashboard
      </span>
    </div>`;
    return;
  }

  el.innerHTML = _tracksSorted.map((t, i) => {
    const streamable = !!t.streamUrl;
    const playBtn    = streamable
      ? `<button class="ap-track-play-btn" onclick="event.stopPropagation(); playTrack(${i})" title="Écouter">
           <span class="ap-track-play-icon">
             <svg viewBox="0 0 24 24" fill="currentColor" width="11" height="11">
               <polygon points="5 3 19 12 5 21 5 3"/>
             </svg>
           </span>
           <span class="ap-track-eq"><span></span><span></span><span></span></span>
         </button>`
      : `<span class="ap-track-no-stream" title="Streaming non disponible">—</span>`;

    return `
    <div class="ap-track-row${streamable ? ' clickable' : ''}" id="ap-track-${i}"
         ${streamable ? `onclick="playTrack(${i})"` : ''}>
      <span class="ap-track-num">${i + 1}</span>
      <div class="ap-track-cover">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="16" height="16">
          <path d="M9 18V5l12-2v13"/>
          <circle cx="6" cy="18" r="3"/>
          <circle cx="18" cy="16" r="3"/>
        </svg>
      </div>
      <div class="ap-track-info">
        <div class="ap-track-name">${esc(t.name || 'Sans titre')}</div>
        <div class="ap-track-meta">
          ${t.genre ? `<span class="ap-track-genre">${esc(t.genre)}</span>` : ''}
          ${t.date  ? `<span class="ap-track-date">${esc(t.date)}</span>`   : ''}
        </div>
      </div>
      <div class="ap-track-right">
        ${(t.plays > 0) ? `<span class="ap-track-plays">${fmtPlays(t.plays)} ▶</span>` : ''}
        ${playBtn}
      </div>
    </div>`;
  }).join('');
}


/* ── Mini Player ─────────────────────────────────────────────────────────── */

const _audio = { el: null, idx: -1, playing: false };

function initPlayer() {
  const audioEl = getEl('amp-audio');
  if (!audioEl) return;
  _audio.el = audioEl;

  audioEl.addEventListener('timeupdate', () => {
    if (!audioEl.duration) return;
    const pct  = (audioEl.currentTime / audioEl.duration) * 100;
    const fill = getEl('amp-progress-fill');
    if (fill) fill.style.width = pct + '%';
    setEl('amp-time-current', fmtTime(audioEl.currentTime));
  });

  audioEl.addEventListener('loadedmetadata', () => {
    setEl('amp-time-duration', fmtTime(audioEl.duration));
  });

  audioEl.addEventListener('ended', () => { ampNext(); });

  audioEl.addEventListener('play',  () => { _audio.playing = true;  _updatePlayBtn(true);  });
  audioEl.addEventListener('pause', () => { _audio.playing = false; _updatePlayBtn(false); });
  audioEl.addEventListener('error', () => {
    showToast('Erreur de lecture — le son n\'est pas disponible.');
  });

  const pw = getEl('amp-progress-wrap');
  if (pw) {
    pw.addEventListener('click', (e) => {
      if (!audioEl.duration) return;
      const rect = pw.getBoundingClientRect();
      audioEl.currentTime = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * audioEl.duration;
    });
  }
}

function playTrack(sortedIdx) {
  if (!_audio.el) return;
  const t = _tracksSorted[sortedIdx];
  if (!t || !t.streamUrl) return;

  if (_audio.idx === sortedIdx) {
    _audio.el.paused ? _audio.el.play().catch(() => {}) : _audio.el.pause();
    return;
  }

  _audio.idx    = sortedIdx;
  _audio.el.src = t.streamUrl;

  document.querySelectorAll('.ap-track-row').forEach(r => r.classList.remove('playing'));
  const row = getEl(`ap-track-${sortedIdx}`);
  if (row) row.classList.add('playing');

  const playerEl = getEl('ap-mini-player');
  if (playerEl) playerEl.style.display = 'block';

  setEl('amp-title',  t.name || 'Sans titre');
  setEl('amp-artist', _artistData?.artistName || 'Artiste WATT');

  const fill = getEl('amp-progress-fill');
  if (fill) fill.style.width = '0%';
  setEl('amp-time-current', '0:00');
  setEl('amp-time-duration', '0:00');

  _audio.el.play().catch(err => {
    showToast('Lecture impossible : ' + (err.message || 'erreur'));
  });

  // Comptabiliser l'écoute
  if (t.id) {
    fetch(`/api/watt/plays/${t.id}`, { method: 'POST' }).catch(() => {});
  }
}

function ampToggle() {
  if (!_audio.el) return;
  _audio.el.paused ? _audio.el.play().catch(() => {}) : _audio.el.pause();
}

function ampPrev() {
  for (let i = _audio.idx - 1; i >= 0; i--) {
    if (_tracksSorted[i]?.streamUrl) { playTrack(i); return; }
  }
}

function ampNext() {
  for (let i = _audio.idx + 1; i < _tracksSorted.length; i++) {
    if (_tracksSorted[i]?.streamUrl) { playTrack(i); return; }
  }
}

function _updatePlayBtn(playing) {
  const btn = getEl('amp-play-btn');
  if (!btn) return;
  btn.innerHTML = playing
    ? `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
         <rect x="6" y="4" width="4" height="16"/>
         <rect x="14" y="4" width="4" height="16"/>
       </svg>`
    : `<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
         <polygon points="5 3 19 12 5 21 5 3"/>
       </svg>`;
}


/* ── Collab modal ─────────────────────────────────────────────────────────── */

function openCollabModal() {
  const modal = getEl('ap-collab-modal');
  if (modal) {
    modal.style.display = 'flex';
    const msgEl = getEl('ap-collab-msg');
    if (msgEl) msgEl.focus();
  }
}

function closeCollabModal() {
  const modal = getEl('ap-collab-modal');
  if (modal) modal.style.display = 'none';
  const msgEl   = getEl('ap-collab-msg');
  const statusEl = getEl('ap-collab-status');
  if (msgEl)    msgEl.value = '';
  if (statusEl) { statusEl.textContent = ''; statusEl.className = 'ap-collab-status'; }
}

async function sendCollab() {
  const msgEl    = getEl('ap-collab-msg');
  const statusEl = getEl('ap-collab-status');
  const sendBtn  = getEl('ap-collab-send');
  if (!msgEl || !statusEl) return;

  const message = msgEl.value.trim();
  if (!message) {
    statusEl.textContent = 'Écris un message avant d\'envoyer.';
    statusEl.className   = 'ap-collab-status error';
    return;
  }
  if (message.length > 600) {
    statusEl.textContent = 'Message trop long (max 600 caractères).';
    statusEl.className   = 'ap-collab-status error';
    return;
  }

  if (sendBtn) sendBtn.disabled = true;

  try {
    const slug = getSlugFromUrl();
    const res  = await fetch('/api/collabs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ to: slug, message }),
    });

    const data = await res.json();

    if (res.ok) {
      statusEl.textContent = '✓ Demande envoyée ! Elle apparaîtra dans le dashboard de l\'artiste.';
      statusEl.className   = 'ap-collab-status success';
      if (msgEl) msgEl.value = '';
      setTimeout(closeCollabModal, 2800);
    } else if (res.status === 401) {
      statusEl.textContent = 'Tu dois être connecté pour envoyer une demande.';
      statusEl.className   = 'ap-collab-status error';
    } else {
      statusEl.textContent = data.error || 'Erreur lors de l\'envoi.';
      statusEl.className   = 'ap-collab-status error';
    }
  } catch (_) {
    statusEl.textContent = 'Erreur réseau — réessaie.';
    statusEl.className   = 'ap-collab-status error';
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}


/* ── Share & Copy ────────────────────────────────────────────────────────── */

function copyProfileUrl() {
  const url = window.location.href;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url)
      .then(() => { _setCopied(); showToast('Lien copié dans le presse-papiers !'); })
      .catch(() => _fallbackCopy(url));
  } else {
    _fallbackCopy(url);
  }
}

function _fallbackCopy(url) {
  const ta = document.createElement('textarea');
  ta.value = url;
  ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); _setCopied(); showToast('Lien copié !'); }
  catch (_) { showToast('Copie impossible — copiez l\'URL manuellement.'); }
  document.body.removeChild(ta);
}

function _setCopied() {
  const btn = getEl('ap-copy-btn');
  if (!btn) return;
  btn.textContent = '✓ Copié !';
  btn.classList.add('copied');
  setTimeout(() => { btn.textContent = 'Copier le lien'; btn.classList.remove('copied'); }, 2200);
}

function shareProfile() {
  const name = _artistData?.artistName || 'Artiste';
  if (navigator.share) {
    navigator.share({
      title: `${name} · SMYLE PLAY`,
      text:  `Découvre les créations musicales IA de ${name} sur SMYLE PLAY`,
      url:   window.location.href,
    }).catch(() => {});
  } else {
    copyProfileUrl();
  }
}


/* ── Toast ───────────────────────────────────────────────────────────────── */

let _toastTimer = null;
function showToast(msg) {
  const el = getEl('ap-toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}


/* ── Not found ───────────────────────────────────────────────────────────── */

function showNotFound() {
  const nf = getEl('ap-not-found');
  const pf = getEl('ap-profile');
  if (nf) nf.style.display = 'flex';
  if (pf) pf.style.display = 'none';
  document.title = 'Profil introuvable · SMYLE PLAY';
}


/* ── Init ────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  initPlayer();
  loadAndRender();

  // Fermer le modal collab avec Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeCollabModal();
  });
});
