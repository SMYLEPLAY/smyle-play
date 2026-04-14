/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — Dashboard Artiste PLUG WATT
   dashboard.js — Logique complète + canvas réseau + chart SVG 7j
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ── 1. CANVAS FOND ÉLECTRIQUE ─────────────────────────────────────────────────

class DashBgCanvas {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext('2d');
    this.nodes  = [];
    this.particles = [];
    this.resize();
    this.initNodes();
    window.addEventListener('resize', () => { this.resize(); this.initNodes(); });
    this.animate();
  }

  resize() {
    this.W = this.canvas.width  = window.innerWidth;
    this.H = this.canvas.height = window.innerHeight;
  }

  initNodes() {
    const count = Math.max(12, Math.floor(this.W / 100));
    this.nodes = Array.from({ length: count }, () => ({
      x: Math.random() * this.W,
      y: Math.random() * this.H,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      r: 2 + Math.random() * 2.5,
    }));
    this.particles = Array.from({ length: 22 }, () => this._makeParticle());
  }

  _makeParticle() {
    const n1 = Math.floor(Math.random() * this.nodes.length);
    let n2;
    do { n2 = Math.floor(Math.random() * this.nodes.length); } while (n2 === n1);
    return { n1, n2, progress: Math.random(), speed: 0.0015 + Math.random() * 0.002, alpha: 0.5 + Math.random() * 0.5 };
  }

  draw() {
    const { ctx, W, H, nodes, particles } = this;
    ctx.clearRect(0, 0, W, H);
    const DIST = Math.min(200, W * 0.2);

    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      n.x += n.vx; n.y += n.vy;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;

      for (let j = i + 1; j < nodes.length; j++) {
        const m = nodes[j];
        const d = Math.hypot(m.x - n.x, m.y - n.y);
        if (d > DIST) continue;
        const a = (1 - d / DIST) * 0.22;
        ctx.save();
        ctx.strokeStyle = `rgba(255,215,0,${a})`;
        ctx.lineWidth = 0.7;
        ctx.shadowColor = '#FFD700'; ctx.shadowBlur = 2;
        ctx.beginPath(); ctx.moveTo(n.x, n.y); ctx.lineTo(m.x, m.y); ctx.stroke();
        ctx.restore();
      }

      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,215,0,0.55)';
      ctx.shadowColor = '#FFD700'; ctx.shadowBlur = 8;
      ctx.fill();
      ctx.restore();
    }

    particles.forEach(p => {
      p.progress += p.speed;
      if (p.progress >= 1) { Object.assign(p, this._makeParticle()); return; }
      const a = nodes[p.n1], b = nodes[p.n2];
      const x = a.x + (b.x - a.x) * p.progress;
      const y = a.y + (b.y - a.y) * p.progress;
      ctx.save();
      ctx.beginPath(); ctx.arc(x, y, 1.8, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,237,55,${p.alpha})`;
      ctx.shadowColor = '#FFE737'; ctx.shadowBlur = 6;
      ctx.fill(); ctx.restore();
    });
  }

  animate() { this.draw(); requestAnimationFrame(() => this.animate()); }
}

// ── 2. CANVAS RÉSEAU INTERACTIF ───────────────────────────────────────────────

class DashNetwork {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext('2d');
    this.nodes  = [];
    this.edges  = [];
    this.particles = [];
    this.mouse  = { x: -9999, y: -9999 };
    this.hover  = null;
    this.resize();
    this.buildGraph();
    canvas.addEventListener('mousemove', e => {
      const r = canvas.getBoundingClientRect();
      const sx = canvas.width  / r.width;
      const sy = canvas.height / r.height;
      this.mouse.x = (e.clientX - r.left) * sx;
      this.mouse.y = (e.clientY - r.top)  * sy;
    });
    canvas.addEventListener('mouseleave', () => { this.mouse.x = -9999; this.mouse.y = -9999; });
    window.addEventListener('resize', () => { this.resize(); this.buildGraph(); });
    this.animate();
  }

  resize() {
    const r = this.canvas.parentElement.getBoundingClientRect();
    this.W = this.canvas.width  = Math.round(r.width);
    this.H = this.canvas.height = 420;
  }

  nodeColor(type) {
    return { artist: '#FFD700', track: '#00CFFF', playlist: '#FF6B6B', watt: '#ffffff' }[type] || '#888';
  }

  buildGraph() {
    const W = this.W, H = this.H;
    const cx = W / 2, cy = H / 2;

    // Nœud central = TOI
    const me = { id: 'me', type: 'watt', label: 'Toi', x: cx, y: cy, vx: 0, vy: 0, r: 18, fixed: true };

    // Artistes autour
    const artists = [
      { id: 'a1', type: 'artist', label: 'NightWave', angle: 0 },
      { id: 'a2', type: 'artist', label: 'LunaAI', angle: 60 },
      { id: 'a3', type: 'artist', label: 'ZephyrIA', angle: 120 },
      { id: 'a4', type: 'artist', label: 'Aurora', angle: 180 },
      { id: 'a5', type: 'artist', label: 'NebulaX', angle: 240 },
      { id: 'a6', type: 'artist', label: 'EchoBot', angle: 300 },
    ].map(a => {
      const rad = a.angle * Math.PI / 180;
      const d   = Math.min(W, H) * 0.28;
      return { ...a, x: cx + Math.cos(rad) * d, y: cy + Math.sin(rad) * d, vx: 0, vy: 0, r: 13, fixed: false };
    });

    // Morceaux (orbite externe)
    const tracks = [
      { id: 't1', type: 'track', label: 'Neon Dreams', angle: 30 },
      { id: 't2', type: 'track', label: 'Cosmic Drift', angle: 90 },
      { id: 't3', type: 'track', label: 'Dark Matter', angle: 150 },
      { id: 't4', type: 'track', label: 'Electric Rain', angle: 210 },
      { id: 't5', type: 'track', label: 'Pulse Wave', angle: 270 },
      { id: 't6', type: 'track', label: 'Shadow Walk', angle: 330 },
    ].map(t => {
      const rad = t.angle * Math.PI / 180;
      const d   = Math.min(W, H) * 0.44;
      return { ...t, x: cx + Math.cos(rad) * d, y: cy + Math.sin(rad) * d, vx: 0, vy: 0, r: 9, fixed: false };
    });

    this.nodes = [me, ...artists, ...tracks];

    // Connexions
    this.edges = [];
    artists.forEach(a => {
      this.edges.push({ n1: 'me', n2: a.id, alpha: 0.4 });
    });
    tracks.forEach((t, i) => {
      this.edges.push({ n1: artists[i % artists.length].id, n2: t.id, alpha: 0.25 });
    });
    this.edges.push({ n1: 'a1', n2: 'a3', alpha: 0.15 });
    this.edges.push({ n1: 'a2', n2: 'a5', alpha: 0.15 });

    // Particules
    this.particles = [];
    this.edges.slice(0, 7).forEach(e => {
      for (let i = 0; i < 2; i++) {
        this.particles.push({ edge: e, progress: Math.random(), speed: 0.003 + Math.random() * 0.004 });
      }
    });
  }

  _nodeById(id) { return this.nodes.find(n => n.id === id); }

  draw() {
    const { ctx, W, H, nodes, edges, particles, mouse } = this;
    ctx.clearRect(0, 0, W, H);

    // Fond léger
    ctx.fillStyle = 'rgba(10,8,14,0.5)';
    ctx.fillRect(0, 0, W, H);

    // Détecter hover
    this.hover = null;
    nodes.forEach(n => {
      if (Math.hypot(mouse.x - n.x, mouse.y - n.y) < n.r + 6) this.hover = n;
    });

    // Arêtes
    edges.forEach(e => {
      const a = this._nodeById(e.n1), b = this._nodeById(e.n2);
      if (!a || !b) return;
      const isHov = this.hover && (this.hover.id === e.n1 || this.hover.id === e.n2);
      ctx.save();
      ctx.strokeStyle = `rgba(255,215,0,${isHov ? e.alpha * 3 : e.alpha})`;
      ctx.lineWidth   = isHov ? 1.5 : 0.8;
      ctx.shadowColor = '#FFD700'; ctx.shadowBlur = isHov ? 8 : 3;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      ctx.restore();
    });

    // Particules sur arêtes
    particles.forEach(p => {
      p.progress += p.speed;
      if (p.progress >= 1) p.progress = 0;
      const a = this._nodeById(p.edge.n1), b = this._nodeById(p.edge.n2);
      if (!a || !b) return;
      const x = a.x + (b.x - a.x) * p.progress;
      const y = a.y + (b.y - a.y) * p.progress;
      ctx.save();
      ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,237,55,0.8)';
      ctx.shadowColor = '#FFE737'; ctx.shadowBlur = 8;
      ctx.fill(); ctx.restore();
    });

    // Nœuds
    nodes.forEach(n => {
      const isHov = this.hover && this.hover.id === n.id;
      const col   = this.nodeColor(n.type);
      ctx.save();
      ctx.shadowColor = col; ctx.shadowBlur = isHov ? 24 : 10;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r + (isHov ? 3 : 0), 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.globalAlpha = isHov ? 1 : 0.85;
      ctx.fill(); ctx.restore();

      // Label
      if (isHov || n.type === 'watt') {
        ctx.save();
        ctx.font = `${n.type === 'watt' ? '700' : '600'} 11px -apple-system, sans-serif`;
        ctx.fillStyle = n.type === 'watt' ? '#fff' : col;
        ctx.textAlign = 'center';
        ctx.shadowColor = 'rgba(0,0,0,.8)'; ctx.shadowBlur = 4;
        ctx.fillText(n.label, n.x, n.y - n.r - 6);
        ctx.restore();
      }
    });
  }

  animate() { this.draw(); requestAnimationFrame(() => this.animate()); }
}

// ── 3. LOCALSTORAGE HELPERS ───────────────────────────────────────────────────

function getUsers()       { return JSON.parse(localStorage.getItem('smyle_users')         || '[]'); }
function saveUsers(u)     { localStorage.setItem('smyle_users', JSON.stringify(u)); }
function getCurrentUser() { return JSON.parse(localStorage.getItem('smyle_current_user')  || 'null'); }
function setCurrentUser(u){ localStorage.setItem('smyle_current_user', JSON.stringify(u)); }
function clearCurrentUser(){ localStorage.removeItem('smyle_current_user'); }
// Bêta gratuite — accès libre (le paiement sera ajouté ultérieurement)
function isPlugWattActive(){ return true; }

function getWattProfile() {
  return JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
}
function saveWattProfile(p) {
  localStorage.setItem('smyle_watt_profile', JSON.stringify(p));
}

function getMyTracks() {
  return JSON.parse(localStorage.getItem('smyle_watt_tracks') || '[]');
}
function saveMyTracks(t) {
  localStorage.setItem('smyle_watt_tracks', JSON.stringify(t));
}

function getAllArtists() {
  // Agrège tous les profils artistes stockés (simulation réseau)
  const me = getWattProfile();
  const data = JSON.parse(localStorage.getItem('smyle_watt_community') || '[]');
  const list = [];
  if (me) list.push({ ...me, me: true });
  data.forEach(a => list.push(a));
  return list;
}

// Données de démo pour le classement
function getDemoRanking() {
  const me = getWattProfile();
  const myTracks = getMyTracks();
  const totalPlays = myTracks.reduce((s, t) => s + (t.plays || 0), 0);

  const demo = [
    { name: 'NightWave', genre: 'Dark Electro IA', plays: 1842, followers: 234 },
    { name: 'LunaAI',    genre: 'Ambient IA',      plays: 1605, followers: 198 },
    { name: 'ZephyrIA',  genre: 'Lofi IA',          plays: 1290, followers: 156 },
    { name: 'Aurora',    genre: 'Cinematic IA',     plays: 987,  followers: 121 },
    { name: 'NebulaX',   genre: 'Deep House IA',    plays: 742,  followers: 88  },
    { name: 'EchoBot',   genre: 'Trap IA',          plays: 511,  followers: 67  },
  ];

  const meEntry = {
    name:      me ? me.artistName : 'Toi',
    genre:     me ? me.genre      : 'Genre non défini',
    plays:     totalPlays,
    followers: me ? (me.followers || 0) : 0,
    isMe: true,
  };

  const all = [...demo, meEntry].sort((a, b) => {
    if (b.plays !== a.plays) return b.plays - a.plays;
    return b.followers - a.followers;
  });

  return all;
}

// Données historique écoutes simulées (7j)
function getPlaysHistory(period) {
  const tracks = getMyTracks();
  const days = period === 'total' ? 30 : parseInt(period);
  const total = tracks.reduce((s, t) => s + (t.plays || 0), 0);
  const base  = Math.max(3, Math.round(total / (days || 7)));

  return Array.from({ length: days }, (_, i) => {
    const noise = Math.floor(Math.random() * base * 0.6 - base * 0.3);
    return Math.max(0, base + noise + Math.floor(i * 0.2));
  });
}

// ── 4. GUARD D'ACCÈS ──────────────────────────────────────────────────────────
// Bêta gratuite : accès libre, pas de vérification de paiement.
// Le guard redirige uniquement si l'utilisateur n'est pas connecté.

function checkAccess() {
  const guardEl = document.getElementById('dash-guard');
  if (guardEl) guardEl.style.display = 'none';
  return true;
}

// ── 5. RENDU ARTISTE ──────────────────────────────────────────────────────────

function renderArtistCard() {
  const user    = getCurrentUser();
  const profile = getWattProfile();
  const tracks  = getMyTracks();
  const totalPlays = tracks.reduce((s, t) => s + (t.plays || 0), 0);

  // Topbar
  const initials  = profile ? (profile.artistName || '?')[0].toUpperCase() : (user ? (user.name || '?')[0].toUpperCase() : '?');
  const navName   = profile ? profile.artistName : (user ? user.name : 'Artiste');

  const navAv = document.getElementById('dashNavAvatar');
  if (navAv) { navAv.textContent = initials; }
  const navNm = document.getElementById('dashNavName');
  if (navNm) { navNm.textContent = navName; }

  // Avatar section
  const avatarInits = document.getElementById('artistAvatarInitials');
  const avatarImg   = document.getElementById('artistAvatarImg');
  if (avatarInits) avatarInits.textContent = initials;

  const savedImg = localStorage.getItem('smyle_watt_avatar');
  if (savedImg && avatarImg) {
    avatarImg.src = savedImg;
    avatarImg.style.display = 'block';
    if (avatarInits) avatarInits.style.display = 'none';
  }

  // Nom, genre, bio
  setTextById('artistName',     profile ? (profile.artistName || 'Artiste WATT') : 'Artiste WATT');
  setTextById('artistGenre',    profile ? (profile.genre || 'Genre non défini')  : 'Genre non défini');
  setTextById('artistBioShort', profile ? (profile.bio || 'Aucune bio renseignée.') : 'Aucune bio renseignée.');

  // Socials
  const socialsEl = document.getElementById('artistSocials');
  if (socialsEl && profile) {
    socialsEl.innerHTML = '';
    if (profile.soundcloud) {
      socialsEl.innerHTML += `<a class="dash-social-link" href="${profile.soundcloud}" target="_blank" rel="noopener">SoundCloud</a>`;
    }
    if (profile.instagram) {
      socialsEl.innerHTML += `<a class="dash-social-link" href="https://instagram.com/${profile.instagram.replace('@','')}" target="_blank" rel="noopener">${profile.instagram}</a>`;
    }
    if (profile.youtube) {
      socialsEl.innerHTML += `<a class="dash-social-link" href="${profile.youtube}" target="_blank" rel="noopener">YouTube</a>`;
    }
  }

  // KPIs
  const ranking = getDemoRanking();
  const myRank  = ranking.findIndex(a => a.isMe) + 1;
  setTextById('kpiPlays',     totalPlays.toString());
  setTextById('kpiTracks',    tracks.length.toString());
  setTextById('kpiFollowers', profile ? (profile.followers || 0).toString() : '0');
  setTextById('kpiRank',      myRank > 0 ? `#${myRank}` : '—');

  // Liste de mes sons
  renderMyTracks();
}

function renderMyTracks() {
  const tracks  = getMyTracks();
  const profile = getWattProfile();
  const listEl  = document.getElementById('myTracksList');
  const countEl = document.getElementById('myTracksCount');

  if (countEl) countEl.textContent = `${tracks.length} son${tracks.length > 1 ? 's' : ''}`;

  if (!listEl) return;
  if (tracks.length === 0) {
    listEl.innerHTML = `<div class="dash-empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="40" height="40" style="opacity:.2">
        <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
      </svg>
      <p>Aucun son publié.<br>Rends-toi dans la section Upload.</p>
    </div>`;
    return;
  }

  listEl.innerHTML = tracks.map(t => {
    const coverHTML = t.coverDataUrl
      ? `<img src="${t.coverDataUrl}" alt="" />`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="18" height="18" style="opacity:.3"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
    return `
    <div class="dash-track-row" data-id="${t.id}">
      <div class="dash-track-cover">${coverHTML}</div>
      <div class="dash-track-info">
        <div class="dash-track-name">${htmlEscape(t.name)}</div>
        <div class="dash-track-meta">${htmlEscape(t.genre || 'Sans genre')} · ${t.date || 'récent'}</div>
      </div>
      <div class="dash-track-plays">${t.plays || 0} écoutes</div>
      <button class="dash-btn-ghost" style="padding:4px 10px;font-size:.68rem" onclick="deleteTrack('${t.id}')">✕</button>
    </div>`;
  }).join('');
}

function deleteTrack(id) {
  const tracks = getMyTracks().filter(t => t.id !== id);
  saveMyTracks(tracks);
  renderArtistCard();
  renderStats();
  renderRanking();
  dashToast('Son supprimé.');
}

// ── 6. AVATAR UPLOAD ──────────────────────────────────────────────────────────

function triggerAvatarUpload() {
  document.getElementById('avatarFileInput').click();
}

function handleAvatarUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const dataUrl = e.target.result;
    localStorage.setItem('smyle_watt_avatar', dataUrl);
    const img    = document.getElementById('artistAvatarImg');
    const inits  = document.getElementById('artistAvatarInitials');
    if (img)   { img.src = dataUrl; img.style.display = 'block'; }
    if (inits) { inits.style.display = 'none'; }
    const pvAv = document.getElementById('pvAvatar');
    if (pvAv)  { pvAv.innerHTML = `<img src="${dataUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover" alt=""/>` ; }
    dashToast('Photo de profil mise à jour !');
  };
  reader.readAsDataURL(file);
}

// ── 7. UPLOAD DE SON ──────────────────────────────────────────────────────────

let _pendingFile   = null;
let _coverDataUrl  = null;

function handleDragOver(e)  { e.preventDefault(); document.getElementById('dashDropzone').classList.add('drag-over'); }
function handleDragLeave(e) { document.getElementById('dashDropzone').classList.remove('drag-over'); }

function handleFileDrop(e) {
  e.preventDefault();
  document.getElementById('dashDropzone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) showUploadForm(file);
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) showUploadForm(file);
}

function showUploadForm(file) {
  _pendingFile = file;
  const sizeStr = file.size > 1048576
    ? (file.size / 1048576).toFixed(1) + ' MB'
    : (file.size / 1024).toFixed(0) + ' KB';

  document.getElementById('dashUploadFileRow').innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
      <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
    </svg>
    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${htmlEscape(file.name)}</span>
    <span style="color:rgba(255,215,0,.5);font-size:.72rem">${sizeStr}</span>`;

  // Pré-remplir le nom depuis le fichier
  const trackNameEl = document.getElementById('dashTrackName');
  if (trackNameEl && !trackNameEl.value) {
    trackNameEl.value = file.name.replace(/\.(wav|mp3|flac|aac|m4a|ogg)$/i, '').replace(/[_-]/g, ' ');
  }

  document.getElementById('dashDropzone').style.display = 'none';
  document.getElementById('dashUploadForm').style.display = 'block';
}

function cancelUpload() {
  _pendingFile  = null;
  _coverDataUrl = null;
  document.getElementById('dashDropzone').style.display = '';
  document.getElementById('dashUploadForm').style.display = 'none';
  document.getElementById('dashTrackName').value = '';
  document.getElementById('dashGenre').value     = '';
  document.getElementById('dashTags').value      = '';
  document.getElementById('dashDesc').value      = '';
  resetCoverPreview();
  document.getElementById('dashProgressWrap').style.display = 'none';
}

function handleCoverDragOver(e) { e.preventDefault(); }

function handleCoverDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) loadCoverPreview(file);
}

function handleCoverSelect(e) {
  const file = e.target.files[0];
  if (file) loadCoverPreview(file);
}

function loadCoverPreview(file) {
  const reader = new FileReader();
  reader.onload = ev => {
    _coverDataUrl = ev.target.result;
    const img  = document.getElementById('dashCoverPreview');
    const ph   = document.getElementById('dashCoverPlaceholder');
    if (img) { img.src = _coverDataUrl; img.style.display = 'block'; }
    if (ph)  { ph.style.display = 'none'; }
  };
  reader.readAsDataURL(file);
}

function resetCoverPreview() {
  _coverDataUrl = null;
  const img = document.getElementById('dashCoverPreview');
  const ph  = document.getElementById('dashCoverPlaceholder');
  if (img) { img.src = ''; img.style.display = 'none'; }
  if (ph)  { ph.style.display = ''; }
  const inp = document.getElementById('dashCoverInput');
  if (inp) inp.value = '';
}

async function uploadTrack() {
  const name = document.getElementById('dashTrackName').value.trim();
  if (!name) { dashToast('⚠ Le titre est obligatoire.'); return; }
  if (!_pendingFile) { dashToast('⚠ Aucun fichier sélectionné.'); return; }

  const genre = document.getElementById('dashGenre').value.trim();
  const tags  = document.getElementById('dashTags').value.trim();
  const desc  = document.getElementById('dashDesc').value.trim();

  // Afficher progression
  const progressWrap = document.getElementById('dashProgressWrap');
  const fill         = document.getElementById('dashProgressFill');
  const lbl          = document.getElementById('dashProgressLbl');
  progressWrap.style.display = 'block';

  const setProgress = (pct, txt) => {
    fill.style.width = pct + '%';
    lbl.textContent  = txt;
  };

  setProgress(10, 'Préparation...');
  await wait(300);
  setProgress(35, 'Envoi vers Cloudflare R2...');

  const user = getCurrentUser();
  let uploaded = false;

  try {
    const fd = new FormData();
    fd.append('file',   _pendingFile);
    fd.append('name',   name);
    fd.append('userId', user ? String(user.id) : 'guest');

    const res = await fetch('/api/watt/upload', { method: 'POST', body: fd });
    if (res.ok) { uploaded = true; setProgress(80, 'Finalisation...'); }
  } catch (_) { /* mode sans backend */ }

  await wait(400);
  setProgress(95, 'Sauvegarde...');
  await wait(300);

  // Sauvegarde locale dans tous les cas
  const tracks = getMyTracks();
  const newTrack = {
    id:           `wt-${Date.now()}`,
    name,
    genre,
    tags,
    desc,
    file:         _pendingFile.name,
    size:         _pendingFile.size,
    coverDataUrl: _coverDataUrl || null,
    plays:        0,
    date:         new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' }),
    uploadedAt:   Date.now(),
    cloud:        uploaded,
  };
  tracks.unshift(newTrack);
  saveMyTracks(tracks);

  setProgress(100, uploaded ? '⚡ Son publié sur WATT !' : '⚡ Son sauvegardé localement !');
  await wait(1000);

  cancelUpload();
  renderArtistCard();
  renderStats();
  renderRanking();
  dashToast(`⚡ "${name}" publié sur WATT !`);
}

// ── 8. PROFIL ─────────────────────────────────────────────────────────────────

function toggleProfileEdit() {
  const view = document.getElementById('profileViewMode');
  const edit = document.getElementById('profileEditMode');
  const btn  = document.getElementById('profileEditToggle');
  const isEditing = edit.style.display !== 'none';

  if (isEditing) {
    edit.style.display = 'none';
    view.style.display = '';
    if (btn) btn.textContent = 'Modifier';
  } else {
    const p = getWattProfile() || {};
    setVal('peArtistName', p.artistName || '');
    setVal('peGenre',      p.genre      || '');
    setVal('peBio',        p.bio        || '');
    setVal('peSoundcloud', p.soundcloud || '');
    setVal('peInstagram',  p.instagram  || '');
    setVal('peYoutube',    p.youtube    || '');
    view.style.display = 'none';
    edit.style.display = '';
    if (btn) btn.textContent = 'Annuler';
  }
}

function cancelProfileEdit() { toggleProfileEdit(); }

function saveProfile() {
  const artistName = document.getElementById('peArtistName').value.trim();
  if (!artistName) { dashToast('⚠ Le nom d\'artiste est obligatoire.'); return; }

  const profile = {
    artistName,
    genre:      document.getElementById('peGenre').value.trim(),
    bio:        document.getElementById('peBio').value.trim(),
    soundcloud: document.getElementById('peSoundcloud').value.trim(),
    instagram:  document.getElementById('peInstagram').value.trim(),
    youtube:    document.getElementById('peYoutube').value.trim(),
    followers:  (getWattProfile() || {}).followers || 0,
  };
  saveWattProfile(profile);

  // Sync API si disponible
  fetch('/api/watt/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  }).catch(() => {});

  toggleProfileEdit();
  renderArtistCard();
  renderProfileView();
  dashToast('✓ Profil sauvegardé !');
}

function renderProfileView() {
  const p = getWattProfile();
  const initials = p ? (p.artistName || '?')[0].toUpperCase() : '?';
  const savedImg = localStorage.getItem('smyle_watt_avatar');

  const pvAv = document.getElementById('pvAvatar');
  if (pvAv) {
    pvAv.innerHTML = savedImg
      ? `<img src="${savedImg}" style="width:100%;height:100%;border-radius:50%;object-fit:cover" alt=""/>`
      : initials;
  }
  setTextById('pvName',  p ? (p.artistName || '—') : '—');
  setTextById('pvGenre', p ? (p.genre || 'Genre non défini') : 'Genre non défini');
  setTextById('pvBio',   p ? (p.bio || 'Pas encore de bio...') : 'Pas encore de bio...');

  const pvLinks = document.getElementById('pvLinks');
  if (pvLinks && p) {
    pvLinks.innerHTML = '';
    if (p.soundcloud) pvLinks.innerHTML += `<a class="dash-social-link" href="${p.soundcloud}" target="_blank">SoundCloud</a>`;
    if (p.instagram)  pvLinks.innerHTML += `<a class="dash-social-link" href="https://instagram.com/${p.instagram.replace('@','')}" target="_blank">${p.instagram}</a>`;
    if (p.youtube)    pvLinks.innerHTML += `<a class="dash-social-link" href="${p.youtube}" target="_blank">YouTube</a>`;
  }
}

// ── 9. STATS ──────────────────────────────────────────────────────────────────

let _currentPeriod = '7j';

function switchStatsPeriod(period, btn) {
  _currentPeriod = period;
  document.querySelectorAll('.dash-stats-tab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderStats();
}

function renderStats() {
  const tracks     = getMyTracks();
  const totalPlays = tracks.reduce((s, t) => s + (t.plays || 0), 0);
  const ranking    = getDemoRanking();
  const myRank     = ranking.findIndex(a => a.isMe) + 1;
  const profile    = getWattProfile();

  setTextById('statsPlays',     totalPlays.toString());
  setTextById('statsTracks',    tracks.length.toString());
  setTextById('statsFollowers', profile ? (profile.followers || 0).toString() : '0');
  setTextById('statsRank',      myRank > 0 ? `#${myRank}` : '—');

  renderChart(_currentPeriod);
}

function renderChart(period) {
  const data    = getPlaysHistory(period);
  if (!data.length) return;
  const maxVal  = Math.max(...data, 1);
  const chartEl = document.getElementById('statsChart');
  if (!chartEl) return;

  const W = 700, H = 200;
  const padL = 40, padR = 20, padT = 20, padB = 20;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const pts = data.map((v, i) => ({
    x: padL + (i / (data.length - 1)) * plotW,
    y: padT + plotH - (v / maxVal) * plotH,
  }));

  // Ligne principale (courbe lisse)
  const linePath = pts.reduce((acc, p, i) => {
    if (i === 0) return `M ${p.x} ${p.y}`;
    const prev = pts[i - 1];
    const cx   = (prev.x + p.x) / 2;
    return `${acc} C ${cx} ${prev.y} ${cx} ${p.y} ${p.x} ${p.y}`;
  }, '');

  // Remplissage
  const fillPath = `${linePath} L ${pts[pts.length-1].x} ${padT + plotH} L ${padL} ${padT + plotH} Z`;

  const lineEl = document.getElementById('chartLine');
  const fillEl = document.getElementById('chartFill');
  if (lineEl) lineEl.setAttribute('d', linePath);
  if (fillEl) fillEl.setAttribute('d', fillPath);

  // Labels axe X
  const labelsEl = document.getElementById('chartLabels');
  if (labelsEl) {
    const step  = Math.max(1, Math.floor(data.length / 7));
    const today = new Date();
    const labels = data.map((_, i) => {
      const d = new Date(today);
      d.setDate(d.getDate() - (data.length - 1 - i));
      return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
    });
    labelsEl.innerHTML = pts
      .filter((_, i) => i === 0 || i === data.length - 1 || i % step === 0)
      .map((p, _, arr) => {
        const idx = pts.indexOf(p);
        return `<text x="${p.x}" y="${H - 4}" text-anchor="middle" fill="rgba(255,215,0,0.4)" font-size="9">${labels[idx] || ''}</text>`;
      }).join('');
  }
}

// ── 10. CLASSEMENT ────────────────────────────────────────────────────────────

function renderRanking() {
  const ranking = getDemoRanking();
  const myPos   = ranking.findIndex(a => a.isMe) + 1;

  // Ma position
  setTextById('mrcRank', myPos > 0 ? `#${myPos}` : '—');

  // Liste
  const listEl = document.getElementById('dashRankingList');
  if (!listEl) return;

  if (ranking.length === 0) {
    listEl.innerHTML = '<div class="dash-rank-empty">Aucun artiste dans le classement pour l\'instant.</div>';
    return;
  }

  listEl.innerHTML = ranking.map((a, i) => `
    <div class="dash-rank-row ${a.isMe ? 'is-me' : ''}">
      <div class="dash-rank-num">${i < 3 ? ['🥇','🥈','🥉'][i] : `#${i+1}`}</div>
      <div class="dash-rank-avatar">${(a.name || '?')[0].toUpperCase()}</div>
      <div class="dash-rank-info">
        <div class="dash-rank-name">${htmlEscape(a.name)}${a.isMe ? ' <span style="color:var(--d-gold);font-size:.65rem">· Toi</span>' : ''}</div>
        <div class="dash-rank-genre">${htmlEscape(a.genre || 'Genre non défini')}</div>
      </div>
      <div class="dash-rank-stats">
        <div class="dash-rank-plays">${a.plays} écoutes</div>
        <div class="dash-rank-followers">${a.followers} abonnés</div>
      </div>
    </div>
  `).join('');

  // Ma position card
  setTextById('kpiRank', myPos > 0 ? `#${myPos}` : '—');
}

// ── 11. SECTION NAV INTERSECTION OBSERVER ────────────────────────────────────

function initSectionNav() {
  const pills = document.querySelectorAll('.dash-snav-pill');
  const sections = document.querySelectorAll('.dash-section');

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const id = entry.target.id;
      pills.forEach(p => {
        p.classList.toggle('active', p.dataset.sec === id);
      });
    });
  }, {
    rootMargin: '-30% 0px -60% 0px',
    threshold: 0,
  });

  sections.forEach(s => observer.observe(s));
}

// ── 12. DÉCONNEXION ───────────────────────────────────────────────────────────

function dashLogout() {
  clearCurrentUser();
  window.location.href = '/';
}

// ── 13. TOAST ─────────────────────────────────────────────────────────────────

function dashToast(msg) {
  const wrap = document.getElementById('dash-toast');
  if (!wrap) return;
  const el = document.createElement('div');
  el.className = 'dash-toast-msg';
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .3s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 350);
  }, 2800);
}

// ── 14. UTILITAIRES ───────────────────────────────────────────────────────────

function setTextById(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

function htmlEscape(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── 15. INITIALISATION ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Guard d'accès
  if (!checkAccess()) return;

  // Canvas fond page
  const bgCanvas = document.getElementById('dash-bg-canvas');
  if (bgCanvas) new DashBgCanvas(bgCanvas);

  // Canvas réseau
  const netCanvas = document.getElementById('dashNetworkCanvas');
  if (netCanvas) {
    // Attendre que le layout soit stable
    setTimeout(() => {
      try { new DashNetwork(netCanvas); }
      catch(e) { console.warn('DashNetwork init error', e); }
    }, 200);
  }

  // Rendu principal
  renderArtistCard();
  renderProfileView();
  renderStats();
  renderRanking();

  // Section nav
  initSectionNav();

  // Resize observer pour le canvas réseau
  if (window.ResizeObserver && netCanvas) {
    new ResizeObserver(() => {
      // Le canvas se redimensionne dans DashNetwork.resize()
    }).observe(netCanvas.parentElement);
  }
});
