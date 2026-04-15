/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — artiste.js
   Sprint C · Page artiste publique · /artiste/nom-artiste
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function slugify(name) {
  return (name || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')   // accents
    .replace(/[^a-z0-9\s-]/g, '')      // caractères spéciaux
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

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


/* ── URL slug ────────────────────────────────────────────────────────────── */

function getSlugFromUrl() {
  // /artiste/nom-artiste → "nom-artiste"
  const m = window.location.pathname.match(/\/artiste\/([^/]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}


/* ── Data loading ────────────────────────────────────────────────────────── */

function loadArtistData(slug) {
  if (!slug) return null;

  // 1. Profil de l'utilisateur courant (localStorage)
  const profile = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
  if (profile && profile.artistName) {
    const profileSlug = profile.slug || slugify(profile.artistName);
    if (profileSlug === slug) {
      const tracks = JSON.parse(localStorage.getItem('smyle_watt_tracks') || '[]');
      const avatar = localStorage.getItem('smyle_watt_avatar') || null;
      return { profile, tracks, avatar, isMe: true };
    }
  }

  // 2. Artistes communautaires (futur : d'autres artistes inscrits)
  const community = JSON.parse(localStorage.getItem('smyle_watt_community') || '[]');
  const artist = community.find(a => {
    const s = a.slug || slugify(a.artistName);
    return s === slug;
  });
  if (artist) {
    return {
      profile: artist,
      tracks:  artist.tracks || [],
      avatar:  artist.avatar || null,
      isMe:    false,
    };
  }

  return null;
}


/* ── WATT Ranking ────────────────────────────────────────────────────────── */

function getWattRank(artistName) {
  const myTracks   = JSON.parse(localStorage.getItem('smyle_watt_tracks')   || '[]');
  const community  = JSON.parse(localStorage.getItem('smyle_watt_community') || '[]');
  const myProfile  = JSON.parse(localStorage.getItem('smyle_watt_profile')   || 'null');

  const artists = [...community];
  if (myProfile && myProfile.artistName) {
    const totalPlays = myTracks.reduce((s, t) => s + (t.plays || 0), 0);
    artists.push({ artistName: myProfile.artistName, plays: totalPlays });
  }

  artists.sort((a, b) => (b.plays || 0) - (a.plays || 0));
  const idx = artists.findIndex(a => a.artistName === artistName);
  return idx >= 0 ? idx + 1 : null;
}


/* ── Render page ─────────────────────────────────────────────────────────── */

let _artistData = null;

function renderPage() {
  const slug = getSlugFromUrl();
  const data  = loadArtistData(slug);

  if (!data) {
    showNotFound();
    return;
  }

  _artistData = data;
  const { profile, tracks, avatar } = data;

  // Title / OG
  const pageTitle = `${profile.artistName} · SMYLE PLAY`;
  document.title = pageTitle;
  _updateMeta('og:title',     pageTitle);
  _updateMeta('og:description', profile.bio || `Découvre les créations musicales IA de ${profile.artistName} sur SMYLE PLAY`);
  _updateMeta('twitter:title',  pageTitle);
  _updateMeta('twitter:description', profile.bio || 'Musique IA · SMYLE PLAY');

  // Avatar
  const avatarEl = getEl('ap-avatar');
  if (avatarEl) {
    if (avatar) {
      avatarEl.innerHTML = `<img src="${avatar}" alt="${esc(profile.artistName)}" />`;
    } else {
      avatarEl.textContent = (profile.artistName || '?')[0].toUpperCase();
    }
  }

  // Nom, genre, bio
  setEl('ap-artist-name', profile.artistName || 'Artiste WATT');

  const genreEl = getEl('ap-genre-tag');
  if (genreEl) {
    if (profile.genre) {
      genreEl.textContent = profile.genre;
      genreEl.style.display = 'inline-block';
    } else {
      genreEl.style.display = 'none';
    }
  }

  const bioEl = getEl('ap-bio');
  if (bioEl) {
    if (profile.bio) {
      bioEl.textContent = profile.bio;
      bioEl.style.display = 'block';
    } else {
      bioEl.style.display = 'none';
    }
  }

  // Réseaux sociaux
  renderSocials(profile);

  // Stats
  const totalPlays = tracks.reduce((s, t) => s + (t.plays || 0), 0);
  setEl('ap-nb-tracks', tracks.length);
  setEl('ap-nb-plays',  totalPlays);

  // Classement WATT
  const rank    = getWattRank(profile.artistName);
  const rankStr = rank ? `#${rank}` : '#—';
  setEl('ap-watt-rank', rankStr);
  setEl('ap-rank-num',  rankStr);

  // Liste des sons
  renderTracks(tracks, profile.artistName);

  // Share URL
  const shareUrl = window.location.href;
  const urlEl = getEl('ap-share-url');
  if (urlEl) urlEl.textContent = shareUrl;

  // Afficher le profil
  getEl('ap-profile').style.display = 'block';
}

function _updateMeta(property, content) {
  const el = document.querySelector(`[property="${property}"]`) ||
             document.querySelector(`[name="${property}"]`);
  if (el) el.setAttribute('content', content);
}


/* ── Réseaux sociaux ─────────────────────────────────────────────────────── */

function renderSocials(profile) {
  const el = getEl('ap-socials');
  if (!el) return;

  const links = [];

  if (profile.soundcloud) {
    const url = profile.soundcloud.startsWith('http') ? profile.soundcloud : `https://soundcloud.com/${profile.soundcloud}`;
    links.push(`<a href="${esc(url)}" class="ap-social-link" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12">
        <path d="M1.175 12.225c-.056 0-.094.038-.1.094l-.233 2.154.233 2.105c.006.05.044.088.1.088.05 0 .088-.038.1-.088l.262-2.105-.262-2.154c-.012-.056-.05-.094-.1-.094m-.899.828c-.069 0-.119.05-.125.119L0 14.479l.151 1.307c.006.069.056.119.125.119s.119-.05.125-.119l.169-1.307-.169-1.307c-.006-.069-.056-.119-.125-.119m1.82-.398c-.075 0-.131.056-.138.131l-.2 1.693.2 1.662c.006.075.063.131.138.131.075 0 .131-.056.138-.131l.225-1.662-.225-1.693c-.007-.075-.063-.131-.138-.131m.921-.284c-.087 0-.156.069-.162.156l-.175 1.977.175 1.937c.006.087.075.156.162.156.087 0 .156-.069.162-.156l.2-1.937-.2-1.977c-.006-.087-.075-.156-.162-.156m.937-.159c-.1 0-.175.075-.181.175l-.15 2.136.15 2.1c.006.1.081.175.181.175s.175-.075.181-.175l.169-2.1-.169-2.136c-.006-.1-.081-.175-.181-.175m3.594-1.625c-.181 0-.35.05-.494.138-.106-2.409-2.046-4.329-4.479-4.329-.612 0-1.194.125-1.719.35-.2.081-.256.163-.262.238v8.55c.006.081.069.15.156.156h6.798c.081-.006.15-.075.156-.156V11.64c-.006-.081-.075-.15-.156-.156"/>
      </svg>
      SoundCloud
    </a>`);
  }

  if (profile.instagram) {
    const handle = profile.instagram.replace('@', '');
    const url = handle.startsWith('http') ? handle : `https://instagram.com/${handle}`;
    links.push(`<a href="${esc(url)}" class="ap-social-link" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="12" height="12">
        <rect x="2" y="2" width="20" height="20" rx="5"/>
        <circle cx="12" cy="12" r="4"/>
        <circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/>
      </svg>
      Instagram
    </a>`);
  }

  if (profile.youtube) {
    const url = profile.youtube.startsWith('http') ? profile.youtube : `https://youtube.com/@${profile.youtube}`;
    links.push(`<a href="${esc(url)}" class="ap-social-link" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12">
        <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46A2.78 2.78 0 0 0 1.46 6.42 29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58A2.78 2.78 0 0 0 3.41 19.6C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.95-1.95A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58zM9.75 15.02V8.98L15.5 12l-5.75 3.02z"/>
      </svg>
      YouTube
    </a>`);
  }

  el.innerHTML = links.length ? links.join('') : '';
}


/* ── Tracks list ─────────────────────────────────────────────────────────── */

let _tracksSorted = [];

function renderTracks(tracks, artistName) {
  _tracksSorted = [...tracks].sort((a, b) => (b.uploadedAt || 0) - (a.uploadedAt || 0));

  const el = getEl('ap-tracks-list');
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
    const coverHTML = t.coverDataUrl
      ? `<img src="${t.coverDataUrl}" alt="" />`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="16" height="16">
           <path d="M9 18V5l12-2v13"/>
           <circle cx="6" cy="18" r="3"/>
           <circle cx="18" cy="16" r="3"/>
         </svg>`;

    const streamable = !!t.streamUrl;

    const playBtnHTML = streamable
      ? `<button class="ap-track-play-btn" onclick="event.stopPropagation(); playTrack(${i})" title="Écouter ce son">
           <span class="ap-track-play-icon">
             <svg viewBox="0 0 24 24" fill="currentColor" width="11" height="11">
               <polygon points="5 3 19 12 5 21 5 3"/>
             </svg>
           </span>
           <span class="ap-track-eq">
             <span></span><span></span><span></span>
           </span>
         </button>`
      : `<span class="ap-track-no-stream" title="Non disponible en streaming">—</span>`;

    return `
    <div class="ap-track-row${streamable ? ' clickable' : ''}" id="ap-track-${i}"
         ${streamable ? `onclick="playTrack(${i})"` : ''}>
      <span class="ap-track-num">${i + 1}</span>
      <div class="ap-track-cover">${coverHTML}</div>
      <div class="ap-track-info">
        <div class="ap-track-name">${esc(t.name || 'Sans titre')}</div>
        <div class="ap-track-meta">
          ${t.genre ? `<span class="ap-track-genre">${esc(t.genre)}</span>` : ''}
          ${t.date  ? `<span class="ap-track-date">${esc(t.date)}</span>`   : ''}
        </div>
      </div>
      <div class="ap-track-right">
        ${(t.plays > 0) ? `<span class="ap-track-plays">${t.plays} ▶</span>` : ''}
        ${playBtnHTML}
      </div>
    </div>`;
  }).join('');
}


/* ── Mini Player ─────────────────────────────────────────────────────────── */

const _audio = {
  el:       null,
  idx:      -1,
  playing:  false,
};

function initPlayer() {
  const audioEl = document.getElementById('amp-audio');
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

  audioEl.addEventListener('play', () => {
    _audio.playing = true;
    _updatePlayBtn(true);
  });
  audioEl.addEventListener('pause', () => {
    _audio.playing = false;
    _updatePlayBtn(false);
  });
  audioEl.addEventListener('error', () => {
    showToast('Erreur de lecture — le son n\'est pas disponible.');
  });

  // Progress seek (click + touch)
  const pw = getEl('amp-progress-wrap');
  if (pw) {
    pw.addEventListener('click', (e) => {
      if (!audioEl.duration) return;
      const rect = pw.getBoundingClientRect();
      const pct  = (e.clientX - rect.left) / rect.width;
      audioEl.currentTime = Math.max(0, Math.min(1, pct)) * audioEl.duration;
    });
  }
}

function playTrack(sortedIdx) {
  if (!_audio.el) return;
  const t = _tracksSorted[sortedIdx];
  if (!t || !t.streamUrl) return;

  // Toggle pause si même piste
  if (_audio.idx === sortedIdx) {
    if (_audio.playing) { _audio.el.pause(); }
    else { _audio.el.play().catch(() => {}); }
    return;
  }

  // Nouvelle piste
  _audio.idx = sortedIdx;
  _audio.el.src = t.streamUrl;
  _audio.el.load();

  // Update track rows
  document.querySelectorAll('.ap-track-row').forEach(r => r.classList.remove('playing'));
  const row = getEl(`ap-track-${sortedIdx}`);
  if (row) row.classList.add('playing');

  // Afficher le mini player
  const playerEl = getEl('ap-mini-player');
  if (playerEl) playerEl.style.display = 'block';

  // Update mini player info
  setEl('amp-title',  t.name || 'Sans titre');
  setEl('amp-artist', _artistData?.profile?.artistName || 'Artiste WATT');

  const coverEl = getEl('amp-cover');
  if (coverEl) {
    coverEl.innerHTML = t.coverDataUrl
      ? `<img src="${t.coverDataUrl}" alt="" />`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="18" height="18">
           <path d="M9 18V5l12-2v13"/>
           <circle cx="6" cy="18" r="3"/>
           <circle cx="18" cy="16" r="3"/>
         </svg>`;
  }

  // Reset progress
  const fill = getEl('amp-progress-fill');
  if (fill) fill.style.width = '0%';
  setEl('amp-time-current', '0:00');
  setEl('amp-time-duration', '0:00');

  _audio.el.play().catch(err => {
    showToast('Lecture impossible : ' + (err.message || 'erreur'));
  });
}

function ampToggle() {
  if (!_audio.el) return;
  if (_audio.el.paused) {
    _audio.el.play().catch(() => {});
  } else {
    _audio.el.pause();
  }
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


/* ── Share & Copy ────────────────────────────────────────────────────────── */

function copyProfileUrl() {
  const url = window.location.href;

  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => {
      _setCopied();
      showToast('Lien copié dans le presse-papiers !');
    }).catch(() => _fallbackCopy(url));
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
  catch (e) { showToast('Copie impossible — copiez l\'URL manuellement.'); }
  document.body.removeChild(ta);
}

function _setCopied() {
  const btn = getEl('ap-copy-btn');
  if (!btn) return;
  btn.textContent = '✓ Copié !';
  btn.classList.add('copied');
  setTimeout(() => {
    btn.textContent = 'Copier le lien';
    btn.classList.remove('copied');
  }, 2200);
}

function shareProfile() {
  const name = _artistData?.profile?.artistName || 'Artiste';
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
  renderPage();
});
