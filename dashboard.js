/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — Dashboard Artiste PLUG WATT
   dashboard.js — Logique complète + canvas réseau + chart SVG 7j
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ── 0. HELPERS GLOBAUX ────────────────────────────────────────────────────────

// Limite freemium — version gratuite bêta
const FREE_LIMIT = 6;

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
      if (hit && hit.slug) window.location.href = `/u/${hit.slug}`;
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
      if (hit && hit.slug) { e.preventDefault(); window.location.href = `/u/${hit.slug}`; }
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
    this.H = this.canvas.height = 420;
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
  const href = slug ? '/u/' + encodeURIComponent(slug) : '#';
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
  const limited = count >= FREE_LIMIT;

  // Compteur freemium
  const counterVal = document.getElementById('dashFreeCounterVal');
  const barFill    = document.getElementById('dashFreeBarFill');
  if (counterVal) {
    counterVal.textContent = limited
      ? 'Playlist complète ✓'
      : `${count} / ${FREE_LIMIT} sons utilisés`;
    counterVal.style.color = limited ? '#FFD700' : '';
  }
  if (barFill) {
    const pct = Math.min((count / FREE_LIMIT) * 100, 100);
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
    const limited = tracks.length >= FREE_LIMIT;
    countEl.textContent = `${tracks.length}\u202f/\u202f${FREE_LIMIT} son${tracks.length !== 1 ? 's' : ''}`;
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
      <button class="dash-btn-ghost" style="padding:4px 10px;font-size:.68rem" onclick="deleteTrack('${t.id}')">✕</button>
    </div>`;
  }).join('');
}

async function deleteTrack(id) {
  const tracks    = getMyTracks();
  const trackToDelete = tracks.find(t => t.id === id);

  // Supprimer en localStorage immédiatement
  saveMyTracks(tracks.filter(t => t.id !== id));
  renderArtistCard();
  renderMyTracks();
  renderStats();
  renderRanking();
  dashToast('Son supprimé.');

  // Supprimer en DB si l'on a un dbId (shim FastAPI)
  if (trackToDelete?.dbId) {
    try {
      await apiFetch(`/watt/tracks/${encodeURIComponent(trackToDelete.dbId)}`, { method: 'DELETE' });
    } catch (_) { /* silencieux */ }
  }
}

// ── 6. AVATAR UPLOAD ──────────────────────────────────────────────────────────
// Retiré avec le bloc #sec-artist : l'upload d'avatar se fait désormais sur
// /u/<slug> via artiste.js. Les helpers triggerAvatarUpload / handleAvatarUpload
// qui vivaient ici ne sont plus utilisés (plus aucun onclick ne les appelle).

// ── 7. UPLOAD DE SON ──────────────────────────────────────────────────────────

let _pendingFile   = null;
let _coverDataUrl  = null;

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
// Valeurs : 'with_prompt' (défaut) · 'simple'.
function setUploadMode(mode) {
  if (mode !== 'with_prompt' && mode !== 'simple') mode = 'with_prompt';
  const form = document.getElementById('dashUploadForm');
  if (!form) return;
  form.dataset.mode = mode;

  // Pills actifs (tab state + aria)
  document.querySelectorAll('.dash-mode-pill').forEach(p => {
    const on = p.dataset.mode === mode;
    p.classList.toggle('is-active', on);
    p.setAttribute('aria-selected', on ? 'true' : 'false');
  });

  // Libellé du CTA — reflète la nature du post
  const cta = document.getElementById('dashUploadCtaLbl');
  if (cta) {
    cta.textContent = mode === 'with_prompt'
      ? 'Publier avec recette'
      : 'Publier sans recette';
  }
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

  // ── Vérification limite freemium ─────────────────────────────────────────
  const _existing = getMyTracks();
  if (_existing.length >= FREE_LIMIT) {
    dashToast('Ta playlist gratuite est complète (6 / 6). PLUG WATT illimité arrive bientôt !');
    renderUploadState();
    cancelUpload();
    return;
  }

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
  let uploaded  = false;
  let streamUrl = null;
  let r2Key     = null;

  // ── 1. Upload fichier audio vers R2 ─────────────────────────────────────
  try {
    const fd = new FormData();
    fd.append('file',   _pendingFile);
    fd.append('name',   name);
    fd.append('userId', user ? String(user.id) : 'guest');

    const res  = await fetch('/api/watt/upload', { method: 'POST', body: fd });
    if (res.ok) {
      const data = await res.json();
      uploaded  = !data.mock;
      streamUrl = data.url  || null;
      r2Key     = data.key  || null;
      setProgress(70, 'Enregistrement…');
    }
  } catch (_) { /* mode hors-ligne */ }

  await wait(300);
  setProgress(85, 'Sauvegarde en base…');

  // ── 2. Enregistrer les métadonnées du track dans la DB ──────────────────
  let dbTrackId = null;
  try {
    const res2 = await fetch('/api/watt/tracks', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      // Étape 2 — on envoie color seulement si l'artiste a fait un choix.
      // null/absent → le serveur laisse color=NULL → front retombe sur
      // brandColor du profil à l'affichage.
      body:    JSON.stringify({ name, genre, streamUrl, r2Key, color: _pendingTrackColor }),
    });
    if (res2.ok) {
      const data2 = await res2.json();
      dbTrackId   = data2.track?.id || null;
    } else if (res2.status === 409) {
      // Étape 1 — le serveur refuse parce que profile_public=false.
      // On resynchronise l'état local depuis /users/me puis on affiche la
      // gate pédagogique. On stoppe AVANT le localStorage pour ne pas laisser
      // une track fantôme côté client.
      setProgress(100, '⚠ Profil non publié');
      await loadPublishStatus();
      renderCreationGate();
      dashToast('Publie d\'abord ton profil pour pouvoir poster un son.');
      cancelUpload();
      return;
    }
  } catch (_) { /* pas de DB connectée — localStorage prend le relais */ }

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
  const uploadMode = form && form.dataset.mode === 'simple' ? 'simple' : 'with_prompt';
  if (uploadMode === 'with_prompt') {
    const promptText = (document.getElementById('dashPromptText')?.value || '').trim();
    const lyrics     = (document.getElementById('dashPromptLyrics')?.value || '').trim();
    const priceRaw   = parseInt(document.getElementById('dashPromptPrice')?.value, 10);
    const price      = Number.isFinite(priceRaw) ? priceRaw : 80;

    if (promptText.length < 100) {
      dashToast('⚠ Recette IA : prompt trop court (min 100 caractères). Son publié, prompt non créé.');
    } else if (promptText.length > 1000) {
      dashToast('⚠ Recette IA : prompt trop long (max 1000 — plafond Suno). Son publié, prompt non créé.');
    } else if (price < 3 || price > 500) {
      dashToast('⚠ Prix prompt entre 3 et 500 crédits. Son publié, prompt non créé.');
    } else {
      try {
        await apiFetch('/artist/me/prompts', {
          method: 'POST',
          json: {
            title:        name,                    // titre = même que la track
            description:  desc || `Recette IA de "${name}"`,
            prompt_text:  promptText,
            lyrics:       lyrics || null,
            price_credits: price,
            is_published: true,
          },
        });
        dashToast(`💎 Recette IA "${name}" publiée sur la marketplace.`);
      } catch (e) {
        const msg = (e && e.body && e.body.detail) || (e && e.message) || 'erreur inconnue';
        dashToast(`⚠ Son publié, mais prompt refusé : ${msg}`);
      }
    }
  }

  setProgress(100, uploaded ? '⚡ Son publié sur WATT !' : '⚡ Son sauvegardé !');
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

  // 2. Sync avec la DB (principal pour la communauté)
  try {
    const res = await fetch('/api/watt/profile', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(profile),
    });
    if (res.ok) {
      const data = await res.json();
      // Mettre à jour le slug avec le slug validé par le serveur
      if (data.artist?.slug) {
        profile.slug = data.artist.slug;
        saveWattProfile(profile);
      }
    }
  } catch (_) { /* mode hors-ligne — localStorage suffit */ }

  // 3. Sync FastAPI (artist_name + bio + socials + brand_color). Indispensable
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
    const url  = `/u/${slug}`;
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
  const base = slug ? `/u/${encodeURIComponent(slug)}` : '/u/me';
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

// ── 8 ter. PILL PLUG WATT (sec-plug) ─────────────────────────────────────────
// Contrôle centralisé de la présence publique sur la marketplace. Ingrédients :
//   • switch ON/OFF qui bascule profile_public (réutilise publishMyProfile /
//     unpublishMyProfile pour que _dashPublishState reste la source unique
//     de vérité — pas de double état à synchroniser).
//   • preview de la cellule marketplace (nom, genre, brand) — permet à l'user
//     de vérifier visuellement avant de basculer le switch.
//   • 3 compteurs (abonnés, écoutes, rang) — mis à jour par renderStats() via
//     renderPlugStatsFromAggregate() à chaque refresh.
//   • lien "Ouvrir ma boutique" → /u/<slug>.
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
      open.href = `/u/${encodeURIComponent(slug)}`;
      open.classList.remove('is-disabled');
    } else {
      open.href = '#';
      open.classList.add('is-disabled');
    }
  }

  // ── Compteurs : lus des mêmes sources que les stats cards ──────────────
  renderPlugStatsFromDom();
}

// Synchro légère : on lit les mêmes valeurs que celles affichées dans les
// stat cards (statsPlays / statsFollowers / statsRank) pour ne pas re-fetcher
// à chaque toggle. renderStats() les alimente déjà au chargement.
function renderPlugStatsFromDom() {
  const copyFrom = (srcId, dstId) => {
    const src = document.getElementById(srcId);
    const dst = document.getElementById(dstId);
    if (src && dst) dst.textContent = src.textContent || '—';
  };
  copyFrom('statsFollowers', 'dashPlugFollowers');
  copyFrom('statsPlays',     'dashPlugPlays');
  copyFrom('statsRank',      'dashPlugRank');
}

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
  window.open(`/u/${encodeURIComponent(slug)}`, '_blank', 'noopener');
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

  // Ma position — l'ancien KPI "Rang WATT" de #sec-artist a été retiré.
  // Le rang est désormais affiché uniquement dans #sec-stats (id statsRank),
  // renseigné par renderStatsCards() via setTextById('statsRank', …).
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

function dashLogout() {
  clearCurrentUser();
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

  // Section nav
  initSectionNav();

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
    });

    window.SmyleEvents.on(window.SmyleEvents.TYPES.PROFILE_UNPUBLISHED, () => {
      _dashPublishState.isPublic = false;
      _dashPublishState.loaded   = true;
      renderPublishBlock();
      renderCreationGate();
      renderPlugSection();
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

  editor.style.display = '';
  editor.scrollIntoView({ behavior: 'smooth', block: 'center' });
  const desc = document.getElementById('dashAdnDescription');
  if (desc) setTimeout(() => desc.focus(), 100);
}

function closeAdnEditor() {
  const editor = document.getElementById('dashAdnEditor');
  if (editor) editor.style.display = 'none';
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
  if (!Number.isInteger(priceCredits) || priceCredits < 30 || priceCredits > 500) {
    _dashToast('Prix invalide — entre 30 et 500 crédits.');
    return;
  }

  const payload = {
    description,
    price_credits: priceCredits,
  };
  // On n'envoie usage_guide/example_outputs que si remplis
  // (évite d'effacer par inadvertance côté PATCH partiel).
  if (usageGuide)     payload.usage_guide     = usageGuide;
  if (exampleOutputs) payload.example_outputs = exampleOutputs;

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
  if (_adnState.saving || !_adnState.adn) return;
  if (typeof apiFetch !== 'function') return;

  const nextState = !_adnState.adn.is_published;
  _adnState.saving = true;
  try {
    const adn = await apiFetch('/artist/me/adn', {
      method: 'PATCH',
      json:   { is_published: nextState },
    });
    _adnState.adn = adn;
    renderAdnSection();
    _dashToast(nextState
      ? 'ADN publié — visible sur ton profil 🎉'
      : 'ADN dépublié — invisible pour les fans');
  } catch (err) {
    console.error('[dashboard] toggleAdnPublish error', err);
    _handleAdnError(err);
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

// Expose pour les onclick HTML
if (typeof window !== 'undefined') {
  window.openAdnEditor        = openAdnEditor;
  window.closeAdnEditor       = closeAdnEditor;
  window.saveAdn              = saveAdn;
  window.toggleAdnPublish     = toggleAdnPublish;
  // Ma Musique — mode switcher + widgets live
  window.setUploadMode        = setUploadMode;
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
