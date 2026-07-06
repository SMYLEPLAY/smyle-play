/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — Dashboard Artiste PLUG WATT
   dashboard.js — Logique complète + canvas réseau + chart SVG 7j
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ── 0. HELPERS GLOBAUX ────────────────────────────────────────────────────────

// Limite freemium — version gratuite bêta
const FREE_LIMIT = 6;

// Comptes officiels / fondateur — exemptés de la limite freemium bêta.
// IMPORTANT : on matche sur le slug ET sur le nom d'artiste slugifié.
// Le slug de profil est recalculé à la volée côté backend et peut dériver
// (cf. audit B2) ; ne tester que `p.slug` faisait "revenir" le plafond quand
// le slug changeait. Matcher aussi le nom slugifié (stable) rend l'exemption
// résiliente à cette dérive.
const OFFICIAL_SLUGS = ['smyle', 'tom-lecomte'];
function _isOfficialAccount() {
  const p = (typeof getWattProfile === 'function') ? getWattProfile() : null;
  if (!p) return false;
  const candidates = [
    (p.slug || ''),
    (typeof slugify === 'function' ? slugify(p.artistName || '') : ''),
  ].map(s => String(s).toLowerCase().trim()).filter(Boolean);
  return candidates.some(s => OFFICIAL_SLUGS.includes(s));
}

// ── Wrapper sécurisé localStorage (Safari Private Mode / quota 0 octet) ──────
const safeStorage = {
  getItem(key) {
    try { return localStorage.getItem(key); } catch(e) { return null; }
  },
  setItem(key, val) {
    try { localStorage.setItem(key, val); return true; }
    catch(e) { return false; }
  },
  removeItem(key) {
    try { localStorage.removeItem(key); } catch(e) {}
  },
  isAvailable() {
    try {
      const k = '__smyle_test__';
      localStorage.setItem(k, '1');
      localStorage.removeItem(k);
      return true;
    } catch(e) { return false; }
  },
};

function slugify(name) {
  return (name || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

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
      const r  = canvas.getBoundingClientRect();
      const sx = canvas.width  / r.width;
      const sy = canvas.height / r.height;
      this.mouse.x = (e.clientX - r.left) * sx;
      this.mouse.y = (e.clientY - r.top)  * sy;
      // Curseur pointer si nœud cliquable
      const hit = this.nodes.find(n => Math.hypot(this.mouse.x - n.x, this.mouse.y - n.y) < n.r + 8);
      canvas.style.cursor = (hit && hit.slug) ? 'pointer' : 'default';
    });

    canvas.addEventListener('click', e => {
      const r  = canvas.getBoundingClientRect();
      const sx = canvas.width  / r.width;
      const sy = canvas.height / r.height;
      const mx = (e.clientX - r.left) * sx;
      const my = (e.clientY - r.top)  * sy;
      const hit = this.nodes.find(n => Math.hypot(mx - n.x, my - n.y) < n.r + 8);
      if (hit && hit.slug) window.location.href = `/@${hit.slug}`;
    });

    // Touch support
    canvas.addEventListener('touchend', e => {
      if (e.changedTouches.length === 0) return;
      const t  = e.changedTouches[0];
      const r  = canvas.getBoundingClientRect();
      const sx = canvas.width  / r.width;
      const sy = canvas.height / r.height;
      const mx = (t.clientX - r.left) * sx;
      const my = (t.clientY - r.top)  * sy;
      const hit = this.nodes.find(n => Math.hypot(mx - n.x, my - n.y) < n.r + 12);
      if (hit && hit.slug) { e.preventDefault(); window.location.href = `/@${hit.slug}`; }
    }, { passive: false });

    canvas.addEventListener('mouseleave', () => {
      this.mouse.x = -9999; this.mouse.y = -9999;
      canvas.style.cursor = 'default';
    });
    window.addEventListener('resize', () => { this.resize(); this.buildGraph(); });
    this.animate();
  }

  resize() {
    const r = this.canvas.parentElement.getBoundingClientRect();
    this.W = this.canvas.width  = Math.round(r.width);
    this.H = this.canvas.height = Math.min(420, Math.round(window.innerHeight * 0.6));
  }

  nodeColor(type) {
    return { artist: '#FFD700', track: '#00CFFF', me: '#ffffff', watt: '#ffffff' }[type] || '#888';
  }

  // ── Construit le graphe depuis les données localStorage ──────────────────
  buildGraph() {
    const W = this.W, H = this.H;
    const cx = W / 2, cy = H / 2;

    // ── Données réelles depuis localStorage ─────────────────────────────
    const profile   = JSON.parse(safeStorage.getItem('smyle_watt_profile') || 'null');
    const myTracks  = JSON.parse(safeStorage.getItem('smyle_watt_tracks')   || '[]');
    const community = JSON.parse(safeStorage.getItem('smyle_watt_community') || '[]');

    // ── Nœud central "moi" ───────────────────────────────────────────────
    const meName = (profile && profile.artistName) ? profile.artistName : 'Toi';
    const meSlug = profile ? (profile.slug || slugify(profile.artistName || '')) : '';
    const me = {
      id: 'me', type: 'watt',
      label: meName, slug: meSlug,
      x: cx, y: cy, vx: 0, vy: 0, r: 20, fixed: true,
    };

    // ── Artistes (communauté réelle ou démo) ─────────────────────────────
    const DEMO_ARTISTS = [
      { artistName: 'NightWave', genre: 'Dark Electro', slug: 'nightwave', tracks: [] },
      { artistName: 'LunaAI',    genre: 'Ambient IA',   slug: 'lunaai',    tracks: [] },
      { artistName: 'ZephyrIA',  genre: 'Lofi IA',      slug: 'zephyria',  tracks: [] },
      { artistName: 'Aurora',    genre: 'Cinematic IA', slug: 'aurora',    tracks: [] },
      { artistName: 'NebulaX',   genre: 'Deep House IA',slug: 'nebulax',   tracks: [] },
      { artistName: 'EchoBot',   genre: 'Trap IA',      slug: 'echobot',   tracks: [] },
    ];
    const artistSource = community.length > 0 ? community : DEMO_ARTISTS;
    const maxA = Math.min(artistSource.length, 8);

    const artists = artistSource.slice(0, maxA).map((a, i) => {
      const angle = (360 / maxA) * i;
      const rad   = angle * Math.PI / 180;
      const d     = Math.min(W, H) * 0.28;
      const aSlug = a.slug || slugify(a.artistName || '');
      return {
        id: `a${i}`, type: 'artist',
        label: a.artistName || '?',
        slug: aSlug,
        trackCount: Array.isArray(a.tracks) ? a.tracks.length : 0,
        x: cx + Math.cos(rad) * d,
        y: cy + Math.sin(rad) * d,
        vx: 0, vy: 0, r: 13, fixed: false,
      };
    });

    // ── Pistes (miennes réelles ou démo) ────────────────────────────────
    const DEMO_TRACKS = ['Neon Dreams','Cosmic Drift','Dark Matter','Electric Rain','Pulse Wave','Shadow Walk'];
    const trackNames  = myTracks.length > 0
      ? myTracks.slice(0, 6).map(t => t.name || 'Sans titre')
      : DEMO_TRACKS;
    const maxT  = Math.min(trackNames.length, 6);
    const angleOffset = artists.length > 0 ? (360 / maxA / 2) : 0;

    const tracks = trackNames.slice(0, maxT).map((name, i) => {
      const angle = (360 / maxT) * i + angleOffset;
      const rad   = angle * Math.PI / 180;
      const d     = Math.min(W, H) * 0.44;
      return {
        id: `t${i}`, type: 'track',
        label: name, slug: '',
        x: cx + Math.cos(rad) * d,
        y: cy + Math.sin(rad) * d,
        vx: 0, vy: 0, r: 9, fixed: false,
      };
    });

    this.nodes = [me, ...artists, ...tracks];

    // ── Arêtes ───────────────────────────────────────────────────────────
    this.edges = [];
    artists.forEach(a => this.edges.push({ n1: 'me', n2: a.id, alpha: 0.4 }));
    tracks.forEach((t, i) => {
      const target = artists.length > 0 ? artists[i % artists.length].id : 'me';
      this.edges.push({ n1: target, n2: t.id, alpha: 0.25 });
    });
    if (artists.length >= 3) this.edges.push({ n1: artists[0].id, n2: artists[2].id, alpha: 0.15 });
    if (artists.length >= 5) this.edges.push({ n1: artists[1].id, n2: artists[4].id, alpha: 0.15 });
    if (artists.length >= 6) this.edges.push({ n1: artists[3].id, n2: artists[5].id, alpha: 0.12 });

    // ── Particules ───────────────────────────────────────────────────────
    this.particles = [];
    this.edges.slice(0, 8).forEach(e => {
      for (let i = 0; i < 2; i++)
        this.particles.push({ edge: e, progress: Math.random(), speed: 0.003 + Math.random() * 0.004 });
    });
  }

  _nodeById(id) { return this.nodes.find(n => n.id === id); }

  draw() {
    const { ctx, W, H, nodes, edges, particles, mouse } = this;
    ctx.clearRect(0, 0, W, H);

    // Fond
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
      ctx.strokeStyle = `rgba(255,215,0,${isHov ? Math.min(e.alpha * 3, 0.9) : e.alpha})`;
      ctx.lineWidth   = isHov ? 1.5 : 0.8;
      ctx.shadowColor = '#FFD700'; ctx.shadowBlur = isHov ? 10 : 3;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      ctx.restore();
    });

    // Particules
    particles.forEach(p => {
      p.progress += p.speed;
      if (p.progress >= 1) p.progress = 0;
      const a = this._nodeById(p.edge.n1), b = this._nodeById(p.edge.n2);
      if (!a || !b) return;
      const x = a.x + (b.x - a.x) * p.progress;
      const y = a.y + (b.y - a.y) * p.progress;
      ctx.save();
      ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,237,55,0.85)';
      ctx.shadowColor = '#FFE737'; ctx.shadowBlur = 8;
      ctx.fill(); ctx.restore();
    });

    // Nœuds
    nodes.forEach(n => {
      const isHov = this.hover && this.hover.id === n.id;
      const col   = this.nodeColor(n.type);

      // Halo supplémentaire sur hover pour nœuds cliquables
      if (isHov && n.slug) {
        ctx.save();
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 7, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255,215,0,0.35)`;
        ctx.lineWidth = 1.5; ctx.stroke(); ctx.restore();
      }

      ctx.save();
      ctx.shadowColor = col; ctx.shadowBlur = isHov ? 28 : 10;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r + (isHov ? 3 : 0), 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.globalAlpha = isHov ? 1 : 0.88;
      ctx.fill(); ctx.restore();

      // Initiales dans le nœud central (>= 22px)
      if (n.type === 'watt') {
        const initials = n.label.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
        ctx.save();
        ctx.font = '700 10px -apple-system,sans-serif';
        ctx.fillStyle = '#0a080e';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(initials, n.x, n.y);
        ctx.textBaseline = 'alphabetic';
        ctx.restore();
      }

      // Labels artistes — toujours visibles (+ grand sur hover)
      if (n.type === 'watt' || n.type === 'artist' || isHov) {
        ctx.save();
        const fSize = (n.type === 'watt') ? 12 : (isHov ? 12 : 10);
        const fW    = (n.type === 'watt' || isHov) ? '700' : '500';
        ctx.font = `${fW} ${fSize}px -apple-system, sans-serif`;
        ctx.fillStyle = n.type === 'watt' ? '#0a080e' : (isHov ? '#fff' : col);
        ctx.globalAlpha = isHov ? 1 : (n.type === 'artist' ? 0.78 : 0.9);
        ctx.textAlign = 'center';
        ctx.shadowColor = 'rgba(0,0,0,.95)'; ctx.shadowBlur = 6;
        const labelY = n.type === 'watt' ? n.y - n.r - 8 : n.y - n.r - 5;
        ctx.fillText(n.label, n.x, labelY);
        ctx.restore();
      }

      // Badge "N sons" sous les nœuds artistes avec pistes connues
      if (n.type === 'artist' && n.trackCount > 0) {
        ctx.save();
        ctx.font = '500 8px -apple-system, sans-serif';
        ctx.fillStyle = 'rgba(255,215,0,0.55)';
        ctx.globalAlpha = isHov ? 1 : 0.7;
        ctx.textAlign = 'center';
        ctx.shadowColor = 'rgba(0,0,0,.9)'; ctx.shadowBlur = 4;
        ctx.fillText(`${n.trackCount} son${n.trackCount > 1 ? 's' : ''}`, n.x, n.y + n.r + 12);
        ctx.restore();
      }

      // Indicateur "cliquable" (petit chevron) sur hover
      if (isHov && n.slug) {
        ctx.save();
        ctx.font = '600 9px -apple-system, sans-serif';
        ctx.fillStyle = 'rgba(255,215,0,0.9)';
        ctx.textAlign = 'center';
        ctx.shadowColor = 'rgba(0,0,0,.95)'; ctx.shadowBlur = 4;
        ctx.fillText('→ profil', n.x, n.y + n.r + (n.trackCount > 0 ? 22 : 12));
        ctx.restore();
      }
    });
  }

  animate() { this.draw(); requestAnimationFrame(() => this.animate()); }
}

// ── 3. LOCALSTORAGE HELPERS ───────────────────────────────────────────────────

function getUsers()       { return JSON.parse(safeStorage.getItem('smyle_users')         || '[]'); }
function saveUsers(u)     { safeStorage.setItem('smyle_users', JSON.stringify(u)); }
function getCurrentUser() { return JSON.parse(safeStorage.getItem('smyle_current_user')  || 'null'); }
function setCurrentUser(u){ return safeStorage.setItem('smyle_current_user', JSON.stringify(u)); }
function clearCurrentUser(){ safeStorage.removeItem('smyle_current_user'); }
// Bêta gratuite — accès libre (le paiement sera ajouté ultérieurement)
function isPlugWattActive(){ return true; }

function getWattProfile() {
  return JSON.parse(safeStorage.getItem('smyle_watt_profile') || 'null');
}
function saveWattProfile(p) {
  safeStorage.setItem('smyle_watt_profile', JSON.stringify(p));
}

function getMyTracks() {
  return JSON.parse(safeStorage.getItem('smyle_watt_tracks') || '[]');
}
function saveMyTracks(t) {
  safeStorage.setItem('smyle_watt_tracks', JSON.stringify(t));
}

function getAllArtists() {
  // Agrège tous les profils artistes stockés (simulation réseau)
  const me = getWattProfile();
  const data = JSON.parse(safeStorage.getItem('smyle_watt_community') || '[]');
  const list = [];
  if (me) list.push({ ...me, me: true });
  data.forEach(a => list.push(a));
  return list;
}

// Cache classement réel — évite un double fetch si renderStats + renderRanking s'enchaînent
let _rankingCache = null;

async function fetchRealRanking() {
  if (_rankingCache) return _rankingCache;
  try {
    const data = await apiFetch('/watt/artists');
    const artists = Array.isArray(data && data.artists) ? data.artists : [];
    const me = getWattProfile();
    const mySlug = me ? (me.slug || '') : '';

    const ranking = artists.map(a => ({
      name:      a.artistName || 'Artiste',
      genre:     a.genre      || 'Genre non défini',
      plays:     a.plays      || 0,
      followers: a.followersCount || 0,
      slug:      a.slug || '',
      isMe:      mySlug ? a.slug === mySlug : false,
    })).sort((a, b) => {
      if (b.plays !== a.plays) return b.plays - a.plays;
      return b.followers - a.followers;
    });

    _rankingCache = ranking;
    return ranking;
  } catch (err) {
    console.warn('[dashboard] fetchRealRanking :', err && err.message);
    return [];
  }
}

// ── Historique d'écoutes RÉEL (chantier vraies stats, 2026-06-10) ─────────
// Avant : courbe SIMULÉE générée côté client (getPlaysHistory). Maintenant :
// GET /watt/me/plays-history agrège la table play_events par jour. Les
// écoutes antérieures au déploiement n'ont pas d'événements : la courbe
// démarre à cette date (le TOTAL affiché reste complet via Track.plays).
const _playsHistoryCache = {};
async function fetchPlaysHistory(period) {
  const days = period === '7j' ? 7 : 30;   // '30j' et 'total' → 30 jours
  const key = String(days);
  if (_playsHistoryCache[key]) return _playsHistoryCache[key];
  try {
    if (typeof apiFetch === 'function') {
      const resp = await apiFetch('/watt/me/plays-history?days=' + days);
      const series = (resp && Array.isArray(resp.series)) ? resp.series : [];
      if (series.length) { _playsHistoryCache[key] = series; return series; }
    }
  } catch (_) { /* silencieux — courbe à zéro plutôt qu'une erreur */ }
  return new Array(days).fill(0);
}

// (Ancienne courbe simulée — conservée nulle part : remplacée par
// fetchPlaysHistory ci-dessus. Fonction laissée pour d'éventuels appels
// externes, mais elle n'est plus utilisée par renderChart.)
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
  // Vérifie que l'utilisateur est connecté (token JWT présent).
  // On bloque si getAuthToken n'est pas encore défini (api.js non chargé)
  // OU si le token est absent — évite l'accès au dashboard sans auth.
  if (typeof getAuthToken !== 'function' || !getAuthToken()) {
    const returnUrl = encodeURIComponent('/dashboard');
    window.location.href = `/?auth=login&return=${returnUrl}`;
    return false;
  }
  const guardEl = document.getElementById('dash-guard');
  if (guardEl) guardEl.style.display = 'none';
  return true;
}

// ── 5. RENDU ARTISTE ──────────────────────────────────────────────────────────

function renderArtistCard() {
  // Depuis la suppression du bloc #sec-artist, cette fonction ne fait plus
  // que :
  //   1. peupler l'avatar + nom dans la topbar (dashNavAvatar / dashNavName)
  //   2. déclencher le rendu de la liste "Mes sons"
  //   3. rafraîchir le dropdown profil du header
  // Toute l'UI d'identité artiste (avatar xl, nom, genre, bio, socials, KPIs
  // plays/tracks/followers/rank) vit désormais sur la page publique /u/<slug>.
  const user    = getCurrentUser();
  const profile = getWattProfile();

  // Topbar — on descend la cascade pour toujours afficher au moins UNE
  // initiale dès qu'on a quelque chose d'identifiable (artistName, name,
  // artist_name renvoyé par /users/me, ou local-part de l'email). Avant,
  // dès que profile existait sans artistName, on retombait sur '?' même si
  // on avait user.name en mémoire : bulle blanche après un refresh du
  // dashboard (bug #37 récurrent après refonte du profil).
  const navName =
        (profile && profile.artistName) ||
        (user && user.artist_name) ||
        (user && user.name) ||
        (user && String(user.email || '').split('@')[0]) ||
        'Artiste';
  const initials = (navName || '?').charAt(0).toUpperCase();

  const navAv = document.getElementById('dashNavAvatar');
  if (navAv) { navAv.textContent = initials; }
  const navNm = document.getElementById('dashNavName');
  if (navNm) { navNm.textContent = navName; }

  // Liste de mes sons
  renderMyTracks();

  // Bulle profil (dropdown topbar) — même source de vérité que le chip
  try { renderUserDropdown(); } catch (_) { /* noop */ }
}

/* Dérive le slug public d'un user depuis son artist_name (prioritaire) ou
   son email (fallback local-part). Miroir côté front de la fonction Python
   `_derive_artist_slug` du backend pour garantir qu'on tape la bonne URL
   /artiste/<slug> sans aller-retour serveur. */
function _deriveArtistSlug(user, profile) {
  const source =
    (profile && profile.artistName) ||
    (user && user.artist_name) ||
    (user && user.name) ||
    (user && String(user.email || '').split('@')[0]) ||
    '';
  return String(source)
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/* ── Bulle profil (dropdown topbar) ────────────────────────────────────────
   Remplit le popover qui s'ouvre au clic sur #dashUserChip. Deux états :
     • profil vierge (pas de nom OU pas de bio) → CTA "Créer mon profil"
       qui scroll vers #sec-profile.
     • profil rempli → liens "Voir mon profil public" (ouvre /artiste/<slug>
       dans un nouvel onglet) + "Éditer mon profil".
   On considère "complet" quand l'utilisateur a au minimum un artistName
   non vide ET une bio — le reste n'est pas bloquant pour l'affichage. */
function renderUserDropdown() {
  const user    = getCurrentUser();
  const profile = getWattProfile();

  // Même cascade que renderArtistCard pour rester cohérent avec le chip.
  const name =
        (profile && profile.artistName) ||
        (user && user.artist_name) ||
        (user && user.name) ||
        (user && String(user.email || '').split('@')[0]) ||
        'Artiste';
  const initials = (name || '?').charAt(0).toUpperCase();
  // Slug calé sur `_derive_artist_slug` côté backend (watt_compat.py) :
  // priorité à `artist_name` slugifié, fallback sur le local-part de l'email.
  const slug     = _deriveArtistSlug(user, profile);

  // En-tête du dropdown
  const dropAv = document.getElementById('dashDropAvatar');
  if (dropAv) {
    dropAv.textContent = '';
    const savedImg = safeStorage.getItem('smyle_watt_avatar');
    const avatarUrl = (profile && profile.avatarUrl) || savedImg || '';
    if (avatarUrl) {
      const img = document.createElement('img');
      img.src = avatarUrl;
      img.alt = name;
      img.addEventListener('error', () => { dropAv.textContent = initials; });
      dropAv.appendChild(img);
    } else {
      dropAv.textContent = initials;
    }
  }
  setTextById('dashDropName', name);
  setTextById('dashDropSlug', slug ? '@' + slug : '@artiste');

  // État vierge vs rempli (règle volontairement simple).
  const hasName = !!(profile && profile.artistName && String(profile.artistName).trim());
  const hasBio  = !!(profile && profile.bio        && String(profile.bio).trim());
  const isEmpty = !hasName || !hasBio;

  const emptyEl   = document.getElementById('dashDropEmpty');
  const actionsEl = document.getElementById('dashDropActions');
  const publicEl  = document.getElementById('dashDropPublic');

  if (emptyEl)   emptyEl.hidden   = !isEmpty;
  if (actionsEl) actionsEl.hidden =  isEmpty;

  // "Mon profil" — pointe TOUJOURS vers /u/<slug>. C'est la même
  // page pour la création (squelette éditable en mode owner), l'édition
  // in-place (profil brouillon ou publié), et la vue publique (fans).
  // Le slug est garanti depuis le signup (fallback email local-part).
  // URL neutre : le statut « artiste » s'obtient en postant un son, pas
  // en s'inscrivant.
  const href = slug ? '/@' + encodeURIComponent(slug) : '#';
  if (publicEl) {
    publicEl.href = href;
    if (!slug) {
      publicEl.setAttribute('aria-disabled', 'true');
      publicEl.style.opacity = '.45';
      publicEl.style.pointerEvents = 'none';
    } else {
      publicEl.removeAttribute('aria-disabled');
      publicEl.style.opacity = '';
      publicEl.style.pointerEvents = '';
    }
  }
  const createEl = document.getElementById('dashDropCreate');
  if (createEl) createEl.href = href;
}

/* Toggle / fermeture du dropdown profil. Handlers installés une seule fois
   au DOMContentLoaded. Click extérieur et touche Échap ferment le popover. */
function _initUserDropdown() {
  const chip = document.getElementById('dashUserChip');
  const drop = document.getElementById('dashUserDrop');
  if (!chip || !drop) return;

  const open  = () => { drop.hidden = false; chip.setAttribute('aria-expanded', 'true');  };
  const close = () => { drop.hidden = true;  chip.setAttribute('aria-expanded', 'false'); };

  chip.addEventListener('click', (e) => {
    e.stopPropagation();
    if (drop.hidden) { renderUserDropdown(); open(); } else { close(); }
  });

  document.addEventListener('click', (e) => {
    if (drop.hidden) return;
    if (!drop.contains(e.target) && !chip.contains(e.target)) close();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !drop.hidden) { close(); chip.focus(); }
  });

  drop.addEventListener('click', (e) => {
    const el = e.target.closest('a, button');
    if (!el) return;
    setTimeout(close, 0);
  });
}

// ── Gestion état section upload (compteur + teaser premium) ─────────────────
function renderUploadState() {
  const tracks  = getMyTracks();
  const count   = tracks.length;
  const limited = count >= FREE_LIMIT && !_isOfficialAccount();

  // Compteur freemium
  const counterVal = document.getElementById('dashFreeCounterVal');
  const barFill    = document.getElementById('dashFreeBarFill');
  if (counterVal) {
    counterVal.textContent = _isOfficialAccount()
      ? `${count} sons publiés`
      : limited
        ? 'Playlist complète ✓'
        : `${count} / ${FREE_LIMIT} sons utilisés`;
    counterVal.style.color = limited ? '#FFD700' : '';
  }
  if (barFill) {
    const pct = _isOfficialAccount() ? 0 : Math.min((count / FREE_LIMIT) * 100, 100);
    barFill.style.width = pct + '%';
    barFill.style.background = limited
      ? 'linear-gradient(90deg, #FFD700, #FFEC6B)'
      : 'linear-gradient(90deg, rgba(255,215,0,.7), rgba(255,215,0,.35))';
  }

  // Zone upload vs teaser
  const uploadLayout = document.getElementById('dashUploadLayout');
  const teaser       = document.getElementById('dashPremiumTeaser');
  if (uploadLayout) uploadLayout.style.display = limited ? 'none' : '';
  if (teaser)       teaser.style.display       = limited ? '' : 'none';
}

function renderMyTracks() {
  const tracks  = getMyTracks();
  const profile = getWattProfile();
  const listEl  = document.getElementById('myTracksList');
  const countEl = document.getElementById('myTracksCount');

  // Compteur "X / 6 sons" dans l'en-tête "Mes Sons"
  if (countEl) {
    const limited = tracks.length >= FREE_LIMIT && !_isOfficialAccount();
    countEl.textContent = _isOfficialAccount()
      ? `${tracks.length} son${tracks.length !== 1 ? 's' : ''}`
      : `${tracks.length}\u202f/\u202f${FREE_LIMIT} son${tracks.length !== 1 ? 's' : ''}`;
    countEl.style.color = limited ? '#FFD700' : '';
  }

  // Mise à jour du compteur upload
  renderUploadState();

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
    // Étape 2 — couleur résolue (track.color → profile.brandColor → or WATT).
    // On l'utilise comme bordure gauche fine : signal discret qui montre à
    // l'artiste l'effet de son choix dans la liste "Mes sons publiés".
    const color = resolveTrackColor(t, profile);
    return `
    <div class="dash-track-row" data-id="${t.id}" style="border-left:3px solid ${color}">
      <div class="dash-track-cover">${coverHTML}</div>
      <div class="dash-track-info">
        <div class="dash-track-name">${htmlEscape(t.name)}</div>
        <div class="dash-track-meta">${htmlEscape(t.genre || 'Sans genre')} · ${t.date || 'récent'}</div>
      </div>
      <div class="dash-track-plays">${t.plays || 0} écoutes</div>
      <div class="dash-track-row-actions">
        <button class="dash-track-edit-btn" title="Modifier ce son" onclick="openTrackEdit('${t.id}')">✏️</button>
        <button class="dash-btn-ghost" style="padding:4px 10px;font-size:.68rem" onclick="deleteTrack('${t.id}')">✕</button>
      </div>
    </div>`;
  }).join('');
}

// ── Édition inline d'un son ────────────────────────────────────────────────
// Panneau modal qui permet à tout artiste de modifier :
//   - le titre du son
//   - la cover (upload fichier → R2 via /watt/upload-image)
//   - la couleur signature
//   - la recette (prompt) liée
// Utilise PATCH /tracks/{dbId} (FastAPI) après avoir résolu les assets.
// Les mêmes fonctions seront accessibles à tous les artistes via leur
// dashboard — l'ID local (localStorage) sert de clé de lookup, le dbId
// est transmis au backend.

let _editTrackLocalId  = null;   // id localStorage en cours d'édition
let _editCoverFile     = null;   // fichier cover sélectionné (si nouveau)
let _editCoverPreview  = null;   // data URL preview

// ══════════════════════════════════════════════════════════════════════════════
// CELLULE ÉDITION CATALOGUE — Section 1b du WattBoard
// Branchée sur GET /tracks/me (API) → trouve TOUS les sons de la plateforme.
// Recherche inline par nom → formulaire d'édition cover/titre/couleur/mood/recette.
// ══════════════════════════════════════════════════════════════════════════════

let _dte2TrackId   = null;   // UUID DB du track en cours d'édition
let _dte2CoverFile = null;   // nouveau fichier cover sélectionné
let _dte2CoverPrev = null;   // data-url preview
let _dte2AllTracks = [];     // cache API — tous les sons de l'artiste

// Initialisation : charge depuis l'API les sons + les prompts
async function initTrackEditor() {
  // 1. Charge TOUS les tracks depuis l'API (source de vérité)
  try {
    const tracks = await apiFetch('/tracks/me');
    _dte2AllTracks = Array.isArray(tracks) ? tracks : [];
    // Synchronise le localStorage avec la réponse API pour cohérence multi-device.
    // Évite que "Mes Sons" (qui lit smyle_watt_tracks) affiche des données périmées.
    if (_dte2AllTracks.length > 0) {
      const localTracks = _dte2AllTracks.map(t => ({
        id:       t.id,
        dbId:     t.id,
        name:     t.title  || '',
        title:    t.title  || '',
        plays:    t.plays  || 0,
        color:    t.color  || '',
        coverUrl: t.cover_url || '',
        promptId: t.prompt_id || null,
        tags:     t.tags   || null,
      }));
      saveMyTracks(localTracks);
    }
  } catch (_) {
    // Fallback localStorage si API indisponible
    _dte2AllTracks = getMyTracks().map(t => ({
      id:        t.dbId || t.id,
      title:     t.name || t.title || '',
      color:     t.color || null,
      cover_url: t.coverUrl || null,
      prompt_id: t.promptId || null,
      plays:     t.plays || 0,
    }));
  }

  // 2. Charge les prompts pour le dropdown recette
  try {
    const resp = await apiFetch('/artist/me/prompts');
    const prompts = (resp && Array.isArray(resp.items)) ? resp.items
                  : (Array.isArray(resp) ? resp : []);
    const sel = document.getElementById('dte2Prompt');
    if (sel && prompts.length > 0) {
      prompts.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.title} · ${p.price_credits} Smyles`;
        sel.appendChild(opt);
      });
    }
  } catch (_) {}
}

// Filtre en temps réel — cherche dans _dte2AllTracks (source API)
function dte2Filter(q) {
  const res = document.getElementById('dte2Results');
  if (!res) return;
  const term = (q || '').trim().toLowerCase();
  if (!term) { res.style.display = 'none'; res.innerHTML = ''; return; }

  const hits = _dte2AllTracks
    .filter(t => (t.title || '').toLowerCase().includes(term))
    .slice(0, 8);

  if (hits.length === 0) {
    res.innerHTML = '<li class="dte2-result-empty">Aucun son trouvé</li>';
    res.style.display = 'block';
    return;
  }
  res.innerHTML = hits.map(t => {
    const col   = t.color || '#FFD700';
    const cover = t.cover_url
      ? `<img src="${t.cover_url.replace(/"/g,'&quot;')}" class="dte2-result-cover" alt="">`
      : `<div class="dte2-result-cover" style="background:${col}"></div>`;
    return `<li class="dte2-result-item" data-id="${t.id}" onclick="dte2Select('${t.id}')">
      ${cover}
      <span class="dte2-result-name" style="color:${col}">${htmlEscape(t.title || 'Sans titre')}</span>
      <span class="dte2-result-meta">${t.plays || 0} écoutes</span>
    </li>`;
  }).join('');
  res.style.display = 'block';
}

// Sélection d'un son → remplit le formulaire (données API)
function dte2Select(trackUuid) {
  const t = _dte2AllTracks.find(x => x.id === trackUuid);
  if (!t) return;

  _dte2TrackId   = trackUuid;
  _dte2CoverFile = null;
  _dte2CoverPrev = t.cover_url || null;

  // Ferme la liste
  const res = document.getElementById('dte2Results');
  const inp = document.getElementById('dte2SearchInput');
  if (res) res.style.display = 'none';
  if (inp) inp.value = t.title || '';

  // Cover preview
  const coverEl = document.getElementById('dte2Cover');
  if (coverEl) {
    coverEl.innerHTML = t.cover_url
      ? `<img src="${t.cover_url.replace(/"/g,'&quot;')}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:10px">`
      : `<div style="width:100%;height:100%;background:${t.color||'#FFD700'};border-radius:10px;opacity:.7"></div>`;
  }

  // Infos
  const lbl   = document.getElementById('dte2SelectedLabel');
  const plays = document.getElementById('dte2SelectedPlays');
  if (lbl)   lbl.textContent   = t.title || 'Sans titre';
  if (plays) plays.textContent = `${t.plays || 0} écoutes`;

  // Titre
  const titleInp = document.getElementById('dte2Title');
  if (titleInp) titleInp.value = t.title || '';

  // Beat (fix dissonance Instrumental/Beat 2026-06-13) — état actuel du flag
  const beatChk = document.getElementById('dte2BeatFlag');
  const bpmInp  = document.getElementById('dte2Bpm');
  const bpmWrap = document.getElementById('dte2BpmWrap');
  if (beatChk) beatChk.checked = !!t.is_beat;
  if (bpmInp)  bpmInp.value = (t.bpm != null) ? t.bpm : '';
  if (bpmWrap) bpmWrap.hidden = !t.is_beat;

  // Tags : pré-rempli depuis t.tags (migration 0038)
  const tagsInp = document.getElementById('dte2Tags');
  if (tagsInp) tagsInp.value = t.tags || '';
  // Synchronise les chips avec les tags existants
  _dte2SyncChips(t.tags || '');

  // Couleur
  const col    = t.color || '';
  const picker = document.getElementById('dte2ColorPicker');
  const colVal = document.getElementById('dte2ColorVal');
  if (picker) picker.value = col || '#FFD700';
  if (colVal) colVal.value = col;
  _dte2RefreshSwatches(col);
  _dte2RefreshColorPreview(col);

  // Recette liée
  const promptSel = document.getElementById('dte2Prompt');
  if (promptSel) promptSel.value = t.prompt_id || '';

  // Reset erreur
  const err = document.getElementById('dte2Err');
  if (err) { err.style.display = 'none'; err.textContent = ''; }

  document.getElementById('dte2Form').style.display = 'block';
}

// Cover
function dte2OnCoverChange(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { dashToast('Image trop lourde (max 5 MB)'); return; }
  _dte2CoverFile = file;
  const reader = new FileReader();
  reader.onload = e => {
    _dte2CoverPrev = e.target.result;
    const coverEl = document.getElementById('dte2Cover');
    if (coverEl) coverEl.innerHTML = `<img src="${e.target.result}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:10px">`;
  };
  reader.readAsDataURL(file);
}

// Couleur
function dte2PickColor(hex, btn) {
  const colVal = document.getElementById('dte2ColorVal');
  const picker = document.getElementById('dte2ColorPicker');
  if (colVal) colVal.value = hex;
  if (picker) picker.value = hex;
  _dte2RefreshSwatches(hex);
  _dte2RefreshColorPreview(hex);
}
function dte2OnColorPicker(hex) {
  const colVal = document.getElementById('dte2ColorVal');
  if (colVal) colVal.value = hex;
  _dte2RefreshSwatches('');
  _dte2RefreshColorPreview(hex);
}
function _dte2RefreshSwatches(active) {
  document.querySelectorAll('.dte2-swatch').forEach(s => {
    s.classList.toggle('is-active', active && s.dataset.hex && s.dataset.hex.toLowerCase() === active.toLowerCase());
  });
}
function _dte2RefreshColorPreview(hex) {
  const prev = document.getElementById('dte2ColorPreview');
  if (!prev || !hex) return;
  prev.style.cssText = `background:${hex};box-shadow:0 0 12px ${hex}66;`;
  prev.textContent = hex.toUpperCase();
}

// Annuler
function dte2Cancel() {
  _dte2TrackId = null; _dte2CoverFile = null; _dte2CoverPrev = null;
  const form = document.getElementById('dte2Form');
  const inp  = document.getElementById('dte2SearchInput');
  if (form) form.style.display = 'none';
  if (inp)  inp.value = '';
}

// ── Chips mood — edit form ────────────────────────────────────────────────
function dte2ToggleChip(btn) {
  btn.classList.toggle('is-active');
  _dte2UpdateTagsFromChips();
}
function _dte2UpdateTagsFromChips() {
  const active = [...document.querySelectorAll('#dte2MoodChips .dte2-chip.is-active')]
    .map(c => c.dataset.tag);
  const inp = document.getElementById('dte2Tags');
  if (!inp) return;
  // Fusion chips activées + tags libres déjà tapés (sans doublon)
  const typed = inp.value.split(',').map(s => s.trim()).filter(Boolean);
  const merged = [...new Set([...active, ...typed.filter(t => !active.some(a => a === t))])];
  inp.value = merged.join(', ');
}
function _dte2SyncChips(tagsStr) {
  const tags = tagsStr.split(',').map(s => s.trim().toLowerCase());
  document.querySelectorAll('#dte2MoodChips .dte2-chip').forEach(c => {
    c.classList.toggle('is-active', tags.includes(c.dataset.tag));
  });
}

// ── Chips mood — création (alimente dashTags) ─────────────────────────────
function dashToggleChip(btn) {
  btn.classList.toggle('is-active');
  const active = [...document.querySelectorAll('#dashMoodChips .dte2-chip.is-active')]
    .map(c => c.dataset.tag);
  const inp = document.getElementById('dashTags');
  if (!inp) return;
  // Fusionne les chips activées avec les tags libres déjà tapés (sans doublon)
  const typed = inp.value.split(',').map(s => s.trim()).filter(Boolean);
  const merged = [...new Set([...active, ...typed.filter(t => !active.some(a => a === t))])];
  inp.value = merged.join(', ');
}

// Enregistrer — PATCH direct via UUID API (source de vérité)
async function dte2Save() {
  if (!_dte2TrackId) return;
  const t = _dte2AllTracks.find(x => x.id === _dte2TrackId);
  if (!t) return;

  const saveBtn = document.getElementById('dte2SaveBtn');
  const errEl   = document.getElementById('dte2Err');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Enregistrement…'; }
  if (errEl)   { errEl.style.display = 'none'; }

  try {
    const newTitle  = (document.getElementById('dte2Title')?.value || '').trim();
    const newColor  = document.getElementById('dte2ColorVal')?.value
                   || document.getElementById('dte2ColorPicker')?.value || '';
    const newPrompt = document.getElementById('dte2Prompt')?.value || '';
    const newTags   = (document.getElementById('dte2Tags')?.value || '').trim();
    // Beat rétroactif (fix dissonance Instrumental/Beat)
    const newIsBeat = !!document.getElementById('dte2BeatFlag')?.checked;
    const _bpmRaw   = (document.getElementById('dte2Bpm')?.value || '').trim();
    let newBpm = null;
    if (newIsBeat && _bpmRaw !== '') {
      const n = parseInt(_bpmRaw, 10);
      if (Number.isInteger(n) && n >= 40 && n <= 300) newBpm = n;
      else throw new Error('BPM invalide : entre 40 et 300, ou vide.');
    }

    // Upload cover si nouveau fichier sélectionné
    let newCoverUrl = t.cover_url || null;
    if (_dte2CoverFile) {
      const uploaded = await _uploadTrackCover(_dte2CoverFile, newTitle || t.title);
      if (uploaded) newCoverUrl = uploaded;
    }

    // PATCH /tracks/{uuid} — champs modifiés uniquement
    const patch = {};
    if (newTitle && newTitle !== t.title)            patch.title     = newTitle;
    if (newColor && newColor !== (t.color || ''))    patch.color     = newColor;
    if (newCoverUrl && newCoverUrl !== t.cover_url)  patch.cover_url = newCoverUrl;
    if (newPrompt && newPrompt !== (t.prompt_id||'')) patch.prompt_id = newPrompt;
    else if (!newPrompt && t.prompt_id)               patch.prompt_id = null;
    if (newTags !== (t.tags || ''))                   patch.tags      = newTags || null;
    if (newIsBeat !== !!t.is_beat)                    patch.is_beat   = newIsBeat;
    if ((newIsBeat ? newBpm : null) !== (t.bpm != null ? t.bpm : null)) patch.bpm = newIsBeat ? newBpm : null;

    if (Object.keys(patch).length > 0) {
      const updated = await apiFetch(`/tracks/${encodeURIComponent(_dte2TrackId)}`, {
        method: 'PATCH', json: patch,
      });
      // Met à jour le cache local
      const idx = _dte2AllTracks.findIndex(x => x.id === _dte2TrackId);
      if (idx !== -1) _dte2AllTracks[idx] = { ..._dte2AllTracks[idx], ...patch, cover_url: newCoverUrl };
    }

    // Sync localStorage si track présente (pour cohérence affichage)
    const lsTracks = getMyTracks();
    const lsIdx = lsTracks.findIndex(x => x.dbId === _dte2TrackId);
    if (lsIdx !== -1) {
      lsTracks[lsIdx] = {
        ...lsTracks[lsIdx],
        name:         newTitle || lsTracks[lsIdx].name,
        color:        newColor || lsTracks[lsIdx].color,
        coverUrl:     newCoverUrl || lsTracks[lsIdx].coverUrl,
        promptId:     newPrompt || lsTracks[lsIdx].promptId || null,
      };
      saveMyTracks(lsTracks);
      renderMyTracks();
    }

    dashToast('✓ Son mis à jour');
    dte2Cancel();
  } catch (err) {
    const msg = (err && err.message) || 'Erreur inconnue';
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Enregistrer les modifications'; }
  }
}

// ── Création de prompt depuis "Modifier un son" ───────────────────────────────
// Ouvre une modale avec tous les champs requis par POST /artist/me/prompts.
// À la validation : crée le prompt, lie au track sélectionné via PATCH, rafraîchit le dropdown.
function dte2OpenCreatePrompt() {
  if (!_dte2TrackId) {
    dashToast('Sélectionne d\'abord un son à modifier');
    return;
  }

  // Empêche double-ouverture
  if (document.getElementById('dte2CreatePromptOverlay')) return;

  const overlay = document.createElement('div');
  overlay.id = 'dte2CreatePromptOverlay';
  overlay.style.cssText = `
    position:fixed;inset:0;z-index:9000;display:flex;align-items:center;justify-content:center;
    background:rgba(0,0,0,.75);backdrop-filter:blur(6px);
    animation:fadeIn .2s ease;
  `;
  overlay.innerHTML = `
    <div id="dte2CreatePromptPanel" style="
      background:#12101a;border:1px solid rgba(136,0,255,.35);border-radius:18px;
      box-shadow:0 0 48px rgba(136,0,255,.18),0 8px 40px rgba(0,0,0,.6);
      width:min(600px,94vw);max-height:90vh;overflow-y:auto;padding:32px 28px;
      display:flex;flex-direction:column;gap:18px;
    ">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <h3 style="color:#e8e0ff;font-size:1.15rem;font-weight:700;margin:0">✨ Créer une recette à vendre</h3>
        <button onclick="dte2CloseCreatePrompt()" style="
          background:none;border:none;color:#8a85a0;font-size:1.3rem;cursor:pointer;line-height:1;padding:4px
        ">✕</button>
      </div>

      <!-- Titre -->
      <div class="dte2-cp-field">
        <label class="dte2-cp-label">Titre de la recette <span style="color:#cc44ff">*</span></label>
        <input id="cp_title" class="dte2-input" type="text" maxlength="120"
               placeholder="Ex : Deep Dancehall Sombre" style="width:100%;box-sizing:border-box">
      </div>

      <!-- Texte du prompt -->
      <div class="dte2-cp-field">
        <label class="dte2-cp-label">Texte du prompt <span style="color:#cc44ff">*</span> <span id="cp_charCount" style="color:#6b6780;font-size:.8rem">(0/1000)</span></label>
        <textarea id="cp_text" class="dte2-input" rows="6"
                  placeholder="Décris ici la recette musicale complète : style, énergie, instruments, ambiance… (100 caractères minimum)"
                  oninput="document.getElementById('cp_charCount').textContent='('+this.value.length+'/1000)'"
                  style="width:100%;box-sizing:border-box;resize:vertical;min-height:120px"></textarea>
      </div>

      <!-- Plateforme + Prix -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div class="dte2-cp-field">
          <label class="dte2-cp-label">Plateforme <span style="color:#cc44ff">*</span></label>
          <select id="cp_platform" class="dte2-input" style="width:100%">
            <option value="">— Choisir —</option>
            <option value="suno">Suno</option>
            <option value="udio">Udio</option>
            <option value="riffusion">Riffusion</option>
            <option value="stable_audio">Stable Audio</option>
            <option value="autre">Autre</option>
          </select>
        </div>
        <div class="dte2-cp-field">
          <label class="dte2-cp-label">Prix (Smyles) <span style="color:#cc44ff">*</span></label>
          <input id="cp_price" class="dte2-input" type="number" min="3" max="500" value="30"
                 style="width:100%;box-sizing:border-box">
        </div>
      </div>

      <!-- Weirdness + Style influence (sliders 0-100) -->
      <div class="dte2-cp-field">
        <label class="dte2-cp-label">
          Weirdness — variété sonore
          <span id="cp_weirdVal" style="color:#cc44ff;font-weight:700;margin-left:8px">50</span>/100
        </label>
        <input id="cp_weird" type="range" min="0" max="100" value="50"
               oninput="document.getElementById('cp_weirdVal').textContent=this.value"
               style="width:100%;accent-color:#8800ff;margin-top:6px">
        <span style="display:flex;justify-content:space-between;font-size:.7rem;color:#6b6780;margin-top:2px">
          <span>0 — classique</span><span>100 — expérimental</span>
        </span>
      </div>

      <div class="dte2-cp-field">
        <label class="dte2-cp-label">
          Style influence — fidélité à la référence
          <span id="cp_styleVal" style="color:#cc44ff;font-weight:700;margin-left:8px">50</span>/100
        </label>
        <input id="cp_style" type="range" min="0" max="100" value="50"
               oninput="document.getElementById('cp_styleVal').textContent=this.value"
               style="width:100%;accent-color:#8800ff;margin-top:6px">
        <span style="display:flex;justify-content:space-between;font-size:.7rem;color:#6b6780;margin-top:2px">
          <span>0 — très libre</span><span>100 — très fidèle</span>
        </span>
      </div>

      <!-- Vocal gender -->
      <div class="dte2-cp-field">
        <label class="dte2-cp-label">Genre vocal <span style="color:#cc44ff">*</span></label>
        <select id="cp_vocal" class="dte2-input" style="width:100%">
          <option value="">— Choisir —</option>
          <option value="masculin">Masculin</option>
          <option value="feminin">Féminin</option>
          <option value="neutre">Neutre</option>
          <option value="mixte">Mixte</option>
          <option value="instrumental">Instrumental</option>
        </select>
      </div>

      <!-- Erreur -->
      <div id="cp_err" style="display:none;color:#ff6b6b;font-size:.85rem;background:rgba(255,80,80,.08);
           border:1px solid rgba(255,80,80,.2);border-radius:8px;padding:8px 12px"></div>

      <!-- Footer -->
      <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:4px">
        <button class="dash-btn-ghost" onclick="dte2CloseCreatePrompt()">Annuler</button>
        <button class="dash-btn-primary" id="cp_saveBtn" onclick="dte2SubmitCreatePrompt()">
          Créer et lier au son
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
}

function dte2CloseCreatePrompt() {
  const el = document.getElementById('dte2CreatePromptOverlay');
  if (el) el.remove();
}

async function dte2SubmitCreatePrompt() {
  const titleEl   = document.getElementById('cp_title');
  const textEl    = document.getElementById('cp_text');
  const platEl    = document.getElementById('cp_platform');
  const priceEl   = document.getElementById('cp_price');
  const weirdEl   = document.getElementById('cp_weird');
  const vocalEl   = document.getElementById('cp_vocal');
  const styleEl   = document.getElementById('cp_style');
  const errEl     = document.getElementById('cp_err');
  const saveBtn   = document.getElementById('cp_saveBtn');

  const title    = (titleEl?.value || '').trim();
  const text     = (textEl?.value || '').trim();
  const platform = platEl?.value || '';
  const price    = parseInt(priceEl?.value || '30', 10);
  const weird    = parseInt(weirdEl?.value || '50', 10);
  const vocal    = vocalEl?.value || '';
  const style    = parseInt(styleEl?.value || '50', 10);

  const showErr = (msg) => {
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
  };

  // Validations
  if (title.length < 5)   { showErr('Le titre doit faire au moins 5 caractères.'); return; }
  if (text.length < 100)  { showErr(`Le texte du prompt doit faire au moins 100 caractères (${text.length}/100).`); return; }
  if (text.length > 1000) { showErr('Le texte du prompt ne doit pas dépasser 1000 caractères.'); return; }
  if (!platform)           { showErr('Choisis une plateforme.'); return; }
  if (price < 3 || price > 500 || isNaN(price)) { showErr('Le prix doit être entre 3 et 500 Smyles.'); return; }
  if (!vocal)              { showErr('Choisis un genre vocal.'); return; }

  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Création en cours…'; }
  if (errEl)   { errEl.style.display = 'none'; }

  try {
    // 1. Créer le prompt
    const newPrompt = await apiFetch('/artist/me/prompts', {
      method: 'POST',
      json: {
        title,
        prompt_text:          text,
        price_credits:        price,
        prompt_platform:      platform,
        prompt_weirdness:     String(weird),
        prompt_style_influence: String(style),
        prompt_vocal_gender:  vocal,
        is_published:         true,
      },
    });

    const promptId = newPrompt.id || newPrompt.prompt_id;
    if (!promptId) throw new Error('Réponse API inattendue (pas d\'ID)');

    // 2. Lier au track sélectionné
    await apiFetch(`/tracks/${encodeURIComponent(_dte2TrackId)}`, {
      method: 'PATCH',
      json: { prompt_id: promptId },
    });

    // 3. Mettre à jour le cache track
    const idx = _dte2AllTracks.findIndex(x => x.id === _dte2TrackId);
    if (idx !== -1) _dte2AllTracks[idx] = { ..._dte2AllTracks[idx], prompt_id: promptId };

    // 4. Ajouter au dropdown + sélectionner
    const sel = document.getElementById('dte2Prompt');
    if (sel) {
      const opt = document.createElement('option');
      opt.value = promptId;
      opt.textContent = `${title} · ${price} Smyles`;
      sel.appendChild(opt);
      sel.value = promptId;
    }

    // 5. Fermer le modal + toast
    dte2CloseCreatePrompt();
    dashToast('✨ Recette créée et liée au son !');

  } catch (err) {
    const msg = (typeof _humanizeApiError === 'function')
      ? _humanizeApiError(err)
      : ((err && err.message) || 'Erreur inconnue');
    showErr(msg);
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Créer et lier au son'; }
  }
}

async function openTrackEdit(localId) {
  const tracks = getMyTracks();
  const t = tracks.find(x => x.id === localId);
  if (!t) return;
  _editTrackLocalId = localId;
  _editCoverFile    = null;
  _editCoverPreview = t.coverDataUrl || null;

  // ── Source de vérité : hydrate depuis l'API avant d'afficher le form ──────
  // Fix persistance tags à l'édition (2026-06-09). Le localStorage est un
  // cache peu fiable (clé d'ID incohérente, champ tags absent sur les sons
  // antérieurs à la migration 0038, autre appareil, cache vidé). On pré-remplit
  // donc tags/titre/couleur/recette depuis /tracks/me (TrackRead), qui est la
  // source de vérité. Sans ça, le champ tags s'affiche vide alors que la base
  // les contient → aucun PATCH envoyé à la sauvegarde → "tags perdus".
  if (t.dbId) {
    let apiTracks = (Array.isArray(_dte2AllTracks) && _dte2AllTracks.length) ? _dte2AllTracks : null;
    if (!apiTracks) {
      try {
        const r = await apiFetch('/tracks/me');
        apiTracks = Array.isArray(r) ? r : [];
      } catch (_) { apiTracks = []; }
    }
    const apiT = apiTracks.find(x => x && x.id === t.dbId);
    if (apiT) {
      t.name     = apiT.title      ?? t.name;
      t.color    = apiT.color      ?? t.color;
      t.tags     = apiT.tags       ?? t.tags;
      t.promptId = apiT.prompt_id  ?? t.promptId;
    }
  }

  // Récupère les prompts de l'artiste pour le dropdown
  let myPrompts = [];
  try {
    const resp = await apiFetch('/artist/me/prompts');
    myPrompts = (resp && Array.isArray(resp.items)) ? resp.items
              : (Array.isArray(resp) ? resp : []);
  } catch (_) {}

  const coverSrc = _editCoverPreview || '';
  const promptOptions = [
    `<option value="">— Aucune recette liée —</option>`,
    ...myPrompts.map(p =>
      `<option value="${p.id}"${t.promptId === p.id ? ' selected' : ''}>${htmlEscape(p.title)} (${p.price_credits} crédits)</option>`
    ),
  ].join('');

  const overlay = document.createElement('div');
  overlay.id = 'dashTrackEditOverlay';
  overlay.innerHTML = `
    <div class="dte-backdrop" onclick="closeTrackEdit()"></div>
    <div class="dte-panel" role="dialog" aria-modal="true">
      <div class="dte-hdr">
        <span class="dte-hdr-title">Modifier le son</span>
        <button class="dte-close" onclick="closeTrackEdit()" aria-label="Fermer">✕</button>
      </div>
      <div class="dte-body">

        <!-- Cover -->
        <div class="dte-field">
          <label class="dte-label">Cover</label>
          <div class="dte-cover-area">
            <div class="dte-cover-preview" id="dteCoverPreview">
              ${coverSrc
                ? `<img src="${coverSrc}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:8px">`
                : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="32" height="32" style="opacity:.3"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`}
            </div>
            <label class="dte-cover-pick-btn">
              📷 Choisir une image
              <input type="file" accept="image/*" id="dteCoverFile" style="display:none" onchange="onEditCoverChange(event)">
            </label>
            <span class="dte-cover-hint">JPG / PNG / WEBP · max 5 MB</span>
          </div>
        </div>

        <!-- Titre -->
        <div class="dte-field">
          <label class="dte-label" for="dteTitle">Titre</label>
          <input class="dte-input" id="dteTitle" type="text" maxlength="255"
                 value="${htmlEscape(t.name || '')}" placeholder="Nom du son">
        </div>

        <!-- Couleur -->
        <div class="dte-field">
          <label class="dte-label">Couleur signature</label>
          <div class="dte-color-row">
            ${['#FFD700','#cc88ff','#00e5ff','#ff6b6b','#00ffaa','#ff9f43'].map(c =>
              `<button class="dte-color-swatch${(t.color||'').toUpperCase()===c.toUpperCase()?' is-selected':''}"
                       style="background:${c}" data-hex="${c}"
                       onclick="selectEditColor('${c}',this)"></button>`
            ).join('')}
            <input type="color" id="dteColorPicker"
                   value="${t.color || '#FFD700'}"
                   oninput="onEditColorPicker(this.value)"
                   title="Couleur personnalisée">
          </div>
          <input type="hidden" id="dteColorVal" value="${t.color || ''}">
        </div>

        <!-- Tags / Mood -->
        <div class="dte-field">
          <label class="dte-label" for="dteTags">Mood &amp; Tags</label>
          <input class="dte-input" id="dteTags" type="text" maxlength="500"
                 value="${htmlEscape(t.tags || '')}"
                 placeholder="ex: chill, dark, instrumental, vocal">
          <span class="dte-hint">Mots-clés séparés par des virgules — améliorent la recherche.</span>
        </div>

        <!-- Recette liée -->
        <div class="dte-field">
          <label class="dte-label" for="dtePrompt">Recette (ADN) liée</label>
          <select class="dte-select" id="dtePrompt">${promptOptions}</select>
          <span class="dte-hint">Lier une recette rend ce son achetable sur la marketplace.</span>
        </div>

        <!-- C4 — Œuvre complète (lier ce son à une image, rétroactif) -->
        <div class="dte-field" id="dteOeuvreField">
          <label class="dte-label">Œuvre complète</label>
          <div id="dteOeuvreBox"></div>
        </div>

      </div>
      <div class="dte-footer">
        <button class="dash-btn-ghost" onclick="closeTrackEdit()">Annuler</button>
        <button class="dash-btn-primary" id="dteSaveBtn" onclick="_saveTrackEdit()">Enregistrer</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add('is-visible'));

  // C4 « Œuvre complète » — hydrate le bloc lien/délien pour le SON.
  // Pivot = le prompt-recette lié à ce son (t.promptId). Sans recette liée,
  // le son n'est pas un produit vendable → rien à lier.
  renderOeuvreCompleteSon(t);
}

// ── C4 « Œuvre complète » (lien rétroactif son <-> image) ──────────────────
// Rend, dans le drawer d'édition d'un SON, soit l'état « lié » (+ délier),
// soit un bouton « Lier à une image » qui ouvre le sélecteur de candidats.
// Le pivot côté son est le prompt-recette (t.promptId) : c'est lui qui porte
// linked_prompt_id. Sans recette liée, on invite l'artiste à en lier une.
async function renderOeuvreCompleteSon(t) {
  const box = document.getElementById('dteOeuvreBox');
  if (!box) return;
  const promptId = t && t.promptId;
  if (!promptId) {
    box.innerHTML =
      `<span class="dte-hint">Lie d'abord une recette (ADN) à ce son pour pouvoir le réunir avec une image en « Œuvre complète ».</span>`;
    return;
  }
  box.innerHTML = `<span class="dte-hint">Chargement…</span>`;
  // On lit l'état de lien du prompt via /artist/me/prompts (linked_prompt_id).
  let linkedPartner = null;
  try {
    const resp = await apiFetch('/artist/me/prompts');
    const items = (resp && Array.isArray(resp.items)) ? resp.items
                : (Array.isArray(resp) ? resp : []);
    const mine = items.find(p => p && p.id === promptId);
    if (mine && (mine.linked_prompt_id || mine.linkedPromptId)) {
      linkedPartner = mine.linked_prompt_id || mine.linkedPromptId;
    }
  } catch (_) {}
  if (linkedPartner) {
    renderOeuvreLinkedState(box, promptId, () => renderOeuvreCompleteSon(t));
  } else {
    renderOeuvreUnlinkedState(box, promptId, 'image', () => renderOeuvreCompleteSon(t));
  }
}

// État « lié » : affiche le partenaire + bouton Délier. On récupère un aperçu
// du partenaire via /linkable n'est pas adapté (il liste les libres), donc on
// affiche un libellé générique + le bouton Délier (DELETE idempotent).
function renderOeuvreLinkedState(box, promptId, onRefresh) {
  box.innerHTML =
    `<div class="dte-oeuvre-linked">` +
      `<span class="dte-oeuvre-linked-label">🔗 Réuni en œuvre complète</span>` +
      `<button type="button" class="dash-btn-ghost dte-oeuvre-unlink-btn">Délier</button>` +
    `</div>` +
    `<span class="dte-hint">Les deux produits restent vendables séparément.</span>`;
  const btn = box.querySelector('.dte-oeuvre-unlink-btn');
  if (btn) {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await apiFetch(`/artist/me/prompts/${encodeURIComponent(promptId)}/link`,
          { method: 'DELETE', raw: true });
        dashToast('Œuvre déliée ✓');
        if (typeof onRefresh === 'function') onRefresh();
      } catch (err) {
        btn.disabled = false;
        dashToast('Erreur : ' + (err && err.message || 'déliaison impossible'));
      }
    });
  }
}

// État « non lié » : bouton « Lier à une <image|son> » → charge les candidats
// (/linkable) et propose un sélecteur. Au choix → POST link bundle_exclusive=false.
function renderOeuvreUnlinkedState(box, promptId, kindLabel, onRefresh) {
  const label = kindLabel === 'image' ? 'une image' : 'un son';
  box.innerHTML =
    `<button type="button" class="dash-btn-ghost dte-oeuvre-link-btn">🔗 Lier à ${label}</button>` +
    `<span class="dte-hint">Réunis ce produit avec ${label} en « Œuvre complète » (les deux restent vendables séparément).</span>` +
    `<div class="dte-oeuvre-candidates" style="display:none"></div>`;
  const btn = box.querySelector('.dte-oeuvre-link-btn');
  const list = box.querySelector('.dte-oeuvre-candidates');
  if (!btn || !list) return;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    list.style.display = 'block';
    list.innerHTML = `<span class="dte-hint">Chargement des candidats…</span>`;
    let candidates = [];
    try {
      candidates = await apiFetch(
        `/artist/me/prompts/${encodeURIComponent(promptId)}/linkable`);
      candidates = Array.isArray(candidates) ? candidates : [];
    } catch (err) {
      list.innerHTML = `<span class="dte-hint">Erreur de chargement : ${htmlEscape(err && err.message || '')}</span>`;
      btn.disabled = false;
      return;
    }
    if (candidates.length === 0) {
      const empty = kindLabel === 'image'
        ? `Aucune image disponible à lier — crée-en une d'abord.`
        : `Aucun son disponible à lier — crée-en un d'abord.`;
      list.innerHTML = `<span class="dte-hint">${empty}</span>`;
      btn.disabled = false;
      return;
    }
    list.innerHTML = candidates.map(c => {
      const thumb = c.coverUrl
        ? `<img src="${htmlEscape(c.coverUrl)}" alt="" class="dte-oeuvre-thumb">`
        : (c.previewKey
            ? `<img src="/watt/images/${String(c.previewKey).split('/').map(encodeURIComponent).join('/')}" alt="" class="dte-oeuvre-thumb">`
            : `<span class="dte-oeuvre-thumb dte-oeuvre-thumb-ph">${kindLabel === 'image' ? '🖼️' : '🎵'}</span>`);
      return `<button type="button" class="dte-oeuvre-cand" data-cand-id="${htmlEscape(c.id)}">` +
        thumb +
        `<span class="dte-oeuvre-cand-title">${htmlEscape(c.title || 'Sans titre')}</span>` +
        `<span class="dte-oeuvre-cand-price">${htmlEscape(String(c.priceCredits))} Smyles</span>` +
      `</button>`;
    }).join('');
    list.querySelectorAll('.dte-oeuvre-cand').forEach(cb => {
      cb.addEventListener('click', async () => {
        const otherId = cb.getAttribute('data-cand-id');
        list.querySelectorAll('.dte-oeuvre-cand').forEach(x => x.disabled = true);
        try {
          // bundle_exclusive=false EN DUR : lien rétroactif → les deux produits
          // restent visibles individuellement (ils avaient une vie publique).
          await apiFetch(`/artist/me/prompts/${encodeURIComponent(promptId)}/link`, {
            method: 'POST',
            json: { other_prompt_id: otherId, bundle_exclusive: false },
            raw: true,
          });
          dashToast('Œuvre complète créée ✓');
          if (typeof onRefresh === 'function') onRefresh();
        } catch (err) {
          const st = err && err.status;
          const msg = st === 409
            ? 'Lien impossible (déjà lié ou natures incompatibles).'
            : ('Erreur : ' + (err && err.message || 'lien impossible'));
          dashToast(msg);
          list.querySelectorAll('.dte-oeuvre-cand').forEach(x => x.disabled = false);
        }
      });
    });
    btn.disabled = false;
  });
}

function closeTrackEdit() {
  const el = document.getElementById('dashTrackEditOverlay');
  if (!el) return;
  el.classList.remove('is-visible');
  setTimeout(() => el.remove(), 280);
  _editTrackLocalId = null;
  _editCoverFile    = null;
  _editCoverPreview = null;
}

function onEditCoverChange(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { dashToast('Image trop lourde (max 5 MB)'); return; }
  _editCoverFile = file;
  const reader = new FileReader();
  reader.onload = e => {
    _editCoverPreview = e.target.result;
    const prev = document.getElementById('dteCoverPreview');
    if (prev) prev.innerHTML = `<img src="${e.target.result}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:8px">`;
  };
  reader.readAsDataURL(file);
}

function selectEditColor(hex, btn) {
  document.getElementById('dteColorVal').value = hex;
  document.getElementById('dteColorPicker').value = hex;
  document.querySelectorAll('.dte-color-swatch').forEach(s => s.classList.remove('is-selected'));
  btn.classList.add('is-selected');
}

function onEditColorPicker(hex) {
  document.getElementById('dteColorVal').value = hex;
  document.querySelectorAll('.dte-color-swatch').forEach(s => s.classList.remove('is-selected'));
}

async function _saveTrackEdit() {
  if (!_editTrackLocalId) return;
  const tracks = getMyTracks();
  const t = tracks.find(x => x.id === _editTrackLocalId);
  if (!t) return;

  const saveBtn = document.getElementById('dteSaveBtn');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Enregistrement…'; }

  try {
    const newTitle  = (document.getElementById('dteTitle')?.value || '').trim();
    const newColor  = document.getElementById('dteColorVal')?.value || '';
    const newPrompt = document.getElementById('dtePrompt')?.value || '';
    const newTags   = (document.getElementById('dteTags')?.value || '').trim();

    // 1. Upload cover si nouveau fichier
    let newCoverUrl = t.coverUrl || null;
    if (_editCoverFile) {
      const uploaded = await _uploadTrackCover(_editCoverFile, newTitle || t.name);
      if (uploaded) newCoverUrl = uploaded;
    }

    // 2. PATCH FastAPI si dbId disponible
    if (t.dbId) {
      const patch = {};
      if (newTitle && newTitle !== t.name)          patch.title      = newTitle;
      if (newColor)                                  patch.color      = newColor;
      if (newCoverUrl)                               patch.cover_url  = newCoverUrl;
      if (newPrompt)                                 patch.prompt_id  = newPrompt;
      else if (!newPrompt && t.promptId)             patch.prompt_id  = null;
      if (newTags !== (t.tags || ''))                patch.tags       = newTags || null;
      if (Object.keys(patch).length > 0) {
        await apiFetch(`/tracks/${encodeURIComponent(t.dbId)}`, { method: 'PATCH', json: patch });
      }
    }

    // 3. Mise à jour localStorage
    const updated = tracks.map(x => {
      if (x.id !== _editTrackLocalId) return x;
      return {
        ...x,
        name:         newTitle || x.name,
        color:        newColor || x.color,
        coverUrl:     newCoverUrl || x.coverUrl,
        coverDataUrl: _editCoverPreview || x.coverDataUrl,
        promptId:     newPrompt || x.promptId || null,
        tags:         newTags || x.tags || null,
      };
    });
    saveMyTracks(updated);
    renderMyTracks();
    renderArtistCard();
    dashToast('Son mis à jour ✓');
    closeTrackEdit();
  } catch (err) {
    dashToast('Erreur : ' + (err && err.message || 'inconnue'));
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Enregistrer'; }
  }
}

async function deleteTrack(id) {
  const tracks    = getMyTracks();
  const trackToDelete = tracks.find(t => t.id === id);

  // Supprimer en localStorage immédiatement
  saveMyTracks(tracks.filter(t => t.id !== id));
  _rankingCache = null; // invalide le cache pour forcer un refresh du classement réel
  renderArtistCard();
  renderMyTracks();
  renderStats();
  renderRanking();
  dashToast('Son supprimé.');

  // Supprimer en DB si l'on a un dbId (shim FastAPI)
  if (trackToDelete?.dbId) {
    try {
      await apiFetch(`/tracks/${encodeURIComponent(trackToDelete.dbId)}`, { method: 'DELETE' });
    } catch (_) { /* silencieux */ }
  }
}

// ── 6. AVATAR UPLOAD ──────────────────────────────────────────────────────────
// Retiré avec le bloc #sec-artist : l'upload d'avatar se fait désormais sur
// /u/<slug> via artiste.js. Les helpers triggerAvatarUpload / handleAvatarUpload
// qui vivaient ici ne sont plus utilisés (plus aucun onclick ne les appelle).

// ── 7. UPLOAD DE SON ──────────────────────────────────────────────────────────

let _pendingFile      = null;
let _coverDataUrl     = null;
// Sprint 1 PR2 (2026-05-04) — File de la cover en mémoire pour upload R2.
// Distinct de _coverDataUrl (preview DataURL pour affichage local).
let _pendingCoverFile = null;

// Étape 2 — couleur choisie pour le son en cours d'upload. null = "hérite
// de la brandColor du profil" (comportement par défaut, aucune valeur
// sérialisée côté serveur). Dès que l'artiste clique sur un preset ou
// utilise le color picker, on la matérialise en hex "#RRGGBB".
let _pendingTrackColor = null;

// Regex partagé avec Pydantic (HEX_COLOR_RE) et Flask. Source unique.
const TRACK_COLOR_RE = /^#[0-9a-fA-F]{6}$/;

// Helper : résout la couleur effective d'un track pour l'affichage.
// Ordre : track.color → profile.brandColor → or WATT par défaut.
// Exposé sur window pour pouvoir être réutilisé depuis artiste.js
// (cellules orphelines sur /u/<slug>, étape 5).
function resolveTrackColor(track, profile) {
  const t = track && track.color;
  if (typeof t === 'string' && TRACK_COLOR_RE.test(t)) return t;
  const b = profile && profile.brandColor;
  if (typeof b === 'string' && TRACK_COLOR_RE.test(b)) return b;
  return '#FFD700';
}
if (typeof window !== 'undefined') window.resolveTrackColor = resolveTrackColor;

// Réinitialise la couleur sur "hériter du profil". Met à jour l'UI (pastille
// du bouton aux couleurs du profil, pilule aria-pressed) et vide le state.
function resetTrackColor() {
  _pendingTrackColor = null;
  const wrap   = document.getElementById('dashTrackColor');
  const btn    = document.getElementById('dashTrackColorInherit');
  const dot    = document.getElementById('dashTrackColorInheritDot');
  const input  = document.getElementById('dashTrackColorInput');
  if (wrap) wrap.dataset.inherit = 'true';
  if (btn)  btn.setAttribute('aria-pressed', 'true');
  // La pastille du bouton "Hériter" prend la couleur du profil, pour que
  // l'artiste voit à l'avance la teinte qu'il hérite.
  const profile = getWattProfile() || {};
  const inherited = TRACK_COLOR_RE.test(profile.brandColor || '') ? profile.brandColor : '#FFD700';
  if (dot) dot.style.background = inherited;
  if (input) input.value = inherited;
  // Désactive visuellement les presets
  document.querySelectorAll('.dash-track-color-preset').forEach(el => {
    el.classList.remove('is-active');
  });
}

// Sélectionne une couleur hex donnée. Utilisé par les presets + le color
// input natif. Idempotent ; si la même couleur est re-cliquée, on bascule
// en mode hériter (UX "toggle off").
function pickTrackColor(hex) {
  const raw = String(hex || '').trim();
  if (!TRACK_COLOR_RE.test(raw)) return;
  // Toggle : re-cliquer sur la même couleur → retour "hériter"
  if (_pendingTrackColor && _pendingTrackColor.toLowerCase() === raw.toLowerCase()) {
    resetTrackColor();
    return;
  }
  _pendingTrackColor = raw;
  const wrap  = document.getElementById('dashTrackColor');
  const btn   = document.getElementById('dashTrackColorInherit');
  const input = document.getElementById('dashTrackColorInput');
  if (wrap) wrap.dataset.inherit = 'false';
  if (btn)  btn.setAttribute('aria-pressed', 'false');
  if (input) input.value = raw;
  document.querySelectorAll('.dash-track-color-preset').forEach(el => {
    el.classList.toggle('is-active', (el.dataset.color || '').toLowerCase() === raw.toLowerCase());
  });
}

// Handler pour <input type="color"> : délègue à pickTrackColor en
// normalisant la valeur (le navigateur renvoie toujours #xxxxxx minuscule).
function onTrackColorPick(e) {
  const v = (e && e.target && e.target.value) || '';
  pickTrackColor(v);
}

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

  // Initialise le mode par défaut (with_prompt) + le widget live de la grille
  // crédits↔euros + le compteur 0/1000 du prompt_text. Ces fonctions sont
  // idempotentes (safe si déjà appelées).
  setUploadMode('with_prompt');
  updatePromptCharCount();
  updateCreditGrid();
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
  // Reset chips mood création
  document.querySelectorAll('#dashMoodChips .dte2-chip').forEach(c => c.classList.remove('is-active'));
  // Reset bloc Recette IA (prompt_text, paroles, prix)
  ['dashPromptText', 'dashPromptLyrics'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const priceEl = document.getElementById('dashPromptPrice');
  if (priceEl) priceEl.value = 80;
  // Retour au mode par défaut "avec recette prompt" (architecture primaire)
  setUploadMode('with_prompt');
  updatePromptCharCount();
  updateCreditGrid();
  resetCoverPreview();
  // C4 Œuvre complète — réinitialise le bloc « vendre la pochette ».
  const _sc = document.getElementById('dashSellCover');
  if (_sc) _sc.checked = false;
  const _scWrap = document.getElementById('dashSellCoverWrap');
  if (_scWrap) _scWrap.hidden = true;
  ['dashCoverImgPlatform', 'dashCoverImgVersion', 'dashCoverImgPrompt', 'dashCoverImgSupply']
    .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const _scPrice = document.getElementById('dashCoverImgPrice');
  if (_scPrice) _scPrice.value = '50';
  // Étape 2 — remet le picker couleur en mode "hériter du profil" pour
  // que le prochain upload reparte propre (évite la fuite d'état d'un son
  // à l'autre si l'artiste en poste plusieurs d'affilée).
  try { resetTrackColor(); } catch (_) { /* noop — widget absent en mode mock */ }
  document.getElementById('dashProgressWrap').style.display = 'none';
}

// ─────────────────────────────────────────────────────────────────────────────
// MODE SWITCH — vente prompt (primary) ↔ poste simple (secondary)
// ─────────────────────────────────────────────────────────────────────────────
// Le mode est la décision structurante du post. Par défaut on met l'artiste
// en situation de VENTE (architecture prompt complète affichée) pour pousser
// la mécanique qui rapporte. L'artiste peut basculer en mode "simple" pour
// partager un son sans recette — dans ce cas le bloc prompt est masqué + la
// grille crédits↔euros disparaît, et le CTA devient "Publier sans recette".
//
// État stocké dans dashUploadForm.dataset.mode, lu par uploadTrack() au submit.
// Valeurs : 'with_prompt' (défaut) · 'simple' · 'beat' · 'pack' (C1).
function setUploadMode(mode) {
  // C2 (2026-06-12) — FLUX UNIQUE : le mode 'pack' est supprimé, tout
  // retombe sur with_prompt. La fonction est conservée (appelée à l'init
  // et par d'anciens raccourcis) mais ne pilote plus de pilules.
  mode = 'with_prompt';
  const form = document.getElementById('dashUploadForm');
  if (!form) return;
  form.dataset.mode = mode;

  // Pills actifs (tab state + aria)
  document.querySelectorAll('.dash-mode-pill').forEach(p => {
    const on = p.dataset.mode === mode;
    p.classList.toggle('is-active', on);
    p.setAttribute('aria-selected', on ? 'true' : 'false');
  });

  // Libellé du CTA — reflète la destination
  const cta = document.getElementById('dashUploadCtaLbl');
  if (cta) {
    cta.textContent = ({
      with_prompt: 'Publier la musique',
      pack:        'Publier le beat',
    })[mode];
  }
}

/* C2 (2026-06-12) — dashReadBeatFields SUPPRIMÉE : plus de champs beat
   séparés. La case « Proposer aussi comme beat » + BPM sont lus dans
   uploadTrack (is_beat/bpm sur le track). */
function dashToggleBeatFlag() {
  const on  = !!document.getElementById('dashBeatFlag')?.checked;
  const wrap = document.getElementById('dashBpmWrap');
  if (wrap) wrap.hidden = !on;
}

// C4 Œuvre complète — révèle/cache les champs provenance image quand
// l'artiste coche « vendre aussi la pochette comme image ».
function dashToggleSellCover() {
  const on   = !!document.getElementById('dashSellCover')?.checked;
  const wrap = document.getElementById('dashSellCoverWrap');
  if (wrap) wrap.hidden = !on;
}
if (typeof window !== 'undefined') window.dashToggleSellCover = dashToggleSellCover;

// Toggle beat dans l'édition catalogue (flag rétroactif, 2026-06-13)
function dte2ToggleBeatFlag() {
  const on  = !!document.getElementById('dte2BeatFlag')?.checked;
  const wrap = document.getElementById('dte2BpmWrap');
  if (wrap) wrap.hidden = !on;
}

// Compteur live du prompt_text + état de validité (empty / short / ok / over)
function updatePromptCharCount() {
  const ta   = document.getElementById('dashPromptText');
  const cnt  = document.getElementById('dashPromptCharCount');
  if (!ta || !cnt) return;
  const len = (ta.value || '').length;
  cnt.textContent = `${len} / 1000`;
  let state;
  if (len === 0)       state = 'empty';
  else if (len < 100)  state = 'short';
  else if (len > 1000) state = 'over';
  else                 state = 'ok';
  cnt.setAttribute('data-state', state);
}

// Met à jour le bloc "live" de la grille crédits↔euros selon le prix saisi.
// Fourchette calculée sur les 3 packs de credits.py :
//   pack_10  → 0.80 €/crédit  (plafond — le plus cher pour l'acheteur)
//   pack_200 → 0.60 €/crédit  (plancher — meilleur deal acheteur)
// On affiche donc : "prix × 0,60€"  —  "prix × 0,80€"
function updateCreditGrid() {
  const priceEl = document.getElementById('dashPromptPrice');
  if (!priceEl) return;
  const raw = parseInt(priceEl.value, 10);
  const credits = Number.isFinite(raw) && raw > 0 ? raw : 0;
  const min = credits * 0.60;
  const max = credits * 0.80;

  const display = document.getElementById('dashCreditLivePrice');
  const minEl   = document.getElementById('dashCreditLiveMin');
  const maxEl   = document.getElementById('dashCreditLiveMax');
  const fmt = (v) => v.toFixed(2).replace('.', ',') + '\u00A0€';
  if (display) display.textContent = credits;
  if (minEl)   minEl.textContent   = fmt(min);
  if (maxEl)   maxEl.textContent   = fmt(max);
}

function handleCoverDragOver(e) { e.preventDefault(); }

function handleCoverDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) loadCoverPreview(file);
}

function handleCoverSelect(e) {
  const file = e.target.files[0];
  if (file) {
    // Sprint 1 PR2 — on garde le File en mémoire pour l'upload R2 réel
    // au moment du Publier. _coverDataUrl reste pour la preview DOM.
    _pendingCoverFile = file;
    loadCoverPreview(file);
  }
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
  _pendingCoverFile = null;
  const img = document.getElementById('dashCoverPreview');
  const ph  = document.getElementById('dashCoverPlaceholder');
  if (img) { img.src = ''; img.style.display = 'none'; }
  if (ph)  { ph.style.display = ''; }
  const inp = document.getElementById('dashCoverInput');
  if (inp) inp.value = '';
}

// Sprint 1 PR2 (2026-05-04) — upload cover R2 via endpoint Flask
// /watt/upload-image (existant, déjà utilisé pour avatar/banner profil).
// Renvoie l'URL R2 publique, ou null si échec / pas de fichier.
async function _uploadTrackCover(file, trackName) {
  if (!file) return null;
  try {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('userId', (window.getCurrentUser && window.getCurrentUser() && window.getCurrentUser().id) || 'guest');
    fd.append('kind', 'track-cover');  // namespace R2 distinct de avatar/banner
    const res = await fetch('/watt/upload-image', { method: 'POST', body: fd });
    if (!res.ok) return null;
    const data = await res.json();
    return data.url || null;
  } catch (_) {
    return null;
  }
}

// PR A (2026-05-05) — crée le track côté FastAPI tracks (table consommée
// par /u/<slug>). Avant : c'était un "miroir" en complément du POST
// Flask. Maintenant : c'est LE POST principal, le path Flask n'est plus
// sollicité par le dashboard.
//
// Retourne le track FastAPI créé (avec id), ou propage l'erreur via
// throw si quelque chose pète (auth, 409 profile_public, validation,
// réseau). Le caller uploadTrack catch et affiche un toast clair.
//
// On envoie full_prompt comme placeholder (= title) car le service
// FastAPI create_track_with_dna exige ce champ pour créer la DNA
// associée. Le DNA per-track devient secondaire dans le nouveau
// modèle (l'ADN par artiste reprend le rôle), mais le champ reste
// obligatoire en DB tant qu'on n'a pas migré la contrainte.
async function _createFastApiTrackMirror({ title, audio_url, r2_key, color, cover_url, full_prompt, tags, platform, is_beat, bpm }) {
  if (typeof apiFetch !== 'function') {
    throw new Error('apiFetch indisponible');
  }
  try {
    const result = await apiFetch('/tracks/', {
      method: 'POST',
      json: {
        title,
        full_prompt: full_prompt || title || '—',
        color: color || null,
        audio_url: audio_url || null,
        r2_key: r2_key || null,
        cover_url: cover_url || null,
        tags: tags || null,
        platform: platform || null,
        // C2 — drapeau beat (étagère /beats) + BPM optionnel.
        is_beat: !!is_beat,
        bpm: bpm != null ? bpm : null,
      },
    });
    // result = TrackWithDNA { track: TrackRead, dna: DNARead }
    return (result && result.track) ? result.track : null;
  } catch (e) {
    // PR A (2026-05-05) — on propage l'erreur au lieu de retourner null
    // silencieusement. Le caller (uploadTrack) catch et affiche un toast
    // explicite à l'utilisateur. Cas typiques :
    //   - 409 profile_public=false → "Publie ton profil d'abord"
    //   - 401 auth manquante      → "Reconnecte-toi"
    //   - 422 validation          → détail Pydantic via _humanizeApiError
    console.error('[dashboard] FastAPI track POST failed:', e && e.message);
    throw e;
  }
}

async function uploadTrack() {
  // ── Étape 1 — Gate "profil publié" côté client ──────────────────────────
  // Défense en profondeur : même si la gate visuelle est contournée, on
  // refuse l'appel réseau si on SAIT que ça va renvoyer 409. On préserve
  // le comportement original si l'état n'a pas encore été chargé (!loaded),
  // pour ne pas pénaliser un démarrage API lent.
  if (_dashPublishState.loaded && !_dashPublishState.isPublic) {
    dashToast('Publie d\'abord ton profil pour pouvoir poster un son.');
    renderCreationGate();
    return;
  }

  const name = document.getElementById('dashTrackName').value.trim();
  if (!name) { dashToast('⚠ Le titre est obligatoire.'); return; }
  if (!_pendingFile) { dashToast('⚠ Aucun fichier sélectionné.'); return; }

  // C2 — plus de modes : validation précoce du seul flag beat (plus bas).

  // ── DÉCISION 100 % IA (2026-06-10) ──────────────────────────────────────
  // Smyleplay ne vend QUE des produits générés par IA. L'outil de
  // génération (plateforme) est donc obligatoire pour TOUTE publication
  // audio — plus seulement pour les recettes. C'est la provenance affichée
  // sur les cartes (4e repère, arme transparence).
  const _platformEarly = (document.getElementById('dashTrackPlatform')?.value || '').trim();
  if (!_platformEarly) {
    dashToast('⚠ Indique l\'IA avec laquelle ce son a été généré (plateforme d\'origine).');
    return;
  }

  // C2 (2026-06-12) — FLUX UNIQUE : plus de mode pack ni de champs beat
  // séparés. Le beat = drapeau de placement (case à cocher) + BPM optionnel,
  // envoyés avec le track. Validation BPM précoce (40..300 ou vide).
  const _isBeatFlag = !!document.getElementById('dashBeatFlag')?.checked;
  let _beatBpm = null;
  if (_isBeatFlag) {
    const _bpmRaw = (document.getElementById('dashTrackBpm')?.value || '').trim();
    if (_bpmRaw !== '') {
      const n = parseInt(_bpmRaw, 10);
      if (!Number.isInteger(n) || n < 40 || n > 300) {
        dashToast('⚠ BPM invalide : entre 40 et 300, ou laisse vide.');
        return;
      }
      _beatBpm = n;
    }
  }

  // ── C4 Œuvre complète — validation précoce « vendre la pochette » ───────
  // Si l'artiste veut vendre la pochette comme image : il FAUT une pochette
  // sélectionnée + provenance (plateforme + version), sinon on bloque le
  // submit (provenance image obligatoire, règle stricte). Le prix image est
  // validé ici aussi (3..500). Le prompt image est optionnel (fallback titre).
  const _sellCover = !!document.getElementById('dashSellCover')?.checked;
  let _coverImg = null;
  if (_sellCover) {
    const cErrs = [];
    if (!_pendingCoverFile) cErrs.push('une pochette (fichier image)');
    const cPlatform = (document.getElementById('dashCoverImgPlatform')?.value || '').trim();
    const cVersion  = (document.getElementById('dashCoverImgVersion')?.value || '').trim();
    if (!cPlatform) cErrs.push('la plateforme de l\'image');
    if (!cVersion)  cErrs.push('la version / modèle de l\'image');
    const cPriceRaw = parseInt(document.getElementById('dashCoverImgPrice')?.value, 10);
    const cPrice = Number.isFinite(cPriceRaw) ? cPriceRaw : NaN;
    if (!Number.isInteger(cPrice) || cPrice < 3 || cPrice > 500) {
      cErrs.push('un prix image entre 3 et 500');
    }
    let cSupply = null;
    const cSupplyRaw = (document.getElementById('dashCoverImgSupply')?.value || '').trim();
    if (cSupplyRaw !== '') {
      const ns = parseInt(cSupplyRaw, 10);
      if (Number.isInteger(ns) && ns >= 1) cSupply = ns;
      else cErrs.push('un nombre d\'exemplaires image valide (>= 1 ou vide)');
    }
    if (cErrs.length) {
      dashToast('⚠ Œuvre complète : il manque ' + cErrs.join(', ') + '.');
      return;
    }
    _coverImg = {
      platform: cPlatform,
      version:  cVersion,
      prompt:   (document.getElementById('dashCoverImgPrompt')?.value || '').trim(),
      price:    cPrice,
      supply:   cSupply,
    };
  }

  // ── Vérification limite freemium (comptes officiels exemptés) ───────────
  const _existing = getMyTracks();
  if (_existing.length >= FREE_LIMIT && !_isOfficialAccount()) {
    dashToast('Ta playlist gratuite est complète (6 / 6). PLUG WATT illimité arrive bientôt !');
    renderUploadState();
    cancelUpload();
    return;
  }

  const genre    = document.getElementById('dashGenre').value.trim();
  const tags     = document.getElementById('dashTags').value.trim();
  const desc     = document.getElementById('dashDesc').value.trim();
  // Item 1 — Plateforme d'origine du prompt (P1-F4 partiel)
  // Stockée en localStorage pour l'instant : le backend accueillera le champ
  // avec la migration P1-F4. Quand la DB stocke, on l'enverra aussi dans le
  // payload POST /api/watt/tracks. Affiché sur la fiche de vente publique.
  const platform = (document.getElementById('dashTrackPlatform')?.value || '').trim();

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
  let uploaded  = false;
  let streamUrl = null;
  let r2Key     = null;

  // ── 1. Upload fichier audio vers R2 ─────────────────────────────────────
  try {
    const fd = new FormData();
    fd.append('file',   _pendingFile);
    fd.append('name',   name);
    fd.append('userId', user ? String(user.id) : 'guest');

    const res  = await fetch('/watt/upload', { method: 'POST', body: fd });
    if (res.ok) {
      const data = await res.json();
      uploaded  = !data.mock;
      streamUrl = data.url  || null;
      r2Key     = data.key  || null;
      setProgress(70, 'Enregistrement…');
    }
  } catch (_) { /* mode hors-ligne */ }

  await wait(300);
  setProgress(80, 'Pochette…');

  // ── 1.5 Sprint 1 PR2 — Upload cover R2 (si l'artiste en a sélectionné une)
  // L'endpoint Flask /watt/upload-image est déjà en place pour
  // avatar/banner profil ; on le réutilise avec kind=track-cover pour
  // namespace dans le bucket. Échec gracieux : si l'upload cover rate,
  // le track est quand même créé (juste sans pochette persistée R2).
  let coverUrl = null;
  if (_pendingCoverFile) {
    coverUrl = await _uploadTrackCover(_pendingCoverFile, name);
  }

  setProgress(85, 'Sauvegarde en base…');

  // ── 2. PR A (2026-05-05) — POST track UNIQUEMENT côté FastAPI ──────────
  //
  // Avant : double POST (Flask /api/watt/tracks + FastAPI /tracks/) avec
  // le miroir FastAPI en best-effort silencieux. Bug : si le miroir FastAPI
  // ratait (auth manquante, payload invalide, etc.), le track existait
  // dans watt_tracks Flask mais PAS dans tracks FastAPI → invisible sur
  // /u/<slug> qui lit FastAPI uniquement. Tom a passé une session entière
  // à essayer d'écouter ses morceaux sans succès.
  //
  // Maintenant : POST FastAPI uniquement. Si l'auth FastAPI manque (JWT
  // sessionStorage absent ou invalide), on AFFICHE un toast d'erreur clair
  // et on STOPPE — pas de track fantôme en localStorage qui mentirait à
  // l'utilisateur sur l'état réel de son upload.
  //
  // Le path Flask `/api/watt/tracks` reste vivant côté serveur pour ne pas
  // casser d'éventuels autres consommateurs, mais le frontend dashboard
  // ne le sollicite plus.
  let dbTrackId = null;
  let fastApiTrack = null;

  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    setProgress(100, '⚠ Connexion requise');
    dashToast('⚠ Tu dois te reconnecter pour publier ton son. Ferme cette session et reconnecte-toi.');
    cancelUpload();
    return;
  }

  // C1.4 — l'ADN du morceau (DNA per-track) reçoit le VRAI prompt :
  // la recette est désormais obligatoire pour toute publication (plus de
  // « partage simple »), donc plus de placeholder mensonger en base.
  const _dnaPrompt = (document.getElementById('dashPromptText')?.value || '').trim();

  try {
    fastApiTrack = await _createFastApiTrackMirror({
      title:       name,
      audio_url:   streamUrl,
      r2_key:      r2Key,
      color:       _pendingTrackColor,
      cover_url:   coverUrl,
      full_prompt: _dnaPrompt || name,  // fallback titre si champ vide (bloqué plus loin de toute façon)
      tags:        tags || null,   // dashTags — lu plus haut (ligne ~1865)
      platform:    platform || null,  // dashTrackPlatform — lu plus haut
      // C2 — placement beat (case à cocher) + BPM optionnel.
      is_beat:     _isBeatFlag,
      bpm:         _beatBpm,
    });
  } catch (e) {
    // PR A — gestion fine des erreurs FastAPI. Cas spéciaux :
    //   - 409 = profile_public=false → gate pédagogique
    //   - 401 = auth invalide → demander relogin
    //   - autre = message générique avec détail Pydantic si dispo
    const status = e && e.status;
    if (status === 409) {
      setProgress(100, '⚠ Profil non publié');
      try { await loadPublishStatus(); } catch (_) {}
      try { renderCreationGate(); } catch (_) {}
      dashToast('Publie d\'abord ton profil pour pouvoir poster un son.');
    } else if (status === 401) {
      setProgress(100, '⚠ Connexion expirée');
      dashToast('Ta session a expiré. Reconnecte-toi pour publier.');
    } else {
      setProgress(100, '⚠ Échec enregistrement');
      const msg = (typeof _humanizeApiError === 'function')
        ? _humanizeApiError(e)
        : (e && e.message) || 'erreur inconnue';
      dashToast('⚠ Enregistrement en base échoué : ' + msg);
    }
    cancelUpload();
    return;
  }

  // PR A — si le POST FastAPI a "réussi" mais sans renvoyer de track id
  // (cas dégénéré, ne devrait pas arriver), on STOPPE quand même. Pas de
  // track fantôme. L'artiste voit un message clair et peut réessayer.
  if (!fastApiTrack || !fastApiTrack.id) {
    setProgress(100, '⚠ Échec enregistrement');
    dashToast('⚠ Le son a été uploadé mais le serveur n\'a pas renvoyé d\'ID. Recharge la page et réessaie.');
    cancelUpload();
    return;
  }

  dbTrackId = fastApiTrack.id;
  window._lastFastApiTrack = fastApiTrack;

  await wait(300);
  setProgress(95, 'Finalisation…');
  await wait(300);

  // ── 3. Toujours sauvegarder en localStorage (cache local) ───────────────
  const tracks = getMyTracks();
  const newTrack = {
    id:           dbTrackId ? `db-${dbTrackId}` : `wt-${Date.now()}`,
    dbId:         dbTrackId,
    name,
    genre,
    tags,
    desc,
    file:         _pendingFile.name,
    size:         _pendingFile.size,
    coverDataUrl: _coverDataUrl || null,
    // Étape 2 — conserve le choix local même en offline. null = hérite.
    color:        _pendingTrackColor,
    plays:        0,
    date:         new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' }),
    uploadedAt:   Date.now(),
    cloud:        uploaded,
    streamUrl,
    // Item 1 — plateforme d'origine ('suno'|'udio'|'riffusion'|'stable_audio'|'autre'|'')
    platform:     platform || null,
  };
  tracks.unshift(newTrack);
  saveMyTracks(tracks);

  // ── 4. Si mode = with_prompt, publier aussi la recette sur la marketplace ──
  // Bornes DOIVENT matcher Pydantic (app/schemas/marketplace.py) :
  //   prompt_text 100..1000 (plafond Suno), price_credits 3..500.
  // Si la track est déjà publiée mais le prompt rejeté par validation, on
  // tolère : la track reste en ligne, l'artiste peut éditer/republier le
  // prompt plus tard depuis la gestion catalogue (phase ultérieure).
  const form = document.getElementById('dashUploadForm');
  // C2 — flux unique : la recette est TOUJOURS publiée (un produit, un prix).
  {
    const promptText = (document.getElementById('dashPromptText')?.value || '').trim();
    const lyrics     = (document.getElementById('dashPromptLyrics')?.value || '').trim();
    const priceRaw   = parseInt(document.getElementById('dashPromptPrice')?.value, 10);
    const price      = Number.isFinite(priceRaw) ? priceRaw : 80;

    // P1-F4 (2026-05-04) — réglages de génération.
    // 4 obligatoires (platform, weirdness, style_influence, vocal_gender)
    // + 1 optionnel (model_version). Sans ces 4, le prompt est inutilisable
    // pour l'acheteur — on bloque la création de prompt (mais le son
    // reste publié, l'artiste peut compléter et republier le prompt
    // ultérieurement via la gestion catalogue).
    // La plateforme du prompt = celle de la track (déjà sélectionnée
    // dans dashTrackPlatform en haut du formulaire).
    const platformVal       = (document.getElementById('dashTrackPlatform')?.value || '').trim();
    const modelVersionVal   = (document.getElementById('dashPromptModelVersion')?.value || '').trim();
    const weirdnessVal      = (document.getElementById('dashPromptWeirdness')?.value || '').trim();
    const styleInfluenceVal = (document.getElementById('dashPromptStyleInfluence')?.value || '').trim();
    const vocalGenderVal    = (document.getElementById('dashPromptVocalGender')?.value || '').trim();

    // Rareté/supply (comme les ADN) : nb d'exemplaires. Vide = illimité.
    const supRaw = (document.getElementById('dashPromptMaxSupply')?.value || '').trim();
    let promptMaxSupply = null;
    if (supRaw !== '') {
      const n = parseInt(supRaw, 10);
      if (Number.isInteger(n) && n >= 1) promptMaxSupply = n;
    }

    const promptErrs = [];
    if (promptText.length < 100)               promptErrs.push('prompt trop court (min 100 caractères)');
    if (promptText.length > 1000)              promptErrs.push('prompt trop long (max 1000)');
    if (price < 3 || price > 500)              promptErrs.push('prix entre 3 et 500 crédits');
    if (!platformVal)                          promptErrs.push('plateforme d\'origine');
    if (!weirdnessVal)                         promptErrs.push('weirdness');
    if (!styleInfluenceVal)                    promptErrs.push('style influence');
    if (!vocalGenderVal)                       promptErrs.push('voix (M/F/Instrumental)');

    if (promptErrs.length) {
      dashToast(`⚠ Son publié, prompt non créé — manque : ${promptErrs.join(', ')}`);
    } else {
      try {
        const promptResp = await apiFetch('/artist/me/prompts', {
          method: 'POST',
          json: {
            title:        name,                    // titre = même que la track
            description:  desc || `Recette IA de "${name}"`,
            prompt_text:  promptText,
            lyrics:       lyrics || null,
            price_credits: price,
            is_published: true,
            // P1-F4 — réglages génération (4 obligatoires + 1 optionnel)
            prompt_platform:        platformVal,
            prompt_model_version:   modelVersionVal || null,
            prompt_weirdness:       weirdnessVal,
            prompt_style_influence: styleInfluenceVal,
            prompt_vocal_gender:    vocalGenderVal,
            // Édition limitée (null = illimité) — rareté dérivée côté backend.
            ...(promptMaxSupply !== null ? { max_supply: promptMaxSupply } : {}),
          },
        });
        dashToast(`💎 Recette IA "${name}" publiée sur la marketplace.`);

        // Sprint 1 PR2 — Lien track FastAPI ↔ prompt (PATCH).
        // Si le miroir track FastAPI existe (créé plus haut) et qu'on
        // vient de créer le prompt, on lie les 2 via PATCH /tracks/{id}.
        // Permet à /u/<slug> d'afficher le bouton "Débloquer le prompt"
        // sur la card du track.
        const fastApiTrack = window._lastFastApiTrack;
        if (fastApiTrack && fastApiTrack.id && promptResp && promptResp.id) {
          try {
            await apiFetch(`/tracks/${encodeURIComponent(fastApiTrack.id)}`, {
              method: 'PATCH',
              json: { prompt_id: promptResp.id },
            });
          } catch (e) {
            console.warn('[dashboard] PATCH track prompt_id failed:', e && e.message);
          }
        }

        // ── C4 Œuvre complète — vendre aussi la pochette comme image ──────
        // Le son (promptResp.id) est créé. On crée l'image en réutilisant le
        // MÊME fichier cover (_pendingCoverFile), puis on lie les deux. Échec
        // partiel géré proprement : si l'image rate, le son reste publié ; si
        // seule la liaison rate, son + image existent quand même (toast clair).
        if (_sellCover && _coverImg && _pendingCoverFile && promptResp && promptResp.id) {
          try {
            const imgFd = new FormData();
            imgFd.append('file', _pendingCoverFile);
            imgFd.append('title', name);                       // même titre que le son
            imgFd.append('image_platform', _coverImg.platform);
            imgFd.append('image_model_version', _coverImg.version);
            // prompt_text NOT NULL côté API : fallback titre si laissé vide.
            imgFd.append('prompt_text', _coverImg.prompt || name);
            imgFd.append('price_credits', String(_coverImg.price));
            imgFd.append('is_published', 'true');
            if (_coverImg.supply !== null) imgFd.append('max_supply', String(_coverImg.supply));
            const imgResp = await apiFetch('/artist/me/images', { method: 'POST', body: imgFd });
            if (imgResp && imgResp.id) {
              try {
                await apiFetch(`/artist/me/prompts/${encodeURIComponent(imgResp.id)}/link`, {
                  method: 'POST',
                  // Flux A « né ensemble » : son + pochette créés dans la MÊME
                  // action → bundle_exclusive=true. Les deux produits ne
                  // s'affichent plus en carte individuelle sur les surfaces
                  // publiques (seulement via l'œuvre) ; l'achat séparé reste
                  // possible. Cf. flux B (images-create.js) qui omet ce flag.
                  json: { other_prompt_id: promptResp.id, bundle_exclusive: true },
                });
                dashToast(`🎨 Œuvre complète : pochette "${name}" en vente comme image, liée au son.`);
              } catch (le) {
                dashToast(`Image créée mais liaison au son échouée : ${_humanizeApiError(le)}. Son et image existent — réessaie la liaison plus tard.`);
              }
            }
          } catch (ie) {
            dashToast(`⚠ Son publié, mais image (pochette) refusée : ${_humanizeApiError(ie)}`);
          }
        }
      } catch (e) {
        // P1-B11 (2026-04-29) — Avant ce fix, e.body.detail pouvait être un
        // array Pydantic ou un objet, qui s'affichaient comme [object Object]
        // dans le toast. On parse maintenant les 3 formes possibles.
        dashToast(`⚠ Son publié, mais prompt refusé : ${_humanizeApiError(e)}`);
      }
    }
  }

  // ── 4ter — SUPPRIMÉ (C2, 2026-06-12) ────────────────────────────────────
  // Plus de ligne `prompts` type beat ni de PATCH beat_id : le beat est un
  // drapeau du track (is_beat + bpm), déjà envoyé à la création plus haut.
  if (_isBeatFlag) {
    dashToast(`🥁 "${name}" est aussi proposé comme beat (étagère /beats).`);
  }

  setProgress(100, uploaded ? '⚡ Son publié sur WATT !' : '⚡ Son sauvegardé !');
  await wait(1000);

  cancelUpload();
  _rankingCache = null; // invalide le cache pour forcer un refresh du classement réel
  renderArtistCard();
  renderStats();
  renderRanking();
  // C1 — rafraîchit les compteurs des tuiles WattBoard v3 (sons/beats/…)
  try { if (window.WattBoardV3) window.WattBoardV3.refresh(); } catch (_) {}
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
    setVal('peArtistName',    p.artistName     || '');
    setVal('peGenre',         p.genre          || '');
    setVal('peCity',          p.city           || '');
    setVal('peBio',           p.bio            || '');
    setVal('peInfluences',    p.influences     || '');
    setVal('peAvatarUrl',     p.avatarUrl      || '');
    setVal('peCoverPhotoUrl', p.coverPhotoUrl  || '');
    setVal('peSoundcloud',    p.soundcloud     || '');
    setVal('peInstagram',     p.instagram      || '');
    setVal('peYoutube',       p.youtube        || '');
    setVal('peTiktok',        p.tiktok         || '');
    setVal('peSpotify',       p.spotify        || '');
    setVal('peTwitterX',      p.twitterX       || '');
    // Chantier 1.2 — préremplir le color picker avec la couleur courante
    setBrandColorPicker(p.brandColor || '#FFD700');
    // Chantier "Profil artiste type" (migration 0017) — préremplir les 2
    // couleurs de thème de la page publique. Null = defaults violet WATT.
    setProfileThemePickers(p.profileBgColor || '', p.profileBrandColor || '');
    view.style.display = 'none';
    edit.style.display = '';
    if (btn) btn.textContent = 'Annuler';
  }
}

/* ── Chantier 1.2 — Color picker wiring ─────────────────────────────────────
   3 chemins d'entrée utilisateur (presets, color input, reset) alignés sur
   un seul état via setBrandColorPicker(hex). On normalise en #RRGGBB majuscule
   — même format que la CHECK constraint SQL côté FastAPI. */
function setBrandColorPicker(hex) {
  const raw = (hex || '#FFD700').trim();
  const m = raw.match(/^#?([0-9a-f]{6})$/i);
  const normalized = m ? `#${m[1].toUpperCase()}` : '#FFD700';

  const input   = document.getElementById('peBrandColor');
  const preview = document.getElementById('peBrandPreview');
  const hexLbl  = document.getElementById('peBrandHex');

  if (input)   input.value = normalized;
  if (preview) preview.style.background = normalized;
  if (hexLbl)  hexLbl.textContent = normalized;

  // Marque le swatch preset actif si la couleur correspond exactement
  document.querySelectorAll('#peBrandPresets .dash-brand-swatch').forEach(sw => {
    const c = (sw.dataset.color || '').toUpperCase();
    sw.classList.toggle('active', c === normalized);
  });
}

function resetBrandColor() { setBrandColorPicker('#FFD700'); }

/* ── Chantier "Profil artiste type" (migration 0017) — Thème page publique ──
   2 pickers (fond + accent) pilotés côté dashboard avant publication.
   On applique la valeur sur l'input natif, on met à jour l'étiquette hex
   et la preview live via 2 custom properties --pt-bg / --pt-brand.
   Passer "" (chaîne vide) remet les defaults violet WATT : c'est le signal
   "pas de perso" que Pydantic traduira en NULL côté DB. */
const _PT_DEFAULTS = { bg: '#070608', brand: '#8800FF' };

function _normalizeHex(raw, fallback) {
  const m = (raw || '').trim().match(/^#?([0-9a-f]{6})$/i);
  return m ? `#${m[1].toUpperCase()}` : fallback;
}

function setProfileThemePickers(bg, brand) {
  const bgHex    = _normalizeHex(bg,    _PT_DEFAULTS.bg);
  const brandHex = _normalizeHex(brand, _PT_DEFAULTS.brand);

  const bgInput     = document.getElementById('peProfileBgColor');
  const bgHexLbl    = document.getElementById('peProfileBgHex');
  const brandInput  = document.getElementById('peProfileBrandColor');
  const brandHexLbl = document.getElementById('peProfileBrandHex');
  const preview     = document.getElementById('peProfileThemePreview');

  if (bgInput)     bgInput.value = bgHex;
  if (bgHexLbl)    bgHexLbl.textContent = bgHex;
  if (brandInput)  brandInput.value = brandHex;
  if (brandHexLbl) brandHexLbl.textContent = brandHex;
  if (preview) {
    preview.style.setProperty('--pt-bg',    bgHex);
    preview.style.setProperty('--pt-brand', brandHex);
  }
}

function resetProfileTheme() {
  setProfileThemePickers(_PT_DEFAULTS.bg, _PT_DEFAULTS.brand);
}

// Init des events du picker — appelé une fois au DOMContentLoaded (cf. init).
function _initBrandPicker() {
  const presets = document.getElementById('peBrandPresets');
  if (presets) {
    presets.addEventListener('click', (e) => {
      const btn = e.target.closest('.dash-brand-swatch');
      if (!btn) return;
      e.preventDefault();
      setBrandColorPicker(btn.dataset.color || '#FFD700');
    });
  }
  const input = document.getElementById('peBrandColor');
  if (input) {
    input.addEventListener('input', () => setBrandColorPicker(input.value));
  }

  // Chantier "Profil artiste type" (migration 0017) — events thème public
  const bgInput    = document.getElementById('peProfileBgColor');
  const brandInput = document.getElementById('peProfileBrandColor');
  if (bgInput) {
    bgInput.addEventListener('input', () => {
      setProfileThemePickers(bgInput.value, brandInput ? brandInput.value : '');
    });
  }
  if (brandInput) {
    brandInput.addEventListener('input', () => {
      setProfileThemePickers(bgInput ? bgInput.value : '', brandInput.value);
    });
  }
}

function cancelProfileEdit() { toggleProfileEdit(); }

async function saveProfile() {
  const artistName = document.getElementById('peArtistName').value.trim();
  if (!artistName) { dashToast('⚠ Le nom d\'artiste est obligatoire.'); return; }

  // Chantier 1.2 — Lecture de la couleur de marque. On normalise en #RRGGBB
  // majuscule pour respecter la regex côté Pydantic (`^#[0-9A-F]{6}$`).
  const rawColor = document.getElementById('peBrandColor')?.value || '#FFD700';
  const mc = rawColor.trim().match(/^#?([0-9a-f]{6})$/i);
  const brandColor = mc ? `#${mc[1].toUpperCase()}` : '#FFD700';

  // Chantier "Profil artiste type" (migration 0017) — thème page publique.
  // Les 2 pickers natifs ne peuvent jamais être "vides" ; donc si l'utilisateur
  // n'y a pas touché on leur applique les defaults violet WATT. Ces defaults
  // sont envoyés en NULL côté API (cf. payload plus bas) pour signaler
  // "pas de personnalisation, utilise le thème WATT standard côté front".
  const rawBg      = document.getElementById('peProfileBgColor')?.value    || _PT_DEFAULTS.bg;
  const rawBrand   = document.getElementById('peProfileBrandColor')?.value || _PT_DEFAULTS.brand;
  const profileBgColor    = _normalizeHex(rawBg,    _PT_DEFAULTS.bg);
  const profileBrandColor = _normalizeHex(rawBrand, _PT_DEFAULTS.brand);

  const slug = slugify(artistName);
  const profile = {
    artistName,
    slug,
    genre:         document.getElementById('peGenre').value.trim(),
    bio:           document.getElementById('peBio').value.trim(),
    city:          document.getElementById('peCity')?.value.trim()           || '',
    influences:    document.getElementById('peInfluences')?.value.trim()     || '',
    avatarUrl:     document.getElementById('peAvatarUrl')?.value.trim()      || '',
    coverPhotoUrl: document.getElementById('peCoverPhotoUrl')?.value.trim()  || '',
    soundcloud:    document.getElementById('peSoundcloud').value.trim(),
    instagram:     document.getElementById('peInstagram').value.trim(),
    youtube:       document.getElementById('peYoutube').value.trim(),
    tiktok:        document.getElementById('peTiktok')?.value.trim()   || '',
    spotify:       document.getElementById('peSpotify')?.value.trim()  || '',
    twitterX:      document.getElementById('peTwitterX')?.value.trim() || '',
    brandColor,                                             // Chantier 1.2
    // Chantier "Profil artiste type" (migration 0017)
    profileBgColor,
    profileBrandColor,
    followers:     (getWattProfile() || {}).followers || 0,
  };

  // 1. Sauvegarder en localStorage (immédiat, toujours)
  saveWattProfile(profile);

  // 2. Sync FastAPI (artist_name + bio + socials + brand_color). Indispensable
  // pour que le bouton "Publier mon profil" valide (ces champs sont lus depuis
  // la DB FastAPI) ET pour que la page artiste publique /artiste/<slug> rende
  // la bonne couleur de marque.
  try {
    // On envoie tous les champs (même vides → null côté serveur grâce aux
    // validateurs Pydantic `empty_string_to_none`). Ça permet à l'utilisateur
    // de VIDER un champ (ex. retirer son Instagram) sans avoir à bypass.
    const payload = {};
    const setField = (key, val) => {
      // artist_name ne doit jamais être null (obligatoire). Pour les autres,
      // une string vide passera par Pydantic et sera normalisée à None.
      if (val !== undefined) payload[key] = (val === '' ? null : val);
    };
    if (profile.artistName)  payload.artist_name = profile.artistName;
    setField('bio',             profile.bio);
    setField('genre',           profile.genre);
    setField('city',            profile.city);
    setField('influences',      profile.influences);
    setField('avatar_url',      profile.avatarUrl);
    setField('cover_photo_url', profile.coverPhotoUrl);
    setField('soundcloud',      profile.soundcloud);
    setField('instagram',       profile.instagram);
    setField('youtube',         profile.youtube);
    setField('tiktok',          profile.tiktok);
    setField('spotify',         profile.spotify);
    setField('twitter_x',       profile.twitterX);
    if (profile.brandColor)  payload.brand_color = profile.brandColor;
    // Chantier "Profil artiste type" (migration 0017) — 2 couleurs de thème.
    // Les pickers natifs ont toujours une valeur (pas de "vide"), donc si
    // l'utilisateur garde pile les defaults violet WATT on envoie NULL pour
    // signaler "pas de perso, fallback thème standard" côté page publique.
    payload.profile_bg_color = (profile.profileBgColor === _PT_DEFAULTS.bg)
      ? null
      : profile.profileBgColor;
    payload.profile_brand_color = (profile.profileBrandColor === _PT_DEFAULTS.brand)
      ? null
      : profile.profileBrandColor;
    if (Object.keys(payload).length > 0 && typeof apiFetch === 'function') {
      await apiFetch('/users/me', { method: 'PATCH', json: payload });
    }
  } catch (err) {
    // Pas bloquant — le profil local est déjà sauvegardé.
    console.warn('[dashboard] Sync FastAPI échec :', err);
  }

  toggleProfileEdit();
  renderArtistCard();
  renderProfileView();
  applyDashboardBrandColor(profile.brandColor);
  dashToast('✓ Profil sauvegardé !');
}

function renderProfileView() {
  const p = getWattProfile();
  const initials = p ? (p.artistName || '?')[0].toUpperCase() : '?';
  const savedImg = safeStorage.getItem('smyle_watt_avatar');

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
    // Helper local : résout un handle ou une URL en une URL cliquable.
    // Pour IG/TikTok/Twitter, l'utilisateur peut entrer "@toto" ou une URL
    // complète — on normalise ici pour que le lien soit toujours valide.
    const resolve = (val, baseFn) => {
      if (!val) return '';
      const v = String(val).trim();
      if (/^https?:\/\//i.test(v)) return v;
      return baseFn(v.replace(/^@/, ''));
    };
    if (p.soundcloud) pvLinks.innerHTML += `<a class="dash-social-link" href="${p.soundcloud}" target="_blank">SoundCloud</a>`;
    if (p.instagram)  pvLinks.innerHTML += `<a class="dash-social-link" href="${resolve(p.instagram, h => `https://instagram.com/${h}`)}" target="_blank">Instagram</a>`;
    if (p.youtube)    pvLinks.innerHTML += `<a class="dash-social-link" href="${p.youtube}" target="_blank">YouTube</a>`;
    if (p.tiktok)     pvLinks.innerHTML += `<a class="dash-social-link" href="${resolve(p.tiktok,   h => `https://tiktok.com/@${h}`)}" target="_blank">TikTok</a>`;
    if (p.spotify)    pvLinks.innerHTML += `<a class="dash-social-link" href="${p.spotify}" target="_blank">Spotify</a>`;
    if (p.twitterX)   pvLinks.innerHTML += `<a class="dash-social-link" href="${resolve(p.twitterX, h => `https://x.com/${h}`)}" target="_blank">Twitter / X</a>`;
  }

  // Lien profil public
  const pvPublicLink = document.getElementById('pvPublicLink');
  if (pvPublicLink && p && p.artistName) {
    const slug = p.slug || slugify(p.artistName);
    const url  = `/@${slug}`;
    pvPublicLink.innerHTML = `
      <div class="dash-public-link-label">Ton profil public</div>
      <div class="dash-public-link-row">
        <a class="dash-public-link-url" href="${url}" target="_blank">${window.location.origin}${url}</a>
        <button class="dash-public-link-copy" onclick="copyPublicProfileLink('${url}')" title="Copier le lien">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="13" height="13">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
        </button>
      </div>`;
    pvPublicLink.style.display = 'block';
  } else if (pvPublicLink) {
    pvPublicLink.style.display = 'none';
  }

  // Chantier 1 — bloc "Publier mon profil" / "En vitrine"
  renderPublishBlock();
}

// ── 8 bis. PUBLICATION DU PROFIL (Chantier 1) ─────────────────────────────────
// Bascule le flag profile_public côté API. Tant qu'il est FALSE, l'artiste
// n'apparaît ni sur /watt/artists, ni sur la page d'accueil hub, ni dans le
// Réseau Créatif. La source de vérité est /users/me.profile_public.

let _dashPublishState = {
  loaded:   false,           // a-t-on reçu une réponse /users/me ?
  isPublic: false,           // profil actuellement en vitrine ?
  missing:  [],              // champs manquants renvoyés par un 422
  loading:  false,           // une requête est-elle en cours ?
};

async function loadPublishStatus() {
  if (typeof apiFetch !== 'function' || typeof getAuthToken !== 'function') return;
  if (!getAuthToken()) return;
  try {
    const me = await apiFetch('/users/me');
    _dashPublishState.isPublic = !!(me && me.profile_public);
    _dashPublishState.loaded   = true;
    _dashPublishState.missing  = [];

    // Chantier 1.2 — on synchronise le localStorage côté dashboard avec les
    // champs officiels de la DB FastAPI (source de vérité). Ça évite qu'un
    // utilisateur qui ré-ouvre le dashboard voie un vieux brandColor local
    // périmé par rapport à la couleur vraiment publiée.
    if (me) {
      // ── Bug #37 — bulle profil "SM" qui ne s'affichait plus ───────────
      // Le badge topbar (initiales) lit `smyle_current_user` via
      // getCurrentUser(). Ce cache n'est renseigné que par le bootstrap
      // auth.js sur index.html — si l'user arrive direct sur /dashboard
      // (nouveau onglet, cache vidé, navigation interne), le cache est
      // vide → initiales "?". On resynchronise depuis la source de
      // vérité ici, puis on re-render le card pour que le badge apparaisse.
      setCurrentUser({
        id:              me.id,
        email:           me.email,
        name:            me.name,
        artist_name:     me.artist_name,
        credits_balance: me.credits_balance,
      });

      const p = getWattProfile() || {};
      const merged = {
        ...p,
        artistName:    me.artist_name     || p.artistName     || '',
        bio:           me.bio             || p.bio            || '',
        genre:         me.genre           || p.genre          || '',
        city:          me.city            || p.city           || '',
        // Chantier "Profil artiste type" — nouveaux champs (migration 0016)
        influences:    me.influences      || p.influences     || '',
        avatarUrl:     me.avatar_url      || p.avatarUrl      || '',
        coverPhotoUrl: me.cover_photo_url || p.coverPhotoUrl  || '',
        soundcloud:    me.soundcloud      || p.soundcloud     || '',
        instagram:     me.instagram       || p.instagram      || '',
        youtube:       me.youtube         || p.youtube        || '',
        tiktok:        me.tiktok          || p.tiktok         || '',
        spotify:       me.spotify         || p.spotify        || '',
        twitterX:      me.twitter_x       || p.twitterX       || '',
        brandColor:    me.brand_color     || p.brandColor     || '',
        // Chantier "Profil artiste type" (migration 0017) — thème page publique.
        // On laisse "" si null côté DB : les pickers savent interpréter "" comme
        // "pas de perso → defaults violet WATT".
        profileBgColor:    me.profile_bg_color    || p.profileBgColor    || '',
        profileBrandColor: me.profile_brand_color || p.profileBrandColor || '',
        // P0-F1 reliquat (2026-04-28) — Casquettes : la DB est source de vérité.
        // Si me.roles est null (jamais coché), on retombe sur localStorage puis [].
        // Si me.roles est [] explicitement, c'est un choix utilisateur valide
        // (« aucune casquette ») → on respecte, pas de fallback localStorage.
        roles:         Array.isArray(me.roles) ? me.roles : (Array.isArray(p.roles) ? p.roles : []),
      };
      saveWattProfile(merged);
      applyDashboardBrandColor(merged.brandColor);

      // Re-render pour que les initiales apparaissent maintenant qu'on
      // a bien un user en localStorage.
      try { renderArtistCard(); } catch (_) { /* noop */ }
    }

    renderPublishBlock();
    renderCreationGate();
    renderPlugSection();
    // Chantier "1 bouton unifié" — le label du bouton save dépend de
    // profile_public qui n'est connu qu'après ce fetch. On bascule ici
    // et on rafraîchit aussi le hint slug du bloc PLUG WATT.
    try { _updateDashIdSaveButton(); } catch (_) {}
    try { _updateDashPlugSlugHint(); } catch (_) {}
    // Ré-hydrate les inputs #dashId* maintenant que le localStorage a
    // été resynchronisé depuis la DB (voir saveWattProfile plus haut).
    try { initDashIdentity(); } catch (_) {}
  } catch (err) {
    // Pas grave — on laisse le bloc caché si l'API n'est pas jointe.
    console.warn('[dashboard] loadPublishStatus échec :', err);
  }
}

// ── Étape 1 — Gate visuel "profil publié obligatoire avant publication" ─────
// Source de vérité : _dashPublishState.isPublic (synchronisé avec
// users.profile_public côté FastAPI par loadPublishStatus).
//   • profil non publié → banner pédagogique AU-DESSUS + form visible mais
//     désactivé (is-gated). L'user voit ce qu'il pourra faire ; les clics
//     sur la dropzone re-rappellent la banner.
//   • profil publié     → gate masquée, layout réactif normal.
// Le backend refuse de toute façon avec 409 (app.py et tracks.py), cette UI
// est une courtoisie qui évite à l'user de remplir le form pour rien, tout
// en gardant visible la proposition de valeur "vente prompt / upload".
function renderCreationGate() {
  const gate   = document.getElementById('dashCreationGate');
  const layout = document.getElementById('dashUploadLayout');
  const freeCt = document.getElementById('dashFreeCounter');
  if (!gate || !layout) return;

  // Tant qu'on n'a pas eu le retour /users/me on est optimistes : on ne
  // bloque pas. Sinon au premier paint l'user a une UI fermée le temps
  // d'un aller-retour API.
  if (!_dashPublishState.loaded) {
    gate.style.display = 'none';
    layout.classList.remove('is-gated');
    return;
  }

  // Profil publié → on cache la banner, on retire le dimming du layout
  // et on laisse renderUploadState() gérer le reste (teaser freemium etc.).
  if (_dashPublishState.isPublic) {
    gate.style.display = 'none';
    layout.classList.remove('is-gated');
    if (freeCt) freeCt.style.display = '';
    try { renderUploadState(); } catch (_) { /* noop */ }
    return;
  }

  // Profil non publié → banner visible + form dégradé ("is-gated" ajoute
  // l'opacité et désactive les pointer-events). On ne masque plus le
  // layout : l'user doit VOIR l'aspect vente prompt / upload pour être
  // motivé à publier son profil.
  gate.style.display = '';
  layout.classList.add('is-gated');
  if (freeCt) freeCt.style.display = '';
  const teaser = document.getElementById('dashPremiumTeaser');
  if (teaser) teaser.style.display = 'none';
}

// Intercepte tout clic sur le layout dégradé quand la gate est active :
// au lieu d'ouvrir le file picker, on ramène la banner à l'écran et on
// toast pour expliquer le pourquoi. Câblé en capture pour préempter les
// onclick inline (dropzone, boutons mode, presets couleur…).
function handleGatedLayoutClick(ev) {
  if (!_dashPublishState.loaded || _dashPublishState.isPublic) return;
  ev.preventDefault();
  ev.stopPropagation();
  const gate = document.getElementById('dashCreationGate');
  if (gate) {
    gate.scrollIntoView({ behavior: 'smooth', block: 'center' });
    gate.classList.add('is-flash');
    setTimeout(() => gate.classList.remove('is-flash'), 900);
  }
  dashToast('Crée d\'abord ton profil public pour débloquer l\'upload.');
}

// Redirige vers la page profil de l'user en FORÇANT le mode édition. On
// ajoute ?edit=1 : artiste.js intercepte ce param au chargement et ouvre
// directement l'éditeur (nom + bio + couleurs + bouton Publier) au lieu
// de la vue "fans". Slug utilisé si dispo pour une URL stable, sinon /u/me
// (aliasé côté Flask vers le slug du user connecté).
function gotoMyProfile() {
  const p    = getWattProfile() || {};
  const slug = p.slug || p.artistSlug || '';
  const base = slug ? `/@${encodeURIComponent(slug)}` : '/@me';
  window.location.href = `${base}?edit=1`;
}

/* ── Chantier 1.2 — applique la brandColor sur le dashboard ─────────────────
   Pose `--brand` / `--brand-rgb` sur <html> pour que tout le dashboard adopte
   la teinte choisie (avatar preview, bordures actives, bouton publier, etc.
   Les sélecteurs CSS qui utilisent ces vars ne sont pas encore tous migrés :
   pour l'instant seule la page artiste publique en bénéficie réellement.
   Cette mise à jour reste utile pour la cellule wattboard (étape 2D) qui sera
   peinte dans une autre passe, et pour un futur onboarding cohérent. */
function applyDashboardBrandColor(hex) {
  const raw = (hex || '').trim();
  const m = raw.match(/^#?([0-9a-f]{6})$/i);
  const root = document.documentElement;
  if (!m) {
    root.style.removeProperty('--brand');
    root.style.removeProperty('--brand-rgb');
    return;
  }
  const normalized = `#${m[1].toUpperCase()}`;
  const n = parseInt(m[1], 16);
  const rgb = `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
  root.style.setProperty('--brand', normalized);
  root.style.setProperty('--brand-rgb', rgb);
}

function renderPublishBlock() {
  const el = document.getElementById('pvPublishBlock');
  if (!el) return;

  // Si on n'a pas encore eu le retour /users/me, on n'affiche rien
  // (évite un flash "Publier" puis "Déjà publié").
  if (!_dashPublishState.loaded) { el.style.display = 'none'; el.innerHTML = ''; return; }

  const p = getWattProfile() || {};
  const hasName  = !!(p.artistName && p.artistName.trim());
  const hasBio   = !!(p.bio && p.bio.trim());
  const loading  = _dashPublishState.loading;

  el.style.display = 'block';

  if (_dashPublishState.isPublic) {
    // État 3 — publié
    el.innerHTML = `
      <div class="dash-publish-label">Statut public</div>
      <div class="dash-publish-row">
        <span class="dash-publish-status">En vitrine WATT</span>
        <button class="dash-publish-unlink" onclick="unpublishMyProfile()" ${loading ? 'disabled' : ''}>
          Retirer de la vitrine
        </button>
      </div>
      <div class="dash-publish-hint" style="margin-top:8px">
        Ton profil est visible sur l'accueil et dans le Réseau Créatif. Les autres artistes peuvent te suivre.
      </div>`;
    return;
  }

  // État 1 ou 2 — non publié
  const missing = _dashPublishState.missing || [];
  const clientMissing = [];
  if (!hasName) clientMissing.push('artist_name');
  if (!hasBio)  clientMissing.push('bio');
  // On ne connaît pas côté client le nombre de tracks DB exacte → on laisse le
  // serveur trancher. Mais si localStorage a déjà un nom+bio et aucune erreur
  // serveur récente, on permet le clic optimiste.

  const canTryClient = hasName && hasBio;
  const serverBlocks = missing.length > 0;
  const disabled = !canTryClient || loading;

  el.innerHTML = `
    <div class="dash-publish-label">Publier mon profil</div>
    <div class="dash-publish-row">
      <button class="dash-publish-btn" onclick="publishMyProfile()" ${disabled ? 'disabled' : ''}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" width="12" height="12">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
        ${loading ? 'Publication…' : 'Publier mon profil'}
      </button>
      <div class="dash-publish-hint">
        Rend ton profil visible sur la <strong>vitrine WATT</strong> et le <strong>Réseau Créatif</strong>.
        Requis : un nom, une bio, au moins un son.
      </div>
    </div>
    ${(serverBlocks || (clientMissing.length && !canTryClient))
      ? renderPublishMissing(serverBlocks ? missing : clientMissing)
      : ''}
  `;
}

function renderPublishMissing(missing) {
  // Depuis la suppression du gate « 1 son + bio requis », seul
  // artist_name peut être listé. On garde les anciens labels pour
  // compat, au cas où un vieux client ou un proxy renvoie encore
  // des champs legacy — mais en pratique le backend ne renvoie
  // plus que 'artist_name'.
  const labels = {
    artist_name: 'Un <strong>nom</strong> (onglet Modifier).',
    bio:         'Une <strong>bio</strong> (onglet Modifier).',
    tracks:      'Un <strong>son</strong> uploadé sur ton dashboard.',
  };
  const items = missing.map(k => `<li>${labels[k] || k}</li>`).join('');
  return `
    <div class="dash-publish-missing">
      Il te manque encore :
      <ul>${items}</ul>
    </div>`;
}

async function publishMyProfile() {
  if (_dashPublishState.loading) return;
  _dashPublishState.loading = true;
  renderPublishBlock();
  try {
    const res = await apiFetch('/watt/me/profile/publish', {
      method: 'POST',
      json:   {},
    });
    _dashPublishState.isPublic = !!(res && res.profilePublic);
    _dashPublishState.missing  = [];
    _dashPublishState.loading  = false;
    renderPublishBlock();
    // Étape 1 : dès que profile_public bascule à true, on déverrouille le form
    // upload. Inversement (unpublishMyProfile) on le re-verrouille.
    renderCreationGate();
    renderArtistCard();
    renderPlugSection();
    dashToast('✨ Ton profil est publié sur la vitrine WATT !');

    // Bus — informe les autres pages / onglets (marketplace, /u/<slug> owner)
    if (window.SmyleEvents && res && res.artist) {
      window.SmyleEvents.emit(
        window.SmyleEvents.TYPES.PROFILE_PUBLISHED,
        { artist: res.artist }
      );
    }
  } catch (err) {
    _dashPublishState.loading = false;
    if (err && err.status === 422) {
      const detail  = err.body && err.body.detail;
      const missing = (detail && detail.missing) || [];
      _dashPublishState.missing = missing;
      renderPublishBlock();
      dashToast('⚠ Profil incomplet — vérifie ce qui manque.');
    } else if (err && err.status === 401) {
      dashToast('⚠ Session expirée — reconnecte-toi.');
      renderPublishBlock();
    } else {
      console.error('[dashboard] publishMyProfile erreur :', err);
      dashToast('⚠ Impossible de publier — réessaie dans un instant.');
      renderPublishBlock();
    }
  }
}

async function unpublishMyProfile() {
  if (_dashPublishState.loading) return;
  if (!confirm('Retirer ton profil de la vitrine WATT ? Tes sons et abonnés restent, mais tu ne seras plus visible sur l\'accueil tant que tu n\'auras pas re-publié.')) return;
  _dashPublishState.loading = true;
  renderPublishBlock();
  try {
    const res = await apiFetch('/watt/me/profile/unpublish', {
      method: 'POST',
      json:   {},
    });
    _dashPublishState.isPublic = !!(res && res.profilePublic);
    _dashPublishState.missing  = [];
    _dashPublishState.loading  = false;
    renderPublishBlock();
    renderCreationGate();
    renderArtistCard();
    renderPlugSection();
    dashToast('Ton profil est retiré de la vitrine.');

    if (window.SmyleEvents && res) {
      window.SmyleEvents.emit(
        window.SmyleEvents.TYPES.PROFILE_UNPUBLISHED,
        { artistId: (res.artist && res.artist.id) || null, slug: res.artistSlug || null }
      );
    }
  } catch (err) {
    _dashPublishState.loading = false;
    console.error('[dashboard] unpublishMyProfile erreur :', err);
    dashToast('⚠ Impossible de retirer — réessaie dans un instant.');
    renderPublishBlock();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// CHANTIER "1 BOUTON UNIFIÉ" — SECTION IDENTITÉ (sec-identity)
// ═══════════════════════════════════════════════════════════════════════════
// Follow-up ADR-001 (2026-04-21). La section #sec-identity du dashboard est
// la SEULE zone d'édition du profil. Jusqu'ici ses handlers onclick
// (dashIdentitySave / dashIdentityPickAvatar / dashIdentityPickCover)
// pointaient sur du vide : boutons décoratifs. On les câble ici.
//
// Philosophie "1 bouton" (réf. Vinted / Airbnb / LinkedIn, validée par Tom) :
//   • profile_public === false → label "Publier mon profil"
//                                  → PATCH /users/me + POST /watt/me/profile/publish
//   • profile_public === true  → label "Enregistrer"
//                                  → PATCH /users/me seul
// Un user ne DOIT PAS avoir à comprendre la distinction "save vs publish" la
// première fois : un champ rempli = un profil en ligne. La dépublication
// reste gérée par le switch PLUG WATT (cas rare).
//
// Upload avatar/cover : on réutilise l'endpoint Flask /watt/upload-image
// déjà déployé (artiste.js en dépend aussi). Le backend renvoie { url } R2,
// on PATCH /users/me avec avatar_url / cover_photo_url. ══════════════════════

// Taille max image (aligné artiste.js + backend) — 5 Mo
const _DASH_ID_IMG_MAX = 5 * 1024 * 1024;

// Hydrate les inputs dashId* depuis getWattProfile() (source locale) / DB via
// loadPublishStatus(). Appelé au DOMContentLoaded et après chaque save.
// P1-B7 + P0-F1 reliquat (2026-04-28) — Casquettes sélectionnables (multi-select chips).
// Liste alignée sur ROLE_CODES backend (app/schemas/user.py, migration 0018).
// Si la liste backend bouge, mettre à jour ICI en miroir, sinon le PATCH /users/me
// rejettera avec "Rôle inconnu". Chips individuels (pas de chip hybride) : si un
// user est à la fois producteur et interprète, il coche les deux. Persisté en DB
// via `roles` array (cf. dashIdentitySave) + miroir localStorage.
// C4 (2026-06-16) — Casquettes désormais réparties en DEUX groupes :
//   • Audio (les 12 historiques, migration 0018)
//   • Visuel / Monde Image (12 nouveaux codes, ROLE_CODES C4)
// Les `key` ci-dessous matchent EXACTEMENT ROLE_CODES backend
// (app/schemas/user.py). Tout écart fait rejeter le PATCH /users/me
// ("Rôle inconnu"). La persistance (roles array) est inchangée : on ajoute
// uniquement des codes cochables dans la même grille.
const DASH_ID_ROLES_AUDIO = [
  { key: 'artiste',       label: 'Artiste / Interprète' },
  { key: 'producteur',    label: 'Producteur' },
  { key: 'beatmaker',     label: 'Beatmaker' },
  { key: 'topliner',      label: 'Topliner' },
  { key: 'ghostwriter',   label: 'Ghostwriter' },
  { key: 'compositeur',   label: 'Compositeur' },
  { key: 'parolier',      label: 'Parolier' },
  { key: 'arrangeur',     label: 'Arrangeur' },
  { key: 'editeur',       label: 'Éditeur' },
  { key: 'dj',            label: 'DJ' },
  { key: 'ingenieur_son', label: 'Ingénieur son' },
  { key: 'auditeur',      label: 'Auditeur' },
];
const DASH_ID_ROLES_VISUEL = [
  { key: 'illustrateur',        label: 'Illustrateur' },
  { key: 'graphiste',           label: 'Graphiste' },
  { key: 'directeur_artistique',label: 'Directeur artistique' },
  { key: 'photographe',         label: 'Photographe' },
  { key: 'concept_artist',      label: 'Concept artist' },
  { key: 'character_designer',  label: 'Character designer' },
  { key: 'retoucheur',          label: 'Retoucheur' },
  { key: 'coloriste',           label: 'Coloriste' },
  { key: 'artiste_3d',          label: 'Artiste 3D' },
  { key: 'prompteur',           label: 'Prompteur' },
  { key: 'designer',            label: 'Designer' },
  { key: 'collectionneur',      label: 'Collectionneur' },
];
// Conservé pour rétro-compat (validation / itérations éventuelles) : la liste
// plate de TOUS les codes rôle reconnus côté front.
const DASH_ID_ROLES = [...DASH_ID_ROLES_AUDIO, ...DASH_ID_ROLES_VISUEL];

function renderIdentityRolesGrid() {
  const grid = document.getElementById('dashIdRolesGrid');
  if (!grid) return;
  const p = getWattProfile() || {};
  const selected = Array.isArray(p.roles) ? p.roles : [];
  const renderChip = (r) => {
    const isOn = selected.includes(r.key);
    return `<button type="button" class="dash-role-chip${isOn ? ' is-on' : ''}"
      data-role-key="${r.key}" onclick="dashIdentityToggleRole('${r.key}')"
      aria-pressed="${isOn}">${r.label}</button>`;
  };
  const group = (title, roles) =>
    `<div class="dash-roles-group">
       <div class="dash-roles-group-title">${title}</div>
       <div class="dash-roles-group-chips">${roles.map(renderChip).join('')}</div>
     </div>`;
  grid.innerHTML =
    group('🎵 Audio', DASH_ID_ROLES_AUDIO) +
    group('🖼 Visuel', DASH_ID_ROLES_VISUEL);
}

function dashIdentityToggleRole(key) {
  const p = getWattProfile() || {};
  const current = Array.isArray(p.roles) ? [...p.roles] : [];
  const idx = current.indexOf(key);
  if (idx >= 0) current.splice(idx, 1);
  else current.push(key);
  saveWattProfile({ ...p, roles: current });
  renderIdentityRolesGrid();
}
if (typeof window !== 'undefined') {
  window.dashIdentityToggleRole = dashIdentityToggleRole;
}

// ───────────────────────────────────────────────────────────────
// P1-F9 — Vendre une voix (bloc 1c, cellule Création)
//
// Câblage backend complet (PR feat/voices-frontend-dashboard) :
//   - Le draft local (localStorage.wattVoiceDraft) reste utilisé pour
//     préserver le formulaire en cours de saisie (genres + license + sample
//     filename) tant que l'utilisateur n'a pas cliqué Enregistrer. Une fois
//     enregistré, c'est /api/voices qui fait foi.
//   - Le sample audio est uploadé via l'endpoint Flask /api/watt/upload
//     existant (réutilisé tel quel — même pipeline R2 que les tracks).
//     Le backend FastAPI /api/voices reçoit l'URL R2 résultante.
//   - La liste des voix créées est chargée depuis GET /api/voices/me et
//     rendue sous le formulaire avec les actions Publier / Modifier /
//     Supprimer.
//
// IMPORTANT — règle Tom (project_voice_separation_rule) : les voix ne sont
// JAMAIS dans le shuffle / playlists / DNA. Elles vivent dans leur propre
// table et leurs propres endpoints.
// ───────────────────────────────────────────────────────────────
const DASH_VOICE_GENRES = [
  { key: 'rnb',     label: 'RnB' },
  { key: 'pop',     label: 'Pop' },
  { key: 'trap',    label: 'Trap' },
  { key: 'rap',     label: 'Rap' },
  { key: 'electro', label: 'Electro' },
  { key: 'house',   label: 'House' },
  { key: 'afro',    label: 'Afro' },
  { key: 'jazz',    label: 'Jazz' },
  { key: 'soul',    label: 'Soul' },
  { key: 'rock',    label: 'Rock' },
  { key: 'autre',   label: 'Autre' },
];

// État en mémoire des voix backend de l'utilisateur. Rempli par loadMyVoices().
//   list      : list<VoiceFullRead> (renvoyé par GET /api/voices/me)
//   loading   : un fetch /api/voices/me est en cours
//   editingId : si non null, le formulaire est en mode édition de cette voix
//   pendingFile : fichier audio en attente d'upload (capturé par
//                 dashVoiceHandleSampleFile, consommé par dashVoiceSave)
const _voicesState = {
  list: [],
  loading: false,
  editingId: null,
  pendingFile: null,
};

function _getVoiceDraft() {
  try { return JSON.parse(localStorage.getItem('wattVoiceDraft') || '{}'); }
  catch (_) { return {}; }
}
function _saveVoiceDraft(d) {
  try { localStorage.setItem('wattVoiceDraft', JSON.stringify(d || {})); }
  catch (_) {}
}

function renderVoiceGenresChips() {
  const grid = document.getElementById('dashVoiceGenresGrid');
  if (!grid) return;
  const d = _getVoiceDraft();
  const selected = Array.isArray(d.genres) ? d.genres : [];
  grid.innerHTML = DASH_VOICE_GENRES.map(g => {
    const isOn = selected.includes(g.key);
    return `<button type="button" class="dash-voice-chip${isOn ? ' is-on' : ''}"
      data-genre-key="${g.key}" onclick="dashVoiceToggleGenre('${g.key}')"
      aria-pressed="${isOn}">${g.label}</button>`;
  }).join('');
}

function dashVoiceToggleGenre(key) {
  const d = _getVoiceDraft();
  const current = Array.isArray(d.genres) ? [...d.genres] : [];
  const idx = current.indexOf(key);
  if (idx >= 0) current.splice(idx, 1);
  else current.push(key);
  _saveVoiceDraft({ ...d, genres: current });
  renderVoiceGenresChips();
}

function dashVoiceSelectLicense(radio) {
  if (!radio) return;
  const wrap = document.getElementById('dashVoiceLicenseGrid');
  if (wrap) {
    wrap.querySelectorAll('.dash-voice-radio').forEach(r => r.classList.remove('is-on'));
    const label = radio.closest('.dash-voice-radio');
    if (label) label.classList.add('is-on');
  }
  const d = _getVoiceDraft();
  _saveVoiceDraft({ ...d, license: radio.value });
}

function dashVoiceHandleSampleFile(ev) {
  const file = ev && ev.target && ev.target.files && ev.target.files[0];
  const zone = document.getElementById('dashVoiceSampleZone');
  const info = document.getElementById('dashVoiceSampleInfo');
  if (!file || !zone || !info) return;
  const sizeKb = Math.round(file.size / 1024);
  const sizeLbl = sizeKb > 1024 ? (sizeKb / 1024).toFixed(1) + ' Mo' : sizeKb + ' Ko';
  info.innerHTML = `<strong>${file.name}</strong>${sizeLbl} · ${file.type || 'audio'}`;
  zone.classList.add('has-file');
  // On garde le File en mémoire pour l'upload réel au moment du Save.
  // localStorage ne peut pas stocker un File — on n'y met que le nom (UX).
  _voicesState.pendingFile = file;
  const d = _getVoiceDraft();
  _saveVoiceDraft({ ...d, sampleName: file.name, sampleSize: file.size });
}

function dashVoiceResetForm() {
  ['dashVoiceName', 'dashVoiceStyle'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  const price = document.getElementById('dashVoicePrice');
  if (price) price.value = 200;
  const firstRadio = document.querySelector('#dashVoiceLicenseGrid input[value="personnel"]');
  if (firstRadio) { firstRadio.checked = true; dashVoiceSelectLicense(firstRadio); }
  const zone = document.getElementById('dashVoiceSampleZone');
  const info = document.getElementById('dashVoiceSampleInfo');
  if (zone) zone.classList.remove('has-file');
  if (info) info.innerHTML = `<strong>Aucun fichier</strong>.mp3, .wav, .m4a — 30s à 2min — a cappella de préférence`;
  _voicesState.pendingFile = null;
  _voicesState.editingId = null;
  _saveVoiceDraft({ genres: [], license: 'personnel' });
  renderVoiceGenresChips();
  // Restaurer le label du bouton à "Enregistrer ma voix" (pas "Mettre à jour")
  const lbl = document.getElementById('dashVoiceSaveLbl');
  if (lbl) lbl.textContent = 'Enregistrer ma voix';
}

// Upload du sample audio vers R2 via le nouvel endpoint Flask qui
// génère AUSSI le preview 30s (chantier 2026-05-13).
// Renvoie { sample_url, preview_url } ou null si échec / mode hors-ligne.
async function _uploadVoiceSample(file, voiceName) {
  if (!file) return null;
  try {
    const fd = new FormData();
    fd.append('file', file);
    // /api/watt/upload prend un "name" pour dériver la clé R2. On lui donne
    // un préfixe "VOICE-<name>" pour distinguer les samples voix des tracks
    // dans le bucket (debug / cleanup batch plus facile).
    fd.append('name', `VOICE-${voiceName || 'sample'}`);
    fd.append('userId', (window.getCurrentUser && window.getCurrentUser() && window.getCurrentUser().id) || 'guest');
    const res = await fetch('/watt/upload-voice', { method: 'POST', body: fd });
    if (!res.ok) return null;
    const data = await res.json();
    // Le mode dev sans R2 renvoie { mock: true, url: null, key }.
    // Dans ce cas on ne peut pas créer la voix : le backend exige sample_url.
    // Si data.mock, on est en mode dev sans R2 — null pour signaler échec.
    if (data.mock || !data.sample_url) return null;
    return { sample_url: data.sample_url, preview_url: data.preview_url || null };
  } catch (_) {
    return null;
  }
}

async function dashVoiceSave() {
  const name   = (document.getElementById('dashVoiceName')  || {}).value || '';
  const style  = (document.getElementById('dashVoiceStyle') || {}).value || '';
  const price  = parseInt((document.getElementById('dashVoicePrice') || {}).value || '0', 10);
  const d = _getVoiceDraft();
  const genres = Array.isArray(d.genres) ? d.genres : [];
  // Chantier Voix 2026-06-12 — plus de licence dans l'UI : la rareté #X/N
  // porte la mécanique. Le backend pose 'personnel' par défaut en DB.
  const isEdit = Boolean(_voicesState.editingId);
  const supplyRaw = ((document.getElementById('dashVoiceMaxSupply') || {}).value || '').trim();
  let maxSupply = null;
  if (supplyRaw !== '') {
    const n = parseInt(supplyRaw, 10);
    if (Number.isInteger(n) && n >= 1) maxSupply = n;
  }
  const errs = [];
  if (!name.trim())           errs.push('Nom de la voix');
  if (!style.trim())          errs.push('Style de voix');
  if (genres.length === 0)    errs.push('Au moins 1 genre');
  if (supplyRaw !== '' && maxSupply === null) errs.push('Nombre d\'exemplaires (entier ≥ 1, ou vide)');
  // En mode édition, le sample est optionnel (on garde celui en DB si pas
  // de nouveau fichier). En création, il est obligatoire.
  if (!isEdit && !_voicesState.pendingFile) errs.push('Sample audio');
  if (!price || price < 50 || price > 5000) errs.push('Prix (50-5000)');
  if (errs.length) {
    alert('Champs manquants ou invalides :\n• ' + errs.join('\n• '));
    return;
  }

  if (typeof apiFetch !== 'function') {
    alert('API indisponible. Recharge la page.');
    return;
  }

  // ── Étape 1 : upload sample R2 si un nouveau fichier est attendu ────
  let sample_url = null;
  let preview_url = null;
  if (_voicesState.pendingFile) {
    const uploaded = await _uploadVoiceSample(_voicesState.pendingFile, name);
    if (!uploaded) {
      alert('Échec de l\'upload du sample audio. Réessaie ou vérifie ta connexion.');
      return;
    }
    sample_url  = uploaded.sample_url;
    preview_url = uploaded.preview_url;
    if (false) {  // garde structure existante
    }
  }

  // Phase B metadata 2026-05-13 : origine + lien track (optionnels visibles avant achat)
  const voiceOriginEl = document.getElementById('dashVoiceOrigin');
  const linkedTrackEl = document.getElementById('dashVoiceLinkedTrack');
  const voice_origin = voiceOriginEl ? (voiceOriginEl.value || null) : null;
  const linked_track_id = linkedTrackEl && linkedTrackEl.value ? linkedTrackEl.value : null;

  // ── Étape 2 : POST (création) ou PATCH (mise à jour) /api/voices ────
  const payload = { name, style, genres, price_credits: price };
  if (!isEdit && maxSupply !== null) payload.max_supply = maxSupply;
  if (sample_url)  payload.sample_url  = sample_url;
  if (preview_url) payload.preview_url = preview_url;
  if (voice_origin) payload.voice_origin = voice_origin;
  if (linked_track_id) payload.linked_track_id = linked_track_id;

  const btn = document.getElementById('dashVoiceSaveBtn');
  if (btn) btn.disabled = true;
  try {
    if (isEdit) {
      await apiFetch(`/api/voices/${_voicesState.editingId}`, {
        method: 'PATCH', json: payload,
      });
      if (typeof dashToast === 'function') dashToast('Voix mise à jour ✓');
    } else {
      await apiFetch('/api/voices', { method: 'POST', json: payload });
      if (typeof dashToast === 'function') {
        dashToast('Voix enregistrée — clique "Publier" pour la mettre en vente');
      }
    }
    // Reset draft local + form + reload list
    _saveVoiceDraft({ genres: [], license: 'personnel' });
    dashVoiceResetForm();
    await loadMyVoices();
  } catch (e) {
    const msg = (typeof _humanizeApiError === 'function')
      ? _humanizeApiError(e)
      : (e && e.message) || 'Erreur inconnue';
    alert(`Échec de l'enregistrement : ${msg}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Liste des voix existantes (CRUD côté liste) ─────────────────────────

async function loadMyVoices() {
  if (typeof apiFetch !== 'function') return;
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    // Pas connecté : pas de voix à charger, on cache la liste.
    _voicesState.list = [];
    renderMyVoicesList();
    return;
  }
  _voicesState.loading = true;
  try {
    const list = await apiFetch('/api/voices/me');
    _voicesState.list = Array.isArray(list) ? list : [];
  } catch (_) {
    _voicesState.list = [];
  } finally {
    _voicesState.loading = false;
    renderMyVoicesList();
  }
}

// Phase B metadata 2026-05-13 : remplir le dropdown #dashVoiceLinkedTrack
// avec la liste des tracks de l'artiste (pour associer une voix à un morceau).
async function dashVoiceLoadLinkedTrackOptions() {
  const select = document.getElementById('dashVoiceLinkedTrack');
  if (!select || typeof apiFetch !== 'function') return;
  if (typeof getAuthToken === 'function' && !getAuthToken()) return;
  try {
    // GET /tracks/me (FastAPI) — retourne un array direct de TrackRead
    const data = await apiFetch('/tracks/me');
    const tracks = Array.isArray(data) ? data : [];
    // Garder la 1ère option "Aucun" + injecter les tracks
    const baseOpt = select.querySelector('option[value=""]');
    select.innerHTML = '';
    if (baseOpt) select.appendChild(baseOpt);
    else {
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '— Aucun (voix autonome) —';
      select.appendChild(o);
    }
    tracks.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = t.title || 'Sans titre'; // FastAPI : "title" (pas "name")
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('[dashVoiceLoadLinkedTrackOptions]', e);
  }
}

function _voiceLicenseLabel(lic) {
  if (lic === 'personnel') return 'Personnel';
  if (lic === 'commercial') return 'Commercial';
  if (lic === 'exclusif')  return 'Exclusif';
  return lic || '';
}

function _voiceGenresLabel(keys) {
  if (!Array.isArray(keys) || !keys.length) return '';
  const labels = keys.map(k => {
    const g = DASH_VOICE_GENRES.find(x => x.key === k);
    return g ? g.label : k;
  });
  return labels.join(' · ');
}

function renderMyVoicesList() {
  const wrap = document.getElementById('dashVoicesList');
  if (!wrap) return;
  const list = _voicesState.list || [];
  if (_voicesState.loading) {
    wrap.innerHTML = `<div class="dash-voices-empty">Chargement…</div>`;
    return;
  }
  if (!list.length) {
    wrap.innerHTML = `<div class="dash-voices-empty">Tu n'as pas encore de voix mise en vente. Remplis le formulaire ci-dessus et clique "Enregistrer ma voix".</div>`;
    return;
  }
  wrap.innerHTML = list.map(v => {
    const pubBtn = v.is_published
      ? `<button type="button" class="dash-voice-card-btn" onclick="dashVoicePublishToggle('${v.id}', false)">Dépublier</button>`
      : `<button type="button" class="dash-voice-card-btn" onclick="dashVoicePublishToggle('${v.id}', true)">Publier</button>`;
    const statusClass = v.is_published ? 'is-published' : 'is-draft';
    const statusLbl   = v.is_published ? 'Publié' : 'Brouillon';
    const cardClass   = v.is_published ? 'dash-voice-card is-published' : 'dash-voice-card';
    const genres = _voiceGenresLabel(v.genres);
    // Chantier Voix — la rareté #X/N remplace la licence dans le récap.
    const _vSupplyLbl = (v.max_supply != null)
      ? (v.max_supply === 1
          ? ((v.editions_sold || 0) >= 1 ? '1/1 · vendue' : '1/1 vente unique')
          : `${(v.editions_sold || 0)}/${v.max_supply} vendus`)
      : 'illimité';
    const meta = [
      `${v.price_credits} SMYLES`,
      _vSupplyLbl,
      genres,
    ].filter(Boolean).join(' · ');
    return `
      <div class="${cardClass}">
        <div class="dash-voice-card-main">
          <div class="dash-voice-card-name">${_escapeHtml(v.name)} <span class="dash-voice-card-status ${statusClass}">${statusLbl}</span></div>
          <div class="dash-voice-card-meta">${_escapeHtml(v.style)} — ${_escapeHtml(meta)}</div>
        </div>
        <div class="dash-voice-card-actions">
          ${pubBtn}
          <button type="button" class="dash-voice-card-btn" onclick="dashVoiceEditFromList('${v.id}')">Modifier</button>
          <button type="button" class="dash-voice-card-btn is-danger" onclick="dashVoiceDeleteFromList('${v.id}')">Supprimer</button>
        </div>
      </div>
    `;
  }).join('');
}

// Helper local pour échapper les chaînes user dans le HTML — évite l'XSS
// si un nom de voix contient < ou >. On reste minimal (pas de DOMPurify) car
// le risque est limité (l'auteur ne peut s'auto-XSS) mais c'est cleaner.
function _escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function dashVoicePublishToggle(voiceId, nextState) {
  if (typeof apiFetch !== 'function') return;
  try {
    await apiFetch(`/api/voices/${voiceId}`, {
      method: 'PATCH',
      json: { is_published: Boolean(nextState) },
    });
    if (typeof dashToast === 'function') {
      dashToast(nextState
        ? 'Voix publiée — visible sur ton profil 🎉'
        : 'Voix dépubliée — invisible pour les fans');
    }
    await loadMyVoices();
  } catch (e) {
    const msg = (typeof _humanizeApiError === 'function')
      ? _humanizeApiError(e)
      : (e && e.message) || 'Erreur inconnue';
    alert(`Échec : ${msg}`);
  }
}

function dashVoiceEditFromList(voiceId) {
  const v = (_voicesState.list || []).find(x => x.id === voiceId);
  if (!v) return;
  _voicesState.editingId = voiceId;
  // Pas de pendingFile : on ne re-upload pas le sample sauf si l'user
  // resélectionne un fichier explicitement. Le PATCH n'enverra alors pas
  // sample_url et le backend conservera l'URL existante.
  _voicesState.pendingFile = null;
  // Pré-remplit les champs.
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
  set('dashVoiceName',  v.name);
  set('dashVoiceStyle', v.style);
  set('dashVoicePrice', v.price_credits);
  // Genres + license dans le draft pour que les renderers les affichent
  _saveVoiceDraft({ genres: Array.isArray(v.genres) ? v.genres : [], license: v.license || 'personnel' });
  renderVoiceGenresChips();
  const r = document.querySelector(`#dashVoiceLicenseGrid input[value="${v.license}"]`);
  if (r) { r.checked = true; dashVoiceSelectLicense(r); }
  // Affiche le nom du sample courant (pas de re-upload nécessaire)
  const zone = document.getElementById('dashVoiceSampleZone');
  const info = document.getElementById('dashVoiceSampleInfo');
  if (zone) zone.classList.add('has-file');
  if (info) info.innerHTML = `<strong>Sample existant conservé</strong>resélectionne un fichier pour le remplacer`;
  // Change le label du bouton pour signaler le mode édition
  const lbl = document.getElementById('dashVoiceSaveLbl');
  if (lbl) lbl.textContent = 'Mettre à jour la voix';
  // Scroll vers le formulaire pour que l'user voie les champs préremplis
  const sec = document.getElementById('sec-voice-sale');
  if (sec && sec.scrollIntoView) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function dashVoiceDeleteFromList(voiceId) {
  if (!confirm('Supprimer cette voix du marketplace ? Les acheteurs qui ont déjà acheté gardent leur accès au sample.')) return;
  if (typeof apiFetch !== 'function') return;
  try {
    await apiFetch(`/api/voices/${voiceId}`, { method: 'DELETE' });
    if (typeof dashToast === 'function') dashToast('Voix supprimée');
    // Si on était en train d'éditer cette voix, reset le formulaire.
    if (_voicesState.editingId === voiceId) dashVoiceResetForm();
    await loadMyVoices();
  } catch (e) {
    const msg = (typeof _humanizeApiError === 'function')
      ? _humanizeApiError(e)
      : (e && e.message) || 'Erreur inconnue';
    alert(`Échec suppression : ${msg}`);
  }
}

async function deleteAdnConfirm() {
  if (!confirm('Supprimer votre ADN du marketplace ? Les acheteurs qui ont déjà acquis votre ADN gardent leur accès en library.')) return;
  if (typeof apiFetch !== 'function') return;
  try {
    await apiFetch('/artist/me/adn', { method: 'DELETE' });
    if (typeof dashToast === 'function') dashToast('ADN supprimé');
    // Recharge la section ADN pour afficher l'état vide
    if (typeof loadMyAdn === 'function') {
      await loadMyAdn();
    } else {
      window.location.reload();
    }
  } catch (e) {
    const msg = (typeof _humanizeApiError === 'function')
      ? _humanizeApiError(e)
      : (e && e.message) || 'Erreur inconnue';
    alert('Échec suppression ADN : ' + msg);
  }
}

function initDashVoiceSale() {
  renderVoiceGenresChips();
  const d = _getVoiceDraft();
  if (d.name)   { const el = document.getElementById('dashVoiceName');  if (el) el.value = d.name; }
  if (d.style)  { const el = document.getElementById('dashVoiceStyle'); if (el) el.value = d.style; }
  if (d.price)  { const el = document.getElementById('dashVoicePrice'); if (el) el.value = d.price; }
  if (d.license) {
    const r = document.querySelector(`#dashVoiceLicenseGrid input[value="${d.license}"]`);
    if (r) { r.checked = true; dashVoiceSelectLicense(r); }
  }
  if (d.sampleName) {
    const zone = document.getElementById('dashVoiceSampleZone');
    const info = document.getElementById('dashVoiceSampleInfo');
    if (zone) zone.classList.add('has-file');
    if (info) info.innerHTML = `<strong>${d.sampleName}</strong>fichier en attente d'enregistrement`;
  }
  // Charge la liste backend et la rend.
  loadMyVoices();
}

if (typeof window !== 'undefined') {
  window.dashVoiceToggleGenre      = dashVoiceToggleGenre;
  window.dashVoiceSelectLicense    = dashVoiceSelectLicense;
  window.dashVoiceHandleSampleFile = dashVoiceHandleSampleFile;
  window.deleteAdnConfirm           = deleteAdnConfirm;
  window.dashVoiceResetForm        = dashVoiceResetForm;
  window.dashVoiceSave             = dashVoiceSave;
  window.dashVoicePublishToggle    = dashVoicePublishToggle;
  window.dashVoiceEditFromList     = dashVoiceEditFromList;
  window.dashVoiceDeleteFromList   = dashVoiceDeleteFromList;
  window.loadMyVoices              = loadMyVoices;
}

function initDashIdentity() {
  const p = getWattProfile() || {};
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ''; };
  set('dashIdName',           p.artistName);
  set('dashIdGenre',          p.genre);
  set('dashIdCity',           p.city);
  set('dashIdBio',            p.bio);
  set('dashIdSocialInstagram', p.instagram);
  set('dashIdSocialTiktok',    p.tiktok);
  set('dashIdSocialYoutube',   p.youtube);
  set('dashIdSocialSpotify',   p.spotify);
  set('dashIdSocialSoundcloud',p.soundcloud);
  renderIdentityRolesGrid();
  // Couleurs : defaults WATT si pas de valeur perso
  set('dashIdBgColor',     p.profileBgColor    || '#070608');
  set('dashIdBrandColor',  p.profileBrandColor || '#8800FF');
  _updateDashIdColorHex('dashIdBgColor',    'dashIdBgColorHex');
  _updateDashIdColorHex('dashIdBrandColor', 'dashIdBrandColorHex');
  // Previews visuels (avatar / cover)
  _renderDashIdAvatarPreview(p.avatarUrl);
  _renderDashIdCoverPreview(p.coverPhotoUrl);
  // Compteur bio
  _updateDashIdBioCount();
  const bio = document.getElementById('dashIdBio');
  if (bio && !bio.dataset.bound) {
    bio.addEventListener('input', _updateDashIdBioCount);
    bio.dataset.bound = '1';
  }
  // Repaint le hex à chaque tick du color picker
  ['dashIdBgColor', 'dashIdBrandColor'].forEach(id => {
    const el = document.getElementById(id);
    if (el && !el.dataset.bound) {
      el.addEventListener('input', () => _updateDashIdColorHex(id, id + 'Hex'));
      el.dataset.bound = '1';
    }
  });
  // Bouton save dynamique + hint slug
  _updateDashIdSaveButton();
  _updateDashPlugSlugHint();
}

function _updateDashIdColorHex(inputId, hexId) {
  const el  = document.getElementById(inputId);
  const hex = document.getElementById(hexId);
  if (el && hex) hex.textContent = (el.value || '').toUpperCase();
}

function _updateDashIdBioCount() {
  const bio = document.getElementById('dashIdBio');
  const cnt = document.getElementById('dashIdBioCount');
  if (bio && cnt) cnt.textContent = (bio.value || '').length;
}

function _renderDashIdAvatarPreview(url) {
  const el = document.getElementById('dashIdAvatarPreview');
  if (!el) return;
  if (url) {
    el.innerHTML = `<img src="${url}" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover"/>`;
  } else {
    const p = getWattProfile() || {};
    const initials = (p.artistName || '?')[0].toUpperCase();
    el.textContent = initials;
  }
}

function _renderDashIdCoverPreview(url) {
  const el = document.getElementById('dashIdCoverPreview');
  if (!el) return;
  if (url) {
    el.style.backgroundImage = `url("${url}")`;
    el.style.backgroundSize  = 'cover';
    el.style.backgroundPosition = 'center';
  } else {
    el.style.backgroundImage = '';
  }
}

// P1-B3 (2026-04-22) — Plus de label dynamique : le bouton Enregistrer
// fait PATCH /users/me, point. La publication est gérée par le switch
// PLUG WATT (dashPlugToggle). Fonction conservée pour compat d'appel,
// elle force simplement "Enregistrer".
function _updateDashIdSaveButton() {
  const lbl = document.getElementById('dashIdSaveLabel');
  if (!lbl) return;
  lbl.textContent = 'Enregistrer';
}

// Remplit le hint "/@<slug>" du bloc PLUG WATT avec le vrai slug calculé.
// Fallback "/@—" si pas de profil encore (cas first-run).
function _updateDashPlugSlugHint() {
  const el = document.getElementById('dashPlugSlugHint');
  if (!el) return;
  const user = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  const p    = getWattProfile();
  let slug = '';
  try { slug = _deriveArtistSlug(user, p) || ''; } catch (_) { slug = ''; }
  el.textContent = slug ? `/@${slug}` : '/@—';
}

// Handlers onclick des boutons "Changer la couverture" / "Changer l'avatar".
// On déclenche l'input file caché ; l'onchange câblé dans dashboard.html
// appellera dashIdentityHandle{Avatar,Cover}File() en retour.
function dashIdentityPickAvatar() {
  const f = document.getElementById('dashIdAvatarFile');
  if (f) f.click();
}
function dashIdentityPickCover() {
  const f = document.getElementById('dashIdCoverFile');
  if (f) f.click();
}

function dashIdentityHandleAvatarFile(ev) {
  const file = ev && ev.target && ev.target.files && ev.target.files[0];
  if (!file) return;
  _uploadDashIdImage(file, 'avatar');
  // Reset le input pour pouvoir resélectionner le même fichier
  ev.target.value = '';
}

function dashIdentityHandleCoverFile(ev) {
  const file = ev && ev.target && ev.target.files && ev.target.files[0];
  if (!file) return;
  _uploadDashIdImage(file, 'cover');
  ev.target.value = '';
}

// Upload vers /watt/upload-image (Flask), puis PATCH /users/me avec
// l'URL R2 renvoyée, puis refresh du preview + du localStorage.
async function _uploadDashIdImage(file, kind) {
  // Validation client (le backend re-valide)
  if (!/^image\//.test(file.type)) { dashToast('⚠ Ce fichier n\'est pas une image.'); return; }
  if (file.size > _DASH_ID_IMG_MAX) {
    dashToast(`⚠ Image trop lourde (${Math.round(file.size / 1024)} KB) — max 5 MB.`);
    return;
  }
  const u = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  if (!u || !u.id) { dashToast('⚠ Tu dois être connecté.'); return; }

  _setDashIdStatus(kind === 'avatar' ? 'Upload avatar…' : 'Upload couverture…', 'loading');

  const fd = new FormData();
  fd.append('file',   file);
  fd.append('userId', u.id);
  fd.append('kind',   kind);

  let uploadJson;
  try {
    const resp = await fetch('/watt/upload-image', { method: 'POST', body: fd });
    uploadJson = await resp.json().catch(() => ({}));
    if (!resp.ok || !uploadJson.url) {
      throw new Error(uploadJson.error || `Upload impossible (HTTP ${resp.status}).`);
    }
  } catch (err) {
    console.error('[dashboard] upload-image error', err);
    _setDashIdStatus('⚠ Upload impossible — réessaie.', 'error');
    return;
  }

  const url = uploadJson.url;
  const apiField = (kind === 'avatar') ? 'avatar_url' : 'cover_photo_url';
  try {
    if (typeof apiFetch === 'function') {
      await apiFetch('/users/me', { method: 'PATCH', json: { [apiField]: url } });
    }
  } catch (err) {
    console.warn('[dashboard] PATCH /users/me image échec :', err);
    _setDashIdStatus('⚠ Sauvegarde impossible — réessaie.', 'error');
    return;
  }

  // Sync localStorage + preview
  const p = getWattProfile() || {};
  if (kind === 'avatar') {
    saveWattProfile({ ...p, avatarUrl: url });
    _renderDashIdAvatarPreview(url);
  } else {
    saveWattProfile({ ...p, coverPhotoUrl: url });
    _renderDashIdCoverPreview(url);
  }
  _setDashIdStatus('✓ Image mise à jour.', 'ok');
  setTimeout(() => _setDashIdStatus('', ''), 2000);
}

function _setDashIdStatus(text, kind) {
  const el = document.getElementById('dashIdStatus');
  if (!el) return;
  el.textContent = text || '';
  el.className = 'dash-identity-status' + (kind ? ' is-' + kind : '');
}

// ══ LA FONCTION CENTRALE — "1 bouton unifié" ═══════════════════════════════
// Lit tous les inputs #dashId*, construit le payload PATCH /users/me, puis
// si profile_public=false, enchaîne automatiquement sur publishMyProfile()
// pour publier dans la foulée. Aucune friction pour l'user.
async function dashIdentitySave() {
  const getVal = (id) => {
    const el = document.getElementById(id);
    return el ? (el.value || '').trim() : '';
  };

  const artistName = getVal('dashIdName');
  if (!artistName) {
    _setDashIdStatus('⚠ Le nom d\'artiste est obligatoire.', 'error');
    dashToast('⚠ Le nom d\'artiste est obligatoire.');
    return;
  }

  // Helper : string vide → null (pour que Pydantic empty_string_to_none
  // propage bien "champ vidé" côté DB, sans dégrader les autres champs).
  const setField = (payload, key, val) => {
    payload[key] = (val === '' ? null : val);
  };

  // Couleurs : on normalise en #RRGGBB uppercase (regex Pydantic stricte)
  const normHex = (raw) => {
    const m = (raw || '').trim().match(/^#?([0-9a-f]{6})$/i);
    return m ? `#${m[1].toUpperCase()}` : null;
  };
  const bgColor    = normHex(getVal('dashIdBgColor'));
  const brandColor = normHex(getVal('dashIdBrandColor'));

  const payload = { artist_name: artistName };
  setField(payload, 'bio',         getVal('dashIdBio'));
  setField(payload, 'genre',       getVal('dashIdGenre'));
  setField(payload, 'city',        getVal('dashIdCity'));
  setField(payload, 'instagram',   getVal('dashIdSocialInstagram'));
  setField(payload, 'tiktok',      getVal('dashIdSocialTiktok'));
  setField(payload, 'youtube',     getVal('dashIdSocialYoutube'));
  setField(payload, 'spotify',     getVal('dashIdSocialSpotify'));
  setField(payload, 'soundcloud',  getVal('dashIdSocialSoundcloud'));

  // P0-F1 reliquat (2026-04-28) — Casquettes : on lit l'état stocké en
  // localStorage par dashIdentityToggleRole et on l'envoie au backend.
  // Liste vide [] = "aucune casquette" (valide). Liste alignée sur
  // ROLE_CODES backend, sinon Pydantic rejette avec "Rôle inconnu".
  const _profileForRoles = getWattProfile() || {};
  const _currentRoles    = Array.isArray(_profileForRoles.roles) ? _profileForRoles.roles : [];
  payload.roles = _currentRoles;
  // Defaults WATT (#070608 / #8800FF) → null côté DB (= "pas de perso, thème standard")
  payload.profile_bg_color    = (bgColor    === '#070608') ? null : bgColor;
  payload.profile_brand_color = (brandColor === '#8800FF') ? null : brandColor;
  // brand_color (carte hub) : on cale sur la couleur d'accent choisie
  if (brandColor) payload.brand_color = brandColor;

  const btn = document.getElementById('dashIdSaveBtn');
  if (btn) btn.disabled = true;
  _setDashIdStatus('Enregistrement…', 'loading');

  try {
    if (typeof apiFetch === 'function') {
      await apiFetch('/users/me', { method: 'PATCH', json: payload });
    }
  } catch (err) {
    console.error('[dashboard] PATCH /users/me échec :', err);
    if (btn) btn.disabled = false;
    _setDashIdStatus('⚠ Enregistrement impossible — réessaie.', 'error');
    dashToast('⚠ Enregistrement impossible — réessaie.');
    return;
  }

  // Sync localStorage — source partagée avec les autres blocs (hub card,
  // PLUG preview, artiste public).
  const p = getWattProfile() || {};
  saveWattProfile({
    ...p,
    artistName,
    bio:        payload.bio        || '',
    genre:      payload.genre      || '',
    city:       payload.city       || '',
    instagram:  payload.instagram  || '',
    tiktok:     payload.tiktok     || '',
    youtube:    payload.youtube    || '',
    spotify:    payload.spotify    || '',
    soundcloud: payload.soundcloud || '',
    brandColor: brandColor || p.brandColor || '',
    profileBgColor:    payload.profile_bg_color    || '',
    profileBrandColor: payload.profile_brand_color || '',
  });
  if (brandColor) { try { applyDashboardBrandColor(brandColor); } catch (_) {} }

  // P1-B3 (2026-04-22) — Plus de publish auto après save. Le switch PLUG
  // WATT (juste en-dessous du bouton Enregistrer) gère la publication de
  // manière explicite. Ce bouton fait UNIQUEMENT PATCH /users/me, ce qui
  // évite les saves involontaires qui re-publient un profil retiré.
  _setDashIdStatus('✓ Profil enregistré.', 'ok');
  dashToast('✓ Profil enregistré.');
  setTimeout(() => _setDashIdStatus('', ''), 2000);

  if (btn) btn.disabled = false;
  _updateDashIdSaveButton();
  _updateDashPlugSlugHint();
  // Re-render des autres blocs qui consomment le profil
  try { renderArtistCard(); }    catch (_) {}
  try { renderProfileView(); }   catch (_) {}
  try { renderPlugSection(); }   catch (_) {}
}

// Expose les handlers pour les onclick/onchange inline
if (typeof window !== 'undefined') {
  window.dashIdentitySave             = dashIdentitySave;
  window.dashIdentityPickAvatar       = dashIdentityPickAvatar;
  window.dashIdentityPickCover        = dashIdentityPickCover;
  window.dashIdentityHandleAvatarFile = dashIdentityHandleAvatarFile;
  window.dashIdentityHandleCoverFile  = dashIdentityHandleCoverFile;
}

// ── 8 ter. PLUG WATT (intégré dans la cellule 01 Identité depuis P1-B3) ─────
// Contrôle centralisé de la présence publique sur la marketplace, désormais
// fusionné dans la cellule Identité publique (voir P1-B3, 2026-04-22).
// Ingrédients :
//   • switch ON/OFF (sous le bouton Enregistrer de l'Identité) qui bascule
//     profile_public via publishMyProfile / unpublishMyProfile —
//     _dashPublishState reste la source unique de vérité.
//   • preview de la cellule marketplace (aside droit du formulaire Identité)
//     — permet de vérifier visuellement avant de basculer le switch.
//   • lien "Ouvrir ma boutique" → /u/<slug> (petit lien texte sous le switch).
// Les 3 compteurs (abonnés / écoutes / rang) ont été retirés : ils vivent
// désormais uniquement dans la cellule Analytique (2b) / Classement (2c).
// Écoute aussi smyle:profile-published / smyle:profile-unpublished émis par
// artiste.js (mise à jour croisée : si le user bascule depuis son profil,
// le dashboard se met à jour sans refresh).

function renderPlugSection() {
  const card = document.getElementById('dashPlugToggleCard');
  if (!card) return;

  const user    = getCurrentUser();
  const profile = getWattProfile();
  const isPublic = !!_dashPublishState.isPublic;
  const isLoading = !!_dashPublishState.loading;

  // ── Carte toggle ───────────────────────────────────────────────────────
  card.classList.toggle('is-on',  isPublic);
  card.classList.toggle('is-off', !isPublic);

  const titleEl = document.getElementById('dashPlugTitle');
  const subEl   = document.getElementById('dashPlugSub');
  if (titleEl) titleEl.textContent = isPublic ? 'Tu es visible sur la marketplace' : 'Mode brouillon';
  if (subEl)   subEl.textContent   = isPublic
    ? 'Les fans peuvent te trouver et s\'abonner.'
    : 'Active le switch pour apparaître dans la marketplace WATT.';

  // Switch natif
  const sw = document.getElementById('dashPlugSwitch');
  if (sw) {
    sw.checked  = isPublic;
    sw.disabled = isLoading;
  }

  // ── Preview de la cellule marketplace ─────────────────────────────────
  const cell = document.getElementById('dashPlugCell');
  if (cell) {
    const brand = (profile && profile.brandColor)
      || (user && user.brand_color)
      || '#8800ff';
    cell.style.setProperty('--brand', brand);
    cell.classList.toggle('is-public', isPublic);

    const name =
      (profile && profile.artistName) ||
      (user && user.artist_name) ||
      (user && user.name) ||
      (user && String(user.email || '').split('@')[0]) ||
      'Ton nom d\'artiste';

    const genre =
      (profile && profile.genre) ||
      (user && user.genre) ||
      'Ton genre musical';

    const avatarEl = document.getElementById('dashPlugCellAvatar');
    if (avatarEl) {
      const url = (profile && profile.avatarUrl) || (user && user.avatar_url) || '';
      if (url) {
        avatarEl.style.backgroundImage = `url("${String(url).replace(/"/g, '\\"')}")`;
        avatarEl.textContent = '';
      } else {
        avatarEl.style.backgroundImage = '';
        avatarEl.textContent = (name || '?').charAt(0).toUpperCase();
      }
    }
    const nameEl = document.getElementById('dashPlugCellName');
    if (nameEl) nameEl.textContent = name;
    const genreEl = document.getElementById('dashPlugCellGenre');
    if (genreEl) genreEl.textContent = genre;

    const chip = document.getElementById('dashPlugCellChip');
    if (chip) chip.textContent = isPublic ? 'En ligne' : 'Brouillon';

    const note = document.getElementById('dashPlugPreviewNote');
    if (note) {
      note.textContent = isPublic
        ? 'Ta cellule apparaît dans la grille de la marketplace WATT.'
        : 'Ton profil est en brouillon — personne ne peut encore le voir.';
    }
  }

  // ── Bouton "Ouvrir ma boutique" ────────────────────────────────────────
  const open = document.getElementById('dashPlugOpen');
  if (open) {
    const slug = _deriveArtistSlug(user, profile);
    if (slug) {
      open.href = `/@${encodeURIComponent(slug)}`;
      open.classList.remove('is-disabled');
    } else {
      open.href = '#';
      open.classList.add('is-disabled');
    }
  }

  // ── Compteurs : lus des mêmes sources que les stats cards ──────────────
  renderPlugStatsFromDom();
}

// P1-B3 (2026-04-22) — Les 3 compteurs (abonnés/écoutes/rang) qui vivaient
// dans l'ex-cellule 04 PLUG WATT dupliquaient les stat cards 2b / 2c. Ils
// ont été supprimés avec la section. Fonction laissée en no-op pour éviter
// de casser les call-sites existants (renderPlugSection, renderStats).
function renderPlugStatsFromDom() { /* no-op depuis P1-B3 */ }

// Handler du switch — on délègue aux endpoints déjà testés
// (publishMyProfile / unpublishMyProfile), avec petit garde-fou :
// on rollback visuellement la checkbox si l'appel échoue.
async function dashPlugToggle(wantPublic) {
  const sw = document.getElementById('dashPlugSwitch');
  if (!sw) return;
  // Si une opération est déjà en cours on annule (sw remis tel quel par renderPlugSection).
  if (_dashPublishState.loading) {
    sw.checked = !!_dashPublishState.isPublic;
    return;
  }

  if (wantPublic) {
    await publishMyProfile();
  } else {
    await unpublishMyProfile();
  }

  // publishMyProfile / unpublishMyProfile appellent renderPublishBlock() —
  // on complète en re-rendant notre section aussi (source de vérité unique :
  // _dashPublishState, déjà mis à jour par les deux fonctions).
  renderPlugSection();
}

function dashPlugOpenShop(ev) {
  if (ev) ev.preventDefault();
  const user    = getCurrentUser();
  const profile = getWattProfile();
  const slug = _deriveArtistSlug(user, profile);
  if (!slug) {
    dashToast('Choisis d\'abord un nom d\'artiste pour ouvrir ta boutique.');
    return false;
  }
  // Ouvre dans un nouvel onglet : l'user garde le WATT BOARD ouvert pour
  // revenir facilement à ses réglages après inspection de sa vitrine.
  window.open(`/@${encodeURIComponent(slug)}`, '_blank', 'noopener');
  return false;
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
  const profile    = getWattProfile();

  setTextById('statsPlays',     totalPlays.toString());
  setTextById('statsTracks',    tracks.length.toString());
  setTextById('statsFollowers', profile ? (profile.followers || 0).toString() : '0');
  // statsRank est mis à jour de façon asynchrone par renderRanking()
  // (utilise le vrai classement API /watt/artists, pas un mock)

  renderChart(_currentPeriod);
}

async function renderChart(period) {
  // Vraies stats (2026-06-10) — données réelles play_events, plus de mock.
  const data    = await fetchPlaysHistory(period);
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

async function renderRanking() {
  const listEl = document.getElementById('dashRankingList');
  if (listEl) listEl.innerHTML = '<div class="dash-rank-empty">Chargement du classement…</div>';

  const ranking = await fetchRealRanking();
  const myPos   = ranking.findIndex(a => a.isMe) + 1;

  // Ma position (mise à jour ici car fetchRealRanking est async)
  const rankLabel = myPos > 0 ? `#${myPos}` : '—';
  setTextById('mrcRank',   rankLabel);
  setTextById('statsRank', rankLabel);

  // Liste
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
}

// ── 11. SECTION NAV INTERSECTION OBSERVER ────────────────────────────────────

function initSectionNav() {
  const pills = document.querySelectorAll('.dash-snav-pill');
  // Depuis la restructure à 2 pills, les sous-sections (sec-dna, sec-ranking)
  // sont marquées .dash-section-sub et ne doivent PAS piloter la nav — leurs
  // parents logiques (sec-upload / sec-stats) gardent la main. On exclut donc
  // les sous-sections de l'observer, sinon le pill actif clignoterait pendant
  // le scroll au passage d'un sous-bloc.
  const sections = document.querySelectorAll('.dash-section:not(.dash-section-sub)');

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

/* ── Suppression de compte RGPD (pack légal v1, 2026-06-10) ──────────────
   Double confirmation : l'utilisateur doit taper SUPPRIMER. Appelle
   DELETE /users/me (anonymisation backend), puis purge la session locale
   et renvoie à l'accueil. */
async function dashDeleteAccount() {
  const typed = window.prompt(
    'Cette action est DÉFINITIVE.\n\n' +
    'Ton profil sera anonymisé et tes contenus retirés du public. ' +
    'Les exemplaires déjà achetés par d\'autres restent dans leur bibliothèque.\n\n' +
    'Pour confirmer, tape exactement : SUPPRIMER'
  );
  if (typed === null) return;                    // annulé
  if (typed.trim() !== 'SUPPRIMER') {
    dashToast('Suppression annulée — le texte ne correspond pas.');
    return;
  }
  try {
    await apiFetch('/users/me', { method: 'DELETE' });
  } catch (e) {
    dashToast('⚠ Échec de la suppression : ' + _humanizeApiError(e));
    return;
  }
  // Purge locale complète puis retour accueil (le JWT est déjà invalide
  // côté serveur : l'email anonymisé ne résout plus aucun token).
  try { if (typeof clearAuthToken === 'function') clearAuthToken(); } catch (_) {}
  try { clearCurrentUser(); } catch (_) {}
  try { safeStorage.removeItem('smyle_watt_profile'); } catch (_) {}
  try { safeStorage.removeItem('smyle_watt_tracks'); } catch (_) {}
  window.location.href = '/';
}

function dashLogout() {
  clearCurrentUser();
  // Vide le JWT (localStorage, partagé entre onglets) et notifie les autres composants
  if (typeof clearAuthToken === 'function') clearAuthToken();
  if (window.SmyleEvents) SmyleEvents.emit('smyle:auth-changed', { loggedIn: false });
  window.location.href = '/';
}

// ── 12b. COPIE LIEN PROFIL PUBLIC ─────────────────────────────────────────────

function copyPublicProfileLink(urlPath) {
  const full = window.location.origin + urlPath;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(full).then(() => dashToast('✓ Lien copié !')).catch(() => _fbCopy(full));
  } else { _fbCopy(full); }
}
function _fbCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
  document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); dashToast('✓ Lien copié !'); } catch(e) {}
  document.body.removeChild(ta);
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

// P1-B11 (2026-04-29) — Helper de parsing des erreurs API.
//
// FastAPI/Pydantic peut renvoyer e.body.detail sous 3 formes :
//   1. string         → ex 404 "ADN not found"
//   2. array d'objets → ex 422 [{"loc":[...], "msg":"...", "type":"..."}]
//   3. objet          → ex 403 { code, message }
//
// Avant ce helper, le code faisait `${e.body.detail}` ce qui transformait
// les array/objets en "[object Object]" — message inutilisable côté user.
// Maintenant, on extrait un message lisible quel que soit le format, avec
// fallback `e.message` puis "erreur inconnue".
//
// Exposé globalement parce qu'on l'utilise dans plusieurs endroits du
// dashboard (publication prompt, ADN, voix, profil).
function _humanizeApiError(e) {
  if (!e) return 'erreur inconnue';
  const detail = e.body && e.body.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail) && detail.length > 0) {
    // Pydantic validation errors : on concatène les messages humains
    return detail
      .map((it) => {
        if (it && typeof it === 'object') {
          const loc = Array.isArray(it.loc) ? it.loc.filter((x) => x !== 'body').join('.') : '';
          const msg = it.msg || it.message || JSON.stringify(it);
          return loc ? `${loc} — ${msg}` : msg;
        }
        return String(it);
      })
      .join(' · ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.error || detail.msg || JSON.stringify(detail);
  }
  if (e.message && typeof e.message === 'string') {
    return e.message;
  }
  return 'erreur inconnue';
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
  renderMyTracks();   // initialise compteur freemium + état zone upload
  initTrackEditor();  // cellule édition catalogue (section 1a)

  // Section nav
  initSectionNav();

  // Chantier "1 bouton unifié" — hydrate les inputs de la section Identité
  // depuis le localStorage (rapide, pas d'attente réseau). loadPublishStatus()
  // ré-hydrate plus tard avec les données DB fraîches.
  try { initDashIdentity(); } catch (e) { console.warn('[dashboard] initDashIdentity error', e); }
  try { initDashVoiceSale(); } catch (e) { console.warn('[dashboard] initDashVoiceSale error', e); }

  // Chantier 1 — charge le statut profile_public depuis /users/me
  // pour afficher le bon état du bloc "Publier mon profil".
  loadPublishStatus();

  // Render initial de la pill PLUG WATT (preview + switch off). Les stats
  // exactes arrivent quand renderStats() finit son fetch ; on rendort juste
  // après pour capter les valeurs fraîches dans statsPlays/statsFollowers/
  // statsRank. On évite un fetch dédié — le dashboard a déjà toutes les
  // sources de vérité nécessaires.
  renderPlugSection();
  setTimeout(renderPlugStatsFromDom, 1200);

  // Bus d'events — si l'user bascule profile_public depuis /u/<slug>
  // (mode owner), le dashboard doit se mettre à jour sans refresh.
  if (window.SmyleEvents) {
    window.SmyleEvents.on(window.SmyleEvents.TYPES.PROFILE_PUBLISHED, (payload) => {
      _dashPublishState.isPublic = true;
      _dashPublishState.loaded   = true;
      if (payload && payload.artist) {
        // Synchronise le profil local pour que renderPlugSection ait les
        // bons nom / genre / brand à afficher dans la preview.
        const p = getWattProfile() || {};
        saveWattProfile({
          ...p,
          artistName: payload.artist.artistName || p.artistName || '',
          genre:      payload.artist.genre      || p.genre      || '',
          brandColor: payload.artist.brandColor || p.brandColor || '',
          avatarUrl:  payload.artist.avatarUrl  || p.avatarUrl  || '',
        });
      }
      renderPublishBlock();
      renderCreationGate();
      renderPlugSection();
      try { _updateDashIdSaveButton(); } catch (_) {}
      try { _updateDashPlugSlugHint(); } catch (_) {}
    });

    window.SmyleEvents.on(window.SmyleEvents.TYPES.PROFILE_UNPUBLISHED, () => {
      _dashPublishState.isPublic = false;
      _dashPublishState.loaded   = true;
      renderPublishBlock();
      renderCreationGate();
      renderPlugSection();
      try { _updateDashIdSaveButton(); } catch (_) {}
      try { _updateDashPlugSlugHint(); } catch (_) {}
    });
  }

  // Expose les handlers pour le onclick inline de dashboard.html
  if (typeof window !== 'undefined') {
    window.dashPlugToggle  = dashPlugToggle;
    window.dashPlugOpenShop = dashPlugOpenShop;
  }

  // Bulle profil (dropdown topbar) — toggle + handlers fermeture
  _initUserDropdown();

  // Chantier 1.2 — init du color picker + application de la brand courante
  _initBrandPicker();
  const _p0 = getWattProfile();
  if (_p0 && _p0.brandColor) applyDashboardBrandColor(_p0.brandColor);

  // Étape 2 — init du picker "couleur du morceau" (mode hériter par défaut).
  // On pose la pastille d'héritage à la brandColor courante.
  try { resetTrackColor(); } catch (_) { /* noop — widget caché ou absent */ }

  // Étape 1 (itération) — quand la gate est active, le dashUploadLayout
  // reste visible mais dégradé (is-gated). On intercepte tout clic en
  // capture pour préempter les onclick inline (dropzone, mode pills…) et
  // rappeler la banner pédagogique au lieu d'ouvrir le file picker.
  const _gatedLayout = document.getElementById('dashUploadLayout');
  if (_gatedLayout) {
    _gatedLayout.addEventListener('click', (ev) => {
      if (_gatedLayout.classList.contains('is-gated')) {
        handleGatedLayoutClick(ev);
      }
    }, true);
  }

  // Resize observer pour le canvas réseau
  if (window.ResizeObserver && netCanvas) {
    new ResizeObserver(() => {
      // Le canvas se redimensionne dans DashNetwork.resize()
    }).observe(netCanvas.parentElement);
  }

  // Chantier "Création DNA" — charge l'ADN existant si présent pour
  // pré-remplir la section #sec-dna (empty / summary / editor).
  loadMyAdn();

  // ADN Visuel (signature visuelle artiste) — charge l'ADN visuel existant
  // pour pré-remplir la section #sec-visual-adn (empty / summary / editor).
  if (typeof loadMyVisualAdn === 'function') loadMyVisualAdn();

  // Si la page artiste a redirigé avec ?edit=1, scroller vers la section
  // Identité et l'ouvrir (c'est un <details> accordéon).
  if (new URLSearchParams(window.location.search).get('edit') === '1') {
    const secId = document.getElementById('sec-identity');
    if (secId) {
      const det = secId.querySelector('details');
      if (det) det.open = true;
      setTimeout(() => secId.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
    }
  }

  // Section échanges — chargement initial + scroll auto si #trades dans l'URL
  loadTrades();
  loadTrophees();
  if (location.hash === '#trades' || location.hash === '#sec-trades') {
    setTimeout(() => {
      const sec = document.getElementById('sec-trades');
      if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 200);
  }
  if (location.hash === '#trophees' || location.hash === '#sec-trophees') {
    setTimeout(() => {
      const sec = document.getElementById('sec-trophees');
      if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 200);
  }

  // ── Deep-link depuis la cellule WATT BOARD (marketplace) ──────────────────
  // Les entrées Dashboard / Upload / Profil / Mes Sons / Statistiques du
  // panneau pointent désormais vers les vraies ancres (#sec-upload, …). On
  // tolère aussi les anciennes ancres (#upload, #profile, #tracks, #stats)
  // par sécurité, et on ouvre l'accordéon Identité s'il est la cible.
  (function _wattBoardDeepLink() {
    const raw = (location.hash || '').slice(1);
    if (!raw) return;
    const ALIAS = {
      upload:  'sec-upload',
      profile: 'sec-identity',
      profil:  'sec-identity',
      tracks:  'myTracksList',
      stats:   'sec-stats',
    };
    const targetId = ALIAS[raw] || raw;
    const el = document.getElementById(targetId);
    if (!el) return;
    // Identité est un <details> accordéon : on l'ouvre avant de scroller.
    if (targetId === 'sec-identity') {
      const det = el.querySelector('details');
      if (det) det.open = true;
    }
    setTimeout(
      () => el.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      250,
    );
  })();

  // ── Ouverture de l'éditeur "Modifier le son" via ?edit-track=<id> ─────────
  // Déclenché par un clic sur un son dans la cellule WATT BOARD (marketplace).
  // La liste des sons se charge en async → on réessaie quelques fois.
  (function _openTrackEditFromUrl() {
    const editId = new URLSearchParams(window.location.search).get('edit-track');
    if (!editId) return;
    let tries = 0;
    const tryOpen = () => {
      tries++;
      const tracks = (typeof getMyTracks === 'function') ? getMyTracks() : [];
      const found = tracks.find(x => x.id === editId || x.dbId === editId);
      if (found && typeof openTrackEdit === 'function') {
        openTrackEdit(found.id);
        return;
      }
      if (tries < 15) setTimeout(tryOpen, 300); // ~4,5s max le temps du sync
    };
    setTimeout(tryOpen, 400);
  })();
});

/* ═══════════════════════════════════════════════════════════════════════════
   CHANTIER "CRÉATION ADN" (BLOC 2-bis WATT BOARD)
   ═══════════════════════════════════════════════════════════════════════════

   Gère la section #sec-dna : création + édition + publication de l'ADN
   signature de l'artiste. Endpoints (cf. routers/marketplace.py) :
     GET   /artist/me/adn   → 200 AdnRead | 404 si pas d'ADN
     POST  /artist/me/adn   → 201 AdnRead (création, 1 max)
     PATCH /artist/me/adn   → 200 AdnRead (édition)
   Limites Pydantic :
     description        200..5000 chars
     usage_guide        ≤ 3000 chars optionnel
     example_outputs    ≤ 5000 chars optionnel
     price_credits      30..500
   Lock métier : après la 1ère vente (owned_adns), description devient
   immutable. Le service renvoie 409 ContentLockedAfterSale qu'on traduit
   en message utilisateur. Prix + is_published + autres champs restent
   éditables même après ventes.                                              */

// État local — source de vérité de la section ADN (hors formulaire en édition)
const _adnState = {
  adn: null,          // AdnRead renvoyé par l'API, ou null si pas encore créé
  saving: false,      // protège les doubles clics
};

async function loadMyAdn() {
  if (typeof apiFetch !== 'function') return;
  try {
    const adn = await apiFetch('/artist/me/adn');
    _adnState.adn = adn || null;
  } catch (err) {
    // 404 = pas d'ADN → état "empty" normal. On log juste les autres.
    if (!err || err.status !== 404) {
      console.warn('[dashboard] loadMyAdn error', err);
    }
    _adnState.adn = null;
  }
  renderAdnSection();
}

// Bascule empty/summary en fonction de _adnState.adn, met à jour les textes.
function renderAdnSection() {
  const empty   = document.getElementById('dashAdnEmpty');
  const summary = document.getElementById('dashAdnSummary');
  if (!empty || !summary) return;

  if (!_adnState.adn) {
    empty.style.display   = '';
    summary.style.display = 'none';
    return;
  }

  const adn = _adnState.adn;
  empty.style.display   = 'none';
  summary.style.display = '';

  // Status chip — le cercle coloré est ajouté via CSS ::before
  // selon l'attribut data-status ("published" | "draft").
  const status = document.getElementById('dashAdnStatus');
  if (status) {
    status.textContent = adn.is_published ? 'Publié' : 'Brouillon';
    status.setAttribute('data-status', adn.is_published ? 'published' : 'draft');
  }

  // Prix
  const priceVal = document.getElementById('dashAdnPriceVal');
  if (priceVal) priceVal.textContent = String(adn.price_credits || 0);

  // Description preview (180 chars, ellipsis)
  const descPreview = document.getElementById('dashAdnDescPreview');
  if (descPreview) {
    const full = adn.description || '';
    descPreview.textContent = full.length > 180
      ? full.slice(0, 180).trimEnd() + '…'
      : full;
  }

  // Badges meta
  const meta = document.getElementById('dashAdnSummaryMeta');
  if (meta) {
    meta.innerHTML = '';
    if (adn.usage_guide) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="dash-adn-summary-badge">📘 Guide d\'usage</span>');
    }
    if (adn.example_outputs) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="dash-adn-summary-badge">🎧 Exemples</span>');
    }
  }

  // Toggle publish button label
  const togBtn = document.getElementById('dashAdnTogglePublishBtn');
  if (togBtn) {
    togBtn.textContent = adn.is_published ? 'Dépublier' : 'Publier';
    togBtn.classList.toggle('dash-btn-secondary', !!adn.is_published);
    togBtn.classList.toggle('dash-btn-primary',   !adn.is_published);
  }

  // Note de lock description — on ne peut pas savoir côté front s'il y a
  // eu une vente sans faire un call dédié ; on s'appuie donc uniquement
  // sur la réponse 409 pendant le save pour afficher la bonne erreur.
  // (Si on voulait l'afficher proactivement il faudrait un flag côté API.)
}

function openAdnEditor() {
  const editor = document.getElementById('dashAdnEditor');
  if (!editor) return;

  // Pré-remplit les champs si l'ADN existe déjà
  const adn = _adnState.adn;
  const title = document.getElementById('dashAdnEditorTitle');
  if (title) title.textContent = adn ? 'Modifier mon ADN' : 'Créer mon ADN';

  document.getElementById('dashAdnDescription').value     = adn ? (adn.description || '') : '';
  document.getElementById('dashAdnUsageGuide').value      = adn ? (adn.usage_guide || '') : '';
  document.getElementById('dashAdnExampleOutputs').value  = adn ? (adn.example_outputs || '') : '';
  document.getElementById('dashAdnPrice').value           = adn ? String(adn.price_credits) : '80';
  // 2026-05-13 v2 — préselection IA + éditions (1 seul input libre)
  const aiSel = document.getElementById('dashAdnAiReference');
  if (aiSel) aiSel.value = (adn && adn.ai_reference) ? adn.ai_reference : '';
  const supInp = document.getElementById('dashAdnMaxSupply');
  if (supInp) {
    supInp.value = (adn && adn.max_supply) ? String(adn.max_supply) : '';
  }
  if (typeof dashAdnUpdateRarityPreview === 'function') dashAdnUpdateRarityPreview();

  editor.style.display = '';
  editor.scrollIntoView({ behavior: 'smooth', block: 'center' });
  const desc = document.getElementById('dashAdnDescription');
  if (desc) setTimeout(() => desc.focus(), 100);
}

function closeAdnEditor() {
  const editor = document.getElementById('dashAdnEditor');
  if (editor) editor.style.display = 'none';
}

// 2026-05-13 v2 — Live preview du tier de rareté pendant la saisie.
// Mirror exact de compute_rarity_tier() côté backend pour cohérence.
function dashAdnUpdateRarityPreview() {
  const inp = document.getElementById('dashAdnMaxSupply');
  const out = document.getElementById('dashAdnRarityPreview');
  if (!inp || !out) return;
  const raw = (inp.value || '').trim();
  if (raw === '') {
    out.innerHTML = '<span style="color:#a09cb8;">Édition illimitée (pas de rareté affichée)</span>';
    return;
  }
  const n = parseInt(raw, 10);
  if (!Number.isInteger(n) || n < 1) {
    out.innerHTML = '<span style="color:#f87171;">Nombre invalide</span>';
    return;
  }
  // Pas de plafond ressenti — INT32 PostgreSQL couvre tout.
  let tier, emoji, label, color;
  if (n === 1)        { tier='Mythic';    emoji='👑'; label='Pièce unique (1/1)';     color='#FFD700'; }
  else if (n <= 10)   { tier='Legendary'; emoji='⭐'; label=`Drop VIP (${n} exemplaires)`; color='#FBBF24'; }
  else if (n <= 10000) { tier='Limited';  emoji='💎'; label=`Édition limitée (${n} exemplaires)`; color='#A78BFA'; }
  else                { tier='Open';      emoji='🟢'; label=`Édition ouverte (${n} exemplaires)`; color='#4ADE80'; }
  out.innerHTML = `<span style="color:${color};">${emoji} <strong>${tier}</strong> — ${label}</span>`;
}

// Preview live de la rareté d'un PROMPT (miroir de compute_rarity_tier backend).
function dashPromptUpdateRarityPreview() {
  const inp = document.getElementById('dashPromptMaxSupply');
  const out = document.getElementById('dashPromptRarityPreview');
  if (!inp || !out) return;
  const raw = (inp.value || '').trim();
  if (raw === '') {
    out.innerHTML = '<span style="color:#a09cb8;">Édition illimitée (pas de badge de rareté)</span>';
    return;
  }
  const n = parseInt(raw, 10);
  if (!Number.isInteger(n) || n < 1) {
    out.innerHTML = '<span style="color:#f87171;">Nombre invalide</span>';
    return;
  }
  let tier, emoji, label, color;
  if (n === 1)         { tier='Mythic';    emoji='👑'; label='Pièce unique (1/1)';            color='#FFD700'; }
  else if (n <= 10)    { tier='Legendary'; emoji='⭐'; label=`Drop VIP (${n} exemplaires)`;   color='#FBBF24'; }
  else if (n <= 10000) { tier='Limited';   emoji='💎'; label=`Édition limitée (${n} ex.)`;    color='#A78BFA'; }
  else                 { tier='Open';      emoji='🟢'; label=`Édition ouverte (${n} ex.)`;    color='#4ADE80'; }
  out.innerHTML = `<span style="color:${color};">${emoji} <strong>${tier}</strong> — ${label}</span>`;
}

async function saveAdn() {
  if (_adnState.saving) return;
  if (typeof apiFetch !== 'function') return;

  const description    = (document.getElementById('dashAdnDescription').value || '').trim();
  const usageGuide     = (document.getElementById('dashAdnUsageGuide').value || '').trim();
  const exampleOutputs = (document.getElementById('dashAdnExampleOutputs').value || '').trim();
  const priceRaw       = document.getElementById('dashAdnPrice').value;
  const priceCredits   = parseInt(priceRaw, 10);

  // Validations client miroir Pydantic (feedback rapide avant 422)
  if (description.length < 200) {
    _dashToast(`Description trop courte (${description.length}/200 chars min).`);
    return;
  }
  if (description.length > 5000) {
    _dashToast('Description trop longue (5000 chars max).');
    return;
  }
  if (!Number.isInteger(priceCredits) || priceCredits < 30) {
    _dashToast('Prix invalide — minimum 30 crédits.');
    return;
  }

  // 2026-05-13 v2 — Rareté simplifiée : 1 seul input libre, tier auto.
  const aiRef = (document.getElementById('dashAdnAiReference')||{}).value || '';
  const supRaw = (document.getElementById('dashAdnMaxSupply')||{}).value || '';
  let maxSupplyVal = null;
  if (supRaw.trim() !== '') {
    const n = parseInt(supRaw, 10);
    if (!Number.isInteger(n) || n < 1) {
      _dashToast('Éditions : nombre invalide. Tape un entier positif ou laisse vide pour illimité.');
      return;
    }
    maxSupplyVal = n;
  }

  const payload = {
    description,
    price_credits: priceCredits,
  };
  // On n'envoie usage_guide/example_outputs que si remplis
  // (évite d'effacer par inadvertance côté PATCH partiel).
  if (usageGuide)     payload.usage_guide     = usageGuide;
  if (exampleOutputs) payload.example_outputs = exampleOutputs;
  if (aiRef)          payload.ai_reference    = aiRef;
  if (maxSupplyVal !== null) payload.max_supply = maxSupplyVal;
  // OFFRES-ADN étape 5 : plancher caché (write-only) — n'envoie que si saisi.
  const reserveRawM = ((document.getElementById('dashAdnReserve')||{}).value || '').trim();
  if (reserveRawM !== '') {
    const rv = parseInt(reserveRawM, 10);
    if (!isNaN(rv) && rv >= 0) payload.adn_reserve_credits = rv;
  }

  const isCreate = !_adnState.adn;
  const method   = isCreate ? 'POST' : 'PATCH';

  _adnState.saving = true;
  try {
    const adn = await apiFetch('/artist/me/adn', {
      method,
      json: payload,
    });
    _adnState.adn = adn;
    renderAdnSection();
    closeAdnEditor();
    _dashToast(isCreate ? 'ADN créé · prêt à publier' : 'ADN mis à jour');
  } catch (err) {
    console.error('[dashboard] saveAdn error', err);
    _handleAdnError(err);
  } finally {
    _adnState.saving = false;
  }
}

async function toggleAdnPublish() {
  if (_adnState.saving) return;
  if (typeof apiFetch !== 'function') return;

  // P1-B12 (2026-04-29) — Avant ce fix, cette fonction était silencieuse si
  // _adnState.adn était null (cas où l'utilisateur croit voir un ADN dans le
  // dashboard mais en DB il n'y a rien). Tom passait donc 30 min à cliquer
  // sans rien comprendre. On affiche maintenant un message explicite + on
  // refetch côté DB pour resynchroniser au cas où le cache local mente.
  if (!_adnState.adn) {
    dashToast('⚠ Aucun ADN en base. Crée-le d\'abord en remplissant le formulaire ci-dessous puis Sauvegarder.');
    // Tentative de re-sync : si l'ADN existe en DB mais n'avait pas été
    // chargé (race condition au boot), on le récupère et on retente.
    try { await loadMyAdn(); } catch (_) {}
    if (!_adnState.adn) return;
  }

  const nextState = !_adnState.adn.is_published;
  _adnState.saving = true;
  try {
    const adn = await apiFetch('/artist/me/adn', {
      method: 'PATCH',
      json:   { is_published: nextState },
    });
    _adnState.adn = adn;
    renderAdnSection();
    dashToast(nextState
      ? 'ADN publié — visible sur ton profil 🎉'
      : 'ADN dépublié — invisible pour les fans');
  } catch (err) {
    console.error('[dashboard] toggleAdnPublish error', err);
    dashToast(`⚠ Bascule publication impossible : ${_humanizeApiError(err)}`);
  } finally {
    _adnState.saving = false;
  }
}

function _handleAdnError(err) {
  if (!err) {
    _dashToast('Erreur inconnue — réessaie.');
    return;
  }
  const detail = err.body && err.body.detail;
  if (err.status === 409) {
    if (typeof detail === 'string' && detail.toLowerCase().includes('lock')) {
      _dashToast('Description verrouillée — un acheteur l\'a déjà acquise.');
    } else if (typeof detail === 'string' && detail.toLowerCase().includes('already')) {
      _dashToast('Tu as déjà un ADN — modifie-le plutôt que d\'en créer un nouveau.');
      // Recharger pour re-synchroniser l'UI
      loadMyAdn();
    } else {
      _dashToast(typeof detail === 'string' ? detail : 'Conflit — réessaie.');
    }
    return;
  }
  if (err.status === 422) {
    // Pydantic validation — on extrait le 1er message si possible
    if (Array.isArray(detail) && detail.length && detail[0].msg) {
      _dashToast(`Validation : ${detail[0].msg}`);
    } else {
      _dashToast('Données invalides — vérifie les champs.');
    }
    return;
  }
  if (err.status === 401) {
    _dashToast('Session expirée — reconnecte-toi.');
    return;
  }
  _dashToast('Enregistrement impossible — réessaie.');
}

// Toast avec fallback : utilise le toast global s'il existe, sinon alerte
function _dashToast(msg) {
  if (typeof toast === 'function') return toast(msg);
  if (typeof showToast === 'function') return showToast(msg);
  const el = document.getElementById('dash-toast');
  if (el) {
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 2400);
    return;
  }
  console.log('[dashboard]', msg);
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADN VISUEL (signature visuelle artiste) — section #sec-visual-adn
   ═══════════════════════════════════════════════════════════════════════════
   Mirror EXACT de l'ADN musical ci-dessus. Endpoints (marketplace.py) :
     GET   /artist/me/visual-adn   → 200 VisualAdnRead | 404 si pas d'ADN
     POST  /artist/me/visual-adn   → 201 (création, 1 max → 409)
     PATCH /artist/me/visual-adn   → 200 (édition ; description figée après vente)
     DELETE /artist/me/visual-adn  → 204 (acheteurs gardent leur accès)
   Spécifique visuel : champs `style` (16 codes) + `palette` (génome, gaté).
   Bornes : description 200..5000, price_credits 30..500.                       */

const _visualAdnState = {
  adn: null,
  saving: false,
};

async function loadMyVisualAdn() {
  if (typeof apiFetch !== 'function') return;
  try {
    const adn = await apiFetch('/artist/me/visual-adn');
    _visualAdnState.adn = adn || null;
  } catch (err) {
    if (!err || err.status !== 404) {
      console.warn('[dashboard] loadMyVisualAdn error', err);
    }
    _visualAdnState.adn = null;
  }
  renderVisualAdnSection();
}

function renderVisualAdnSection() {
  const empty   = document.getElementById('dashVisualAdnEmpty');
  const summary = document.getElementById('dashVisualAdnSummary');
  if (!empty || !summary) return;

  if (!_visualAdnState.adn) {
    empty.style.display   = '';
    summary.style.display = 'none';
    return;
  }

  const adn = _visualAdnState.adn;
  empty.style.display   = 'none';
  summary.style.display = '';

  const status = document.getElementById('dashVisualAdnStatus');
  if (status) {
    status.textContent = adn.is_published ? 'Publié' : 'Brouillon';
    status.setAttribute('data-status', adn.is_published ? 'published' : 'draft');
  }

  const priceVal = document.getElementById('dashVisualAdnPriceVal');
  if (priceVal) priceVal.textContent = String(adn.price_credits || 0);

  const descPreview = document.getElementById('dashVisualAdnDescPreview');
  if (descPreview) {
    const full = adn.description || '';
    descPreview.textContent = full.length > 180
      ? full.slice(0, 180).trimEnd() + '…'
      : full;
  }

  const meta = document.getElementById('dashVisualAdnSummaryMeta');
  if (meta) {
    meta.innerHTML = '';
    if (adn.style) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="dash-adn-summary-badge">🎨 ' + _visualAdnStyleLabel(adn.style) + '</span>');
    }
    if (adn.palette) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="dash-adn-summary-badge">🎨 Palette</span>');
    }
    if (adn.usage_guide) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="dash-adn-summary-badge">📘 Guide d\'usage</span>');
    }
    if (adn.example_outputs) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="dash-adn-summary-badge">🖼️ Exemples</span>');
    }
  }

  const togBtn = document.getElementById('dashVisualAdnTogglePublishBtn');
  if (togBtn) {
    togBtn.textContent = adn.is_published ? 'Dépublier' : 'Publier';
    togBtn.classList.toggle('dash-btn-secondary', !!adn.is_published);
    togBtn.classList.toggle('dash-btn-primary',   !adn.is_published);
  }
}

// Libellés FR des 16 codes de style (mirror de la liste backend).
const _VISUAL_ADN_STYLE_LABELS = {
  realiste: 'Réaliste', cartoon: 'Cartoon', anime: 'Anime', '3d': '3D / Render',
  peinture: 'Peinture', aquarelle: 'Aquarelle', croquis: 'Croquis',
  pixel_art: 'Pixel art', cyberpunk: 'Cyberpunk', fantasy: 'Fantasy',
  minimaliste: 'Minimaliste', retro: 'Rétro', abstrait: 'Abstrait',
  surrealiste: 'Surréaliste', comics: 'Comics', photo: 'Photo',
};
function _visualAdnStyleLabel(code) {
  return _VISUAL_ADN_STYLE_LABELS[code] || code;
}

function openVisualAdnEditor() {
  const editor = document.getElementById('dashVisualAdnEditor');
  if (!editor) return;

  const adn = _visualAdnState.adn;
  const title = document.getElementById('dashVisualAdnEditorTitle');
  if (title) title.textContent = adn ? 'Modifier mon ADN visuel' : 'Créer mon ADN visuel';

  document.getElementById('dashVisualAdnDescription').value    = adn ? (adn.description || '') : '';
  document.getElementById('dashVisualAdnUsageGuide').value     = adn ? (adn.usage_guide || '') : '';
  document.getElementById('dashVisualAdnExampleOutputs').value = adn ? (adn.example_outputs || '') : '';
  document.getElementById('dashVisualAdnPrice').value          = adn ? String(adn.price_credits) : '80';
  const styleSel = document.getElementById('dashVisualAdnStyle');
  if (styleSel) styleSel.value = (adn && adn.style) ? adn.style : '';
  const paletteInp = document.getElementById('dashVisualAdnPalette');
  if (paletteInp) paletteInp.value = (adn && adn.palette) ? adn.palette : '';
  const aiSel = document.getElementById('dashVisualAdnAiReference');
  if (aiSel) aiSel.value = (adn && adn.ai_reference) ? adn.ai_reference : '';
  const supInp = document.getElementById('dashVisualAdnMaxSupply');
  if (supInp) supInp.value = (adn && adn.max_supply) ? String(adn.max_supply) : '';

  // Lock description après vente : on ne le connaît qu'après une 409 au save.
  // Par défaut on déverrouille (le 409 réactivera le verrou + la note).
  const descEl = document.getElementById('dashVisualAdnDescription');
  if (descEl) descEl.disabled = false;

  if (typeof dashVisualAdnUpdateRarityPreview === 'function') dashVisualAdnUpdateRarityPreview();
  if (typeof dashUpdateEurPreview === 'function') dashUpdateEurPreview('dashVisualAdnPrice', 'dashVisualAdnPriceEur');

  editor.style.display = '';
  editor.scrollIntoView({ behavior: 'smooth', block: 'center' });
  if (descEl) setTimeout(() => descEl.focus(), 100);
}

function closeVisualAdnEditor() {
  const editor = document.getElementById('dashVisualAdnEditor');
  if (editor) editor.style.display = 'none';
}

function dashVisualAdnUpdateRarityPreview() {
  const inp = document.getElementById('dashVisualAdnMaxSupply');
  const out = document.getElementById('dashVisualAdnRarityPreview');
  if (!inp || !out) return;
  const raw = (inp.value || '').trim();
  if (raw === '') {
    out.innerHTML = '<span style="color:#a09cb8;">Édition illimitée (pas de rareté affichée)</span>';
    return;
  }
  const n = parseInt(raw, 10);
  if (!Number.isInteger(n) || n < 1) {
    out.innerHTML = '<span style="color:#f87171;">Nombre invalide</span>';
    return;
  }
  let tier, emoji, label, color;
  if (n === 1)         { tier='Mythic';    emoji='👑'; label='Pièce unique (1/1)';                  color='#FFD700'; }
  else if (n <= 10)    { tier='Legendary'; emoji='⭐'; label=`Drop VIP (${n} exemplaires)`;          color='#FBBF24'; }
  else if (n <= 10000) { tier='Limited';   emoji='💎'; label=`Édition limitée (${n} exemplaires)`;   color='#A78BFA'; }
  else                 { tier='Open';      emoji='🟢'; label=`Édition ouverte (${n} exemplaires)`;   color='#4ADE80'; }
  out.innerHTML = `<span style="color:${color};">${emoji} <strong>${tier}</strong> — ${label}</span>`;
}

async function saveVisualAdn() {
  if (_visualAdnState.saving) return;
  if (typeof apiFetch !== 'function') return;

  const description    = (document.getElementById('dashVisualAdnDescription').value || '').trim();
  const usageGuide     = (document.getElementById('dashVisualAdnUsageGuide').value || '').trim();
  const exampleOutputs = (document.getElementById('dashVisualAdnExampleOutputs').value || '').trim();
  const palette        = (document.getElementById('dashVisualAdnPalette').value || '').trim();
  const style          = (document.getElementById('dashVisualAdnStyle')||{}).value || '';
  const priceRaw       = document.getElementById('dashVisualAdnPrice').value;
  const priceCredits   = parseInt(priceRaw, 10);

  if (description.length < 200) {
    _dashToast(`Description trop courte (${description.length}/200 chars min).`);
    return;
  }
  if (description.length > 5000) {
    _dashToast('Description trop longue (5000 chars max).');
    return;
  }
  if (!Number.isInteger(priceCredits) || priceCredits < 30 || priceCredits > 500) {
    _dashToast('Prix invalide — entre 30 et 500 crédits.');
    return;
  }

  const aiRef  = (document.getElementById('dashVisualAdnAiReference')||{}).value || '';
  const supRaw = (document.getElementById('dashVisualAdnMaxSupply')||{}).value || '';
  let maxSupplyVal = null;
  if (supRaw.trim() !== '') {
    const n = parseInt(supRaw, 10);
    if (!Number.isInteger(n) || n < 1) {
      _dashToast('Éditions : nombre invalide. Tape un entier positif ou laisse vide pour illimité.');
      return;
    }
    maxSupplyVal = n;
  }

  const payload = {
    description,
    price_credits: priceCredits,
  };
  if (usageGuide)     payload.usage_guide     = usageGuide;
  if (exampleOutputs) payload.example_outputs = exampleOutputs;
  if (palette)        payload.palette         = palette;
  if (style)          payload.style           = style;
  if (aiRef)          payload.ai_reference    = aiRef;
  if (maxSupplyVal !== null) payload.max_supply = maxSupplyVal;
  // OFFRES-ADN étape 5 : plancher caché (write-only) — n'envoie que si saisi.
  const reserveRawV = ((document.getElementById('dashVisualAdnReserve')||{}).value || '').trim();
  if (reserveRawV !== '') {
    const rv = parseInt(reserveRawV, 10);
    if (!isNaN(rv) && rv >= 0) payload.adn_reserve_credits = rv;
  }

  const isCreate = !_visualAdnState.adn;
  const method   = isCreate ? 'POST' : 'PATCH';

  _visualAdnState.saving = true;
  try {
    const adn = await apiFetch('/artist/me/visual-adn', {
      method,
      json: payload,
    });
    _visualAdnState.adn = adn;
    renderVisualAdnSection();
    closeVisualAdnEditor();
    _dashToast(isCreate ? 'ADN visuel créé · prêt à publier' : 'ADN visuel mis à jour');
  } catch (err) {
    console.error('[dashboard] saveVisualAdn error', err);
    _handleVisualAdnError(err);
  } finally {
    _visualAdnState.saving = false;
  }
}

async function toggleVisualAdnPublish() {
  if (_visualAdnState.saving) return;
  if (typeof apiFetch !== 'function') return;

  if (!_visualAdnState.adn) {
    _dashToast('⚠ Aucun ADN visuel en base. Crée-le d\'abord avec le formulaire ci-dessous.');
    try { await loadMyVisualAdn(); } catch (_) {}
    if (!_visualAdnState.adn) return;
  }

  const nextState = !_visualAdnState.adn.is_published;
  _visualAdnState.saving = true;
  try {
    const adn = await apiFetch('/artist/me/visual-adn', {
      method: 'PATCH',
      json:   { is_published: nextState },
    });
    _visualAdnState.adn = adn;
    renderVisualAdnSection();
    _dashToast(nextState
      ? 'ADN visuel publié — visible sur ton profil 🎉'
      : 'ADN visuel dépublié — invisible pour les fans');
  } catch (err) {
    console.error('[dashboard] toggleVisualAdnPublish error', err);
    const msg = (typeof _humanizeApiError === 'function') ? _humanizeApiError(err) : 'réessaie';
    _dashToast(`⚠ Bascule publication impossible : ${msg}`);
  } finally {
    _visualAdnState.saving = false;
  }
}

async function deleteVisualAdnConfirm() {
  if (!confirm('Supprimer votre ADN visuel du marketplace ? Les acheteurs qui l\'ont déjà acquis gardent leur accès en library.')) return;
  if (typeof apiFetch !== 'function') return;
  try {
    await apiFetch('/artist/me/visual-adn', { method: 'DELETE' });
    _dashToast('ADN visuel supprimé');
    _visualAdnState.adn = null;
    if (typeof loadMyVisualAdn === 'function') {
      await loadMyVisualAdn();
    } else {
      renderVisualAdnSection();
    }
  } catch (e) {
    const msg = (typeof _humanizeApiError === 'function')
      ? _humanizeApiError(e)
      : (e && e.message) || 'Erreur inconnue';
    alert('Échec suppression ADN visuel : ' + msg);
  }
}

function _handleVisualAdnError(err) {
  if (!err) {
    _dashToast('Erreur inconnue — réessaie.');
    return;
  }
  const detail = err.body && err.body.detail;
  if (err.status === 409) {
    if (typeof detail === 'string' && detail.toLowerCase().includes('lock')) {
      _dashToast('Description verrouillée — un acheteur l\'a déjà acquise.');
      // Verrouille le champ + montre la note (mirror du lock backend).
      const descEl = document.getElementById('dashVisualAdnDescription');
      if (descEl) descEl.disabled = true;
      const note = document.getElementById('dashVisualAdnLockNote');
      if (note) note.style.display = '';
    } else if (typeof detail === 'string' && detail.toLowerCase().includes('already')) {
      _dashToast('Tu as déjà un ADN visuel — modifie-le plutôt que d\'en créer un nouveau.');
      loadMyVisualAdn();
    } else {
      _dashToast(typeof detail === 'string' ? detail : 'Conflit — réessaie.');
    }
    return;
  }
  if (err.status === 422) {
    if (Array.isArray(detail) && detail.length && detail[0].msg) {
      _dashToast(`Validation : ${detail[0].msg}`);
    } else {
      _dashToast('Données invalides — vérifie les champs.');
    }
    return;
  }
  if (err.status === 401) {
    _dashToast('Session expirée — reconnecte-toi.');
    return;
  }
  _dashToast('Enregistrement impossible — réessaie.');
}

// Expose pour les onclick HTML
if (typeof window !== 'undefined') {
  window.openAdnEditor        = openAdnEditor;
  window.closeAdnEditor       = closeAdnEditor;
  window.saveAdn              = saveAdn;
  window.dashAdnUpdateRarityPreview = dashAdnUpdateRarityPreview;
  window.dashUpdateEurPreview       = dashUpdateEurPreview;
  window.toggleAdnPublish     = toggleAdnPublish;
  // ADN Visuel (signature visuelle artiste) — section #sec-visual-adn
  window.loadMyVisualAdn          = loadMyVisualAdn;
  window.openVisualAdnEditor      = openVisualAdnEditor;
  window.closeVisualAdnEditor     = closeVisualAdnEditor;
  window.saveVisualAdn            = saveVisualAdn;
  window.toggleVisualAdnPublish   = toggleVisualAdnPublish;
  window.deleteVisualAdnConfirm   = deleteVisualAdnConfirm;
  window.dashVisualAdnUpdateRarityPreview = dashVisualAdnUpdateRarityPreview;
  // Ma Musique — mode switcher + widgets live
  window.setUploadMode        = setUploadMode;
  window.dashToggleBeatFlag   = dashToggleBeatFlag;
  window.dte2ToggleBeatFlag   = dte2ToggleBeatFlag;
  window.updatePromptCharCount = updatePromptCharCount;
  window.updateCreditGrid     = updateCreditGrid;
  // Étape 1 — CTA de la gate "profil publié obligatoire" (onclick inline).
  window.gotoMyProfile          = gotoMyProfile;
  window.handleGatedLayoutClick = handleGatedLayoutClick;
  // Étape 2 — picker couleur du morceau (presets + inherit + color input).
  window.pickTrackColor       = pickTrackColor;
  window.resetTrackColor      = resetTrackColor;
  window.onTrackColorPick     = onTrackColorPick;
}


// ─────────────────────────────────────────────────────────────────────────────
// 2026-05-13 — Live preview équivalent euros à côté des inputs prix crédits.
// Utilisé par dashAdnPrice, dashPromptPrice, dashVoicePrice via oninput.
// Affiche "≈ X€" en dessous de l'input. Mise à jour temps réel.
// ─────────────────────────────────────────────────────────────────────────────
function dashUpdateEurPreview(inputId, outputId) {
  const input = document.getElementById(inputId);
  const output = document.getElementById(outputId);
  if (!input || !output) return;
  const credits = parseInt(input.value, 10);
  if (typeof window.formatEurApprox !== 'function') {
    output.textContent = '';
    return;
  }
  if (!Number.isInteger(credits) || credits <= 0) {
    output.textContent = '';
    return;
  }
  output.textContent = window.formatEurApprox(credits) + ' (ordre d\'idée)';
}

// Init au boot : pour pré-remplir si les inputs ont déjà une valeur (édition).
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(function() {
    dashUpdateEurPreview('dashAdnPrice', 'dashAdnPriceEur');
    dashUpdateEurPreview('dashPromptPrice', 'dashPromptPriceEur');
    dashUpdateEurPreview('dashVoicePrice', 'dashVoicePriceEur');
  }, 100);
});

// ═══════════════════════════════════════════════════════════════════════════
// SECTION ÉCHANGES ADN
// ═══════════════════════════════════════════════════════════════════════════

async function loadTrades() {
  const root = document.getElementById('dash-trades-root');
  if (!root) return;
  try {
    const data = await apiFetch('/trades/offers/me');
    renderTrades(root, data || []);
  } catch (_) {
    root.innerHTML = '<p class="dash-empty-hint">Impossible de charger les échanges.</p>';
  }
}

function _tradeStatusLabel(status) {
  const map = {
    pending:   { label: '⏳ En attente', cls: 'trade-status-pending' },
    accepted:  { label: '✅ Accepté',    cls: 'trade-status-accepted' },
    rejected:  { label: '❌ Refusé',     cls: 'trade-status-rejected' },
    cancelled: { label: '🚫 Annulé',     cls: 'trade-status-cancelled' },
    expired:   { label: '⌛ Expiré',     cls: 'trade-status-expired' },
  };
  return map[status] || { label: status, cls: '' };
}

function _tradeTimeLeft(expiresAt) {
  if (!expiresAt) return '';
  const diff = Math.floor((new Date(expiresAt) - Date.now()) / 1000);
  if (diff <= 0) return 'Expiré';
  if (diff < 3600) return `Expire dans ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `Expire dans ${Math.floor(diff / 3600)} h`;
  return `Expire dans ${Math.floor(diff / 86400)} j`;
}

function renderTrades(root, trades) {
  if (!trades.length) {
    root.innerHTML = `
      <div class="trades-empty">
        <p>Aucun échange en cours.</p>
        <p style="font-size:12px;color:rgba(255,255,255,0.35);margin-top:6px">
          Visite la boutique d'un artiste et clique sur 🔄 Échanger pour proposer un trade.
        </p>
      </div>`;
    return;
  }

  const currentUserId = _dashCurrentUserId();

  const html = trades.map(t => {
    const isSender   = t.sender_id === currentUserId;
    const direction  = isSender ? 'Envoyé à' : 'Reçu de';
    const otherName  = isSender ? (t.receiver_name || 'Artiste') : (t.sender_name || 'Artiste');
    const { label: statusLabel, cls: statusCls } = _tradeStatusLabel(t.status);
    const timeLeft   = t.status === 'pending' ? _tradeTimeLeft(t.expires_at) : '';

    const offered   = t.offered_prompt  || {};
    const requested = t.requested_prompt || {};

    const actions = t.status === 'pending' ? (
      isSender
        ? `<button class="trade-action-btn trade-cancel-btn"
                   onclick="cancelTrade('${t.id}', this)">Annuler</button>`
        : `<button class="trade-action-btn trade-accept-btn"
                   onclick="acceptTrade('${t.id}', this)">✅ Accepter</button>
           <button class="trade-action-btn trade-reject-btn"
                   onclick="rejectTrade('${t.id}', this)">❌ Refuser</button>`
    ) : '';

    const supplement = t.credit_supplement > 0
      ? `<span class="trade-supp">+ ${t.credit_supplement} crédits</span>` : '';

    return `
      <div class="trade-card">
        <div class="trade-card-header">
          <span class="trade-direction">${direction} <strong>${otherName}</strong></span>
          <span class="trade-status ${statusCls}">${statusLabel}</span>
        </div>
        <div class="trade-card-body">
          <div class="trade-prompt-box">
            <span class="trade-prompt-lbl">${isSender ? 'Tu proposes' : 'Il/elle propose'}</span>
            <span class="trade-prompt-name">${offered.title || '—'}</span>
            <span class="trade-prompt-price">${offered.price_credits || 0} crédits</span>
            ${offered.audio_url ? `<audio controls preload="none" src="${offered.audio_url}" style="width:100%;margin-top:6px;height:32px"></audio>` : ''}
          </div>
          <span class="trade-arrow">⇄</span>
          <div class="trade-prompt-box">
            <span class="trade-prompt-lbl">${isSender ? 'Tu demandes' : 'Tu recevrais'}</span>
            <span class="trade-prompt-name">${requested.title || '—'}</span>
            <span class="trade-prompt-price">${requested.price_credits || 0} crédits</span>
            ${requested.audio_url ? `<audio controls preload="none" src="${requested.audio_url}" style="width:100%;margin-top:6px;height:32px"></audio>` : ''}
          </div>
          ${supplement}
        </div>
        ${t.message ? `<p class="trade-message">"${t.message}"</p>` : ''}
        ${timeLeft   ? `<p class="trade-expires">${timeLeft}</p>` : ''}
        ${actions    ? `<div class="trade-actions">${actions}</div>` : ''}
      </div>`;
  }).join('');

  root.innerHTML = `<div class="trades-list">${html}</div>`;
}

function _dashCurrentUserId() {
  try {
    const tok = window.getAuthToken && window.getAuthToken();
    if (!tok) return null;
    const p = JSON.parse(atob(tok.split('.')[1]));
    return p.sub || p.user_id || null;
  } catch (_) { return null; }
}

async function acceptTrade(id, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    await apiFetch(`/trades/offers/${id}/accept`, { method: 'PATCH' });
    loadTrades();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = '✅ Accepter'; }
    const d = (err && err.body && err.body.detail) || err.message || '';
    alert('Erreur : ' + (typeof d === 'string' ? d : JSON.stringify(d)));
  }
}

async function rejectTrade(id, btn) {
  if (!confirm('Refuser cet échange ?')) return;
  if (btn) { btn.disabled = true; }
  try {
    await apiFetch(`/trades/offers/${id}/reject`, { method: 'PATCH' });
    loadTrades();
  } catch (_) {
    if (btn) btn.disabled = false;
  }
}

async function cancelTrade(id, btn) {
  if (!confirm('Annuler ta proposition ?')) return;
  if (btn) { btn.disabled = true; }
  try {
    await apiFetch(`/trades/offers/${id}/cancel`, { method: 'PATCH' });
    loadTrades();
  } catch (_) {
    if (btn) btn.disabled = false;
  }
}

// ── TROPHÉES ──────────────────────────────────────────────────────────────────

const AXIS_LABEL = { buyer: 'Collectionneur', fan: 'Fan', artist: 'Artiste', trader: 'Échanges', referrer: 'Parrainage', streak: 'Fidélité', collector: 'Packs', image_creator: 'Créateur visuel', image_seller: 'Ventes image', visual_dna: 'Signature visuelle' };
const AXIS_ICON  = { buyer: '🛒', fan: '🎚', artist: '🎵', trader: '🔄', referrer: '🤝', streak: '🔥', collector: '🎁', image_creator: '🖼', image_seller: '🏷', visual_dna: '🧬' };
const TPH_AXES = ['buyer', 'fan', 'artist', 'trader', 'referrer', 'streak', 'collector', 'image_creator', 'image_seller', 'visual_dna'];

async function loadTrophees() {
  const grid = document.getElementById('tphGrid');
  if (!grid) return;

  try {
    // Catalog + progression en parallèle
    const [catalog, me] = await Promise.all([
      apiFetch('/achievements'),
      apiFetch('/me/achievements').catch(() => null),
    ]);

    // Mise à jour compteurs par axe
    if (me && me.progress) {
      const p = me.progress;
      const bv = document.getElementById('tphBuyerVal');
      const fv = document.getElementById('tphFanVal');
      const av = document.getElementById('tphArtistVal');
      if (bv) bv.textContent = p.buyer ?? '0';
      if (fv) fv.textContent = p.fan ?? '0';
      if (av) av.textContent = p.artist ?? '0';
    }

    // Index des items débloqués par code
    const unlockedMap = {};
    if (me && me.items) {
      me.items.forEach(item => {
        unlockedMap[item.achievement.code] = {
          unlocked: item.unlocked,
          unlocked_at: item.unlocked_at,
        };
      });
    }

    // Grouper par axe
    const items = catalog.items || [];
    const byAxis = {};
    TPH_AXES.forEach(ax => { byAxis[ax] = []; });
    items.forEach(a => { if (byAxis[a.axis]) byAxis[a.axis].push(a); });

    // Valeur de progression par axe
    const currentVal = {};
    TPH_AXES.forEach(ax => { currentVal[ax] = (me && me.progress && me.progress[ax]) || 0; });

    let html = '';
    TPH_AXES.forEach(axis => {
      const group = byAxis[axis];
      if (!group.length) return;
      html += `<div class="tph-axis-group">
        <div class="tph-axis-group-title">${AXIS_ICON[axis]} ${AXIS_LABEL[axis]}</div>
        <div class="tph-badges-row">`;

      group.sort((a, b) => a.display_order - b.display_order).forEach(a => {
        const state = unlockedMap[a.code] || { unlocked: false };
        const cur   = currentVal[axis] || 0;
        const pct   = Math.min(Math.round((cur / a.threshold) * 100), 100);
        const done  = state.unlocked;

        html += `<div class="tph-badge ${done ? 'tph-badge-done' : 'tph-badge-locked'}">
          <div class="tph-badge-icon">${done ? '🏆' : '🔒'}</div>
          <div class="tph-badge-name">${htmlEscape(a.name)}</div>
          <div class="tph-badge-desc">${htmlEscape(a.description)}</div>
          ${a.credit_reward > 0 ? `<div class="tph-badge-reward">+${a.credit_reward} Smyles</div>` : ''}
          ${!done ? `<div class="tph-badge-progress">
            <div class="tph-progress-bar"><div class="tph-progress-fill" style="width:${pct}%"></div></div>
            <span class="tph-progress-txt">${cur} / ${a.threshold}</span>
          </div>` : `<div class="tph-badge-unlocked-at">${state.unlocked_at ? '✓ ' + new Date(state.unlocked_at).toLocaleDateString('fr-FR') : '✓ Débloqué'}</div>`}
        </div>`;
      });

      html += `</div></div>`;
    });

    grid.innerHTML = html || '<div class="tph-loading">Aucun trophée disponible.</div>';
  } catch (e) {
    if (grid) grid.innerHTML = '<div class="tph-loading">Impossible de charger les trophées.</div>';
  }
}
