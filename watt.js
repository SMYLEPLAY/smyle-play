/* ═══════════════════════════════════════════════════════════════════════════
   PLUG WATT — watt.js
   Page artiste PLUG WATT · Réseau électrique animé · Upload R2
   ═══════════════════════════════════════════════════════════════════════════ */

// ── BÊTA GRATUITE — pas de code ni de paiement requis ────────────────────────

// ── Limite freemium ───────────────────────────────────────────────────────────
const FREE_LIMIT = 6;   // Nombre maximum de sons en version gratuite

// ── 1. CANVAS ELECTRIC WEB (fond de page) ────────────────────────────────────

class ElectricWebBg {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext('2d');
    this.nodes  = [];
    this.particles = [];
    this.mouse  = { x: -999, y: -999 };
    this.resize();
    this.initNodes();
    this.bindEvents();
    this.animate();
  }

  resize() {
    this.W = this.canvas.width  = window.innerWidth;
    this.H = this.canvas.height = window.innerHeight;
  }

  initNodes() {
    this.nodes = [];
    const count = Math.max(14, Math.floor(this.W / 90));
    for (let i = 0; i < count; i++) {
      this.nodes.push({
        x:  Math.random() * this.W,
        y:  Math.random() * this.H,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
        r:  2.5 + Math.random() * 3,
        glow: 0.5 + Math.random() * 0.5,
      });
    }
    // Particles sur les connexions
    this.particles = [];
    for (let i = 0; i < 28; i++) {
      this.spawnParticle();
    }
  }

  spawnParticle() {
    const n1 = Math.floor(Math.random() * this.nodes.length);
    let n2;
    do { n2 = Math.floor(Math.random() * this.nodes.length); } while (n2 === n1);
    this.particles.push({
      n1, n2,
      progress: Math.random(),
      speed: 0.0018 + Math.random() * 0.0025,
      alpha: 0.6 + Math.random() * 0.4,
      size:  1.5 + Math.random() * 1.5,
    });
  }

  bindEvents() {
    window.addEventListener('mousemove', e => {
      this.mouse.x = e.clientX;
      this.mouse.y = e.clientY;
    });
    window.addEventListener('resize', () => {
      this.resize();
      this.initNodes();
    });
  }

  draw() {
    const { ctx, W, H, nodes, particles, mouse } = this;
    ctx.clearRect(0, 0, W, H);

    // Connexions entre nœuds proches
    const DIST = Math.min(220, W * 0.22);
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > DIST) continue;

        const alpha = (1 - dist / DIST) * 0.28;
        ctx.save();
        ctx.beginPath();
        ctx.strokeStyle = `rgba(255,215,0,${alpha})`;
        ctx.lineWidth   = 0.8;
        ctx.shadowColor = '#FFD700';
        ctx.shadowBlur  = 3;
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.restore();
      }
    }

    // Particules
    for (const p of particles) {
      const a = nodes[p.n1], b = nodes[p.n2];
      const x = a.x + (b.x - a.x) * p.progress;
      const y = a.y + (b.y - a.y) * p.progress;

      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,235,80,${p.alpha})`;
      ctx.shadowColor = '#FFD700';
      ctx.shadowBlur  = 10;
      ctx.fill();
      ctx.restore();

      p.progress += p.speed;
      if (p.progress >= 1) {
        p.progress = 0;
        // Choisir une nouvelle paire de nœuds
        p.n1 = Math.floor(Math.random() * nodes.length);
        do { p.n2 = Math.floor(Math.random() * nodes.length); } while (p.n2 === p.n1);
      }
    }

    // Nœuds
    for (const n of nodes) {
      const mdx = mouse.x - n.x, mdy = mouse.y - n.y;
      const mDist = Math.sqrt(mdx * mdx + mdy * mdy);
      const boost = mDist < 100 ? (1 - mDist / 100) * 0.6 : 0;
      const glow  = n.glow + boost;

      // Halo
      const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 5);
      grad.addColorStop(0,   `rgba(255,215,0,${glow * 0.55})`);
      grad.addColorStop(0.5, `rgba(255,215,0,${glow * 0.12})`);
      grad.addColorStop(1,   'rgba(255,215,0,0)');
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * 5, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Cœur
      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,215,0,${glow})`;
      ctx.shadowColor = '#FFD700';
      ctx.shadowBlur  = 12;
      ctx.fill();
      ctx.restore();

      // Déplacer
      n.x += n.vx; n.y += n.vy;
      if (n.x < -20 || n.x > W + 20) n.vx *= -1;
      if (n.y < -20 || n.y > H + 20) n.vy *= -1;
    }
  }

  animate() {
    this.draw();
    requestAnimationFrame(() => this.animate());
  }
}

// ── 2. CANVAS NETWORK (panel visualisation) ──────────────────────────────────

class WattNetwork {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext('2d');
    this.nodes  = [];
    this.edges  = [];
    this.particles = [];
    this.resize();
    this.buildGraph();
    this.animate();
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.W = this.canvas.width  = rect.width  || 900;
    this.H = this.canvas.height = rect.height || 320;
  }

  buildGraph() {
    const W = this.W, H = this.H;
    // Types: 'artist' (gold), 'track' (cyan), 'playlist' (red)
    const nodeData = [
      { label: 'Artiste A', type: 'artist',   x: W*.12, y: H*.3  },
      { label: 'Artiste B', type: 'artist',   x: W*.85, y: H*.2  },
      { label: 'Artiste C', type: 'artist',   x: W*.55, y: H*.8  },
      { label: 'Artiste D', type: 'artist',   x: W*.22, y: H*.75 },
      { label: 'Track 01',  type: 'track',    x: W*.35, y: H*.2  },
      { label: 'Track 02',  type: 'track',    x: W*.68, y: H*.55 },
      { label: 'Track 03',  type: 'track',    x: W*.15, y: H*.55 },
      { label: 'Track 04',  type: 'track',    x: W*.82, y: H*.7  },
      { label: 'WATT',      type: 'watt',     x: W*.5,  y: H*.42 },
      { label: 'Sunset',    type: 'playlist', x: W*.72, y: H*.3  },
      { label: 'Night City',type: 'playlist', x: W*.4,  y: H*.65 },
      { label: 'Hit Mix',   type: 'playlist', x: W*.25, y: H*.45 },
    ];

    this.nodes = nodeData.map(d => ({
      ...d,
      vx: (Math.random() - .5) * .25,
      vy: (Math.random() - .5) * .25,
      r:  d.type === 'watt' ? 9 : d.type === 'artist' ? 6 : 4.5,
    }));

    // Connexions (edges)
    this.edges = [
      [8,0],[8,1],[8,2],[8,3],            // WATT → artistes
      [0,4],[0,6],[1,4],[1,5],[2,5],[3,6],// artistes → tracks
      [4,9],[5,9],[6,11],[5,10],[6,10],   // tracks → playlists
      [3,11],[2,10],[7,10],[1,7],[7,9],   // suite
      [0,11],[1,9],[8,4],[8,5],           // WATT → tracks
    ];

    // Particules électriques
    this.particles = [];
    for (let i = 0; i < 22; i++) {
      const e = this.edges[Math.floor(Math.random() * this.edges.length)];
      this.particles.push({
        e: [...e],
        p: Math.random(),
        spd: 0.004 + Math.random() * 0.005,
        a: 0.7 + Math.random() * 0.3,
      });
    }
  }

  nodeColor(type) {
    if (type === 'artist')   return { fill: 'rgba(255,215,0,0.9)', glow: '#FFD700' };
    if (type === 'track')    return { fill: 'rgba(0,210,255,0.85)', glow: '#00CFFF' };
    if (type === 'playlist') return { fill: 'rgba(255,100,100,0.85)', glow: '#FF6060' };
    if (type === 'watt')     return { fill: 'rgba(255,230,0,1)', glow: '#FFD700' };
    return { fill: 'rgba(255,255,255,.5)', glow: '#fff' };
  }

  draw() {
    const { ctx, W, H, nodes, edges, particles } = this;
    ctx.clearRect(0, 0, W, H);

    // Fond très sombre
    ctx.fillStyle = 'rgba(8,7,2,0.0)';
    ctx.fillRect(0, 0, W, H);

    // Edges
    for (const [i, j] of edges) {
      const a = nodes[i], b = nodes[j];
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.sqrt(dx*dx+dy*dy);
      const alpha = Math.max(0.04, 0.22 - len / (W * 0.8));

      ctx.save();
      ctx.beginPath();
      ctx.strokeStyle = `rgba(255,200,0,${alpha})`;
      ctx.lineWidth = 1;
      ctx.shadowColor = 'rgba(255,200,0,0.3)';
      ctx.shadowBlur  = 4;
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.restore();
    }

    // Particules
    for (const p of particles) {
      const [i, j] = p.e;
      const a = nodes[i], b = nodes[j];
      const x = a.x + (b.x - a.x) * p.p;
      const y = a.y + (b.y - a.y) * p.p;

      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI*2);
      ctx.fillStyle = `rgba(255,235,60,${p.a})`;
      ctx.shadowColor = '#FFD700';
      ctx.shadowBlur  = 8;
      ctx.fill();
      ctx.restore();

      p.p += p.spd;
      if (p.p >= 1) {
        p.p = 0;
        p.e = [...this.edges[Math.floor(Math.random() * this.edges.length)]];
      }
    }

    // Nœuds
    for (const n of nodes) {
      const c = this.nodeColor(n.type);

      // Halo
      const gr = ctx.createRadialGradient(n.x,n.y,0, n.x,n.y, n.r*4.5);
      const baseAlpha = n.type === 'watt' ? 0.35 : 0.2;
      gr.addColorStop(0,   c.fill.replace(/[\d.]+\)$/, `${baseAlpha})`));
      gr.addColorStop(1,   'rgba(0,0,0,0)');
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * 4.5, 0, Math.PI*2);
      ctx.fillStyle = gr;
      ctx.fill();

      // Cercle principal
      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI*2);
      ctx.fillStyle = c.fill;
      ctx.shadowColor = c.glow;
      ctx.shadowBlur  = n.type === 'watt' ? 18 : 10;
      ctx.fill();
      ctx.restore();

      // Label
      ctx.save();
      ctx.font = `${n.type==='watt'?'700 ':''} ${n.type==='watt'?10:8}px Helvetica, Arial, sans-serif`;
      ctx.fillStyle = n.type==='watt' ? 'rgba(255,215,0,0.9)' : 'rgba(255,240,200,0.5)';
      ctx.textAlign = 'center';
      ctx.fillText(n.label, n.x, n.y + n.r + 13);
      ctx.restore();

      // Mouvement lent
      n.x += n.vx; n.y += n.vy;
      const pad = 40;
      if (n.x < pad || n.x > W - pad) n.vx *= -1;
      if (n.y < pad || n.y > H - pad) n.vy *= -1;
    }
  }

  animate() {
    this.draw();
    requestAnimationFrame(() => this.animate());
  }
}

// ── 3. AUTH (réutilise localStorage de index.html) ────────────────────────────

// ── Wrapper sécurisé localStorage (Safari Private Mode / quota 0) ────────────
// En navigation privée iOS, localStorage.setItem lance QuotaExceededError silencieusement.
// Ce wrapper intercepte l'erreur et affiche un message utile à l'utilisateur.
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
  // Vérifie si le stockage est disponible (écrit + lit un octet de test)
  isAvailable() {
    try {
      const k = '__smyle_test__';
      localStorage.setItem(k, '1');
      localStorage.removeItem(k);
      return true;
    } catch(e) { return false; }
  },
};

function getUsers()       { return JSON.parse(safeStorage.getItem('smyle_users') || '[]'); }
function saveUsers(u)     { safeStorage.setItem('smyle_users', JSON.stringify(u)); }
function getCurrentUser() { return JSON.parse(safeStorage.getItem('smyle_current_user') || 'null'); }
function setCurrentUser(u){ return safeStorage.setItem('smyle_current_user', JSON.stringify(u)); }
function clearCurrentUser(){ safeStorage.removeItem('smyle_current_user'); }

// ── Slugify (identique à dashboard.js) ──────────────────────────────────────
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

// ── 4. ÉTAT DE L'UI ───────────────────────────────────────────────────────────
// Bêta gratuite : connecté → gate-subscribe (CTA dashboard), sinon → gate-login

function renderPageState() {
  const user = getCurrentUser();

  document.getElementById('gate-login').style.display     = (!user) ? '' : 'none';
  document.getElementById('gate-subscribe').style.display = (user)  ? '' : 'none';

  renderNavUser(user);
  // Les deux fonctions sont async — appel sans await (fire-and-forget, elles gèrent leur propre état)
  renderPublicRanking();
  renderPublicTracks();
}

// Accès direct au dashboard (bêta gratuite — pas de vérification de paiement)
function enterDashboard() {
  window.location.href = '/dashboard';
}

function renderNavUser(user) {
  const area = document.getElementById('wattNavUser');
  if (!area) return;
  if (user) {
    area.innerHTML = `
      <span class="watt-nav-user-name">${user.name}</span>
      <span style="font-size:9px;letter-spacing:.2em;color:rgba(255,215,0,.5);text-transform:uppercase;border:1px solid rgba(255,215,0,.2);padding:2px 8px;border-radius:2px">⚡ WATT</span>
      <button class="watt-nav-logout-btn" onclick="wattLogout()">Déco</button>
    `;
  } else {
    area.innerHTML = `
      <button class="watt-btn-ghost" style="padding:5px 14px;font-size:9px" onclick="openWattAuth('login')">Connexion</button>
    `;
  }
}

// ── 5. AUTH MODAL ─────────────────────────────────────────────────────────────

function openWattAuth(tab) {
  document.getElementById('wattAuthModal').classList.add('open');
  switchWattTab(tab);
}

function closeWattAuthModal() {
  document.getElementById('wattAuthModal').classList.remove('open');
  document.getElementById('wAuthMsg').textContent = '';
}

function switchWattTab(tab) {
  document.getElementById('wtab-login').classList.toggle('active',  tab === 'login');
  document.getElementById('wtab-signup').classList.toggle('active', tab === 'signup');
  document.getElementById('wform-login').style.display  = tab === 'login'  ? '' : 'none';
  document.getElementById('wform-signup').style.display = tab === 'signup' ? '' : 'none';
  document.getElementById('wAuthMsg').textContent = '';
}

function _authMsg(txt) {
  const el = document.getElementById('wAuthMsg');
  if (el) el.textContent = txt;
}

function wattLogin() {
  // Vérification stockage disponible (Safari Private Mode)
  if (!safeStorage.isAvailable()) {
    _authMsg('Stockage indisponible. Quitte la navigation privée et réessaie.');
    return;
  }
  const email = document.getElementById('wlogin-email').value.trim();
  const pass  = document.getElementById('wlogin-password').value;
  if (!email || !pass) { _authMsg('Remplis tous les champs.'); return; }

  const users = getUsers();
  const user  = users.find(u => u.email === email && u.password === pass);
  if (!user) {
    _authMsg('Email ou mot de passe incorrect.');
    return;
  }
  if (!setCurrentUser(user)) {
    _authMsg('Impossible de sauvegarder la session. Essaie en mode normal.');
    return;
  }
  closeWattAuthModal();
  // Redirect immédiat — pas de setTimeout pour éviter problèmes mobile
  window.location.replace('/dashboard');
}

function wattSignup() {
  // Vérification stockage disponible (Safari Private Mode)
  if (!safeStorage.isAvailable()) {
    _authMsg('Stockage indisponible. Quitte la navigation privée et réessaie.');
    return;
  }
  const name  = document.getElementById('wsignup-name').value.trim();
  const email = document.getElementById('wsignup-email').value.trim();
  const pass  = document.getElementById('wsignup-password').value;
  if (!name || !email || !pass) { _authMsg('Tous les champs sont requis.'); return; }
  if (pass.length < 6)          { _authMsg('Mot de passe trop court (min 6 caractères).'); return; }

  const users = getUsers();
  if (users.find(u => u.email === email)) {
    _authMsg('Email déjà utilisé — connecte-toi.');
    return;
  }
  const user = { id: Date.now(), email, password: pass, name, playlists: [] };
  users.push(user);
  saveUsers(users);
  if (!setCurrentUser(user)) {
    _authMsg('Impossible de sauvegarder la session. Essaie en mode normal.');
    return;
  }
  closeWattAuthModal();
  window.location.replace('/dashboard');
}

function wattLogout() {
  clearCurrentUser();
  renderPageState();
  wattToast('Déconnecté.');
}

// ── 7. PROFIL ARTISTE ─────────────────────────────────────────────────────────

function getArtistProfile() {
  const user = getCurrentUser();
  const key = `smyle_watt_profile_${user ? user.id : 'guest'}`;
  return JSON.parse(localStorage.getItem(key) || 'null');
}

function saveArtistProfile(data) {
  const user = getCurrentUser();
  const key = `smyle_watt_profile_${user ? user.id : 'guest'}`;
  localStorage.setItem(key, JSON.stringify(data));
}

function renderProfile() {
  const user    = getCurrentUser();
  const profile = getArtistProfile();
  const name    = profile?.artistName || user?.name || '—';
  const genre   = profile?.genre || 'Genre non défini';
  const bio     = profile?.bio || 'Pas encore de bio...';
  const initials = name.slice(0, 2).toUpperCase();

  document.getElementById('avatarDisplay').textContent = initials;
  document.getElementById('profileName').textContent   = name;
  document.getElementById('profileGenre').textContent  = genre;
  document.getElementById('profileBio').textContent    = bio;

  const linksEl = document.getElementById('profileLinks');
  const links = [];
  if (profile?.soundcloud) links.push({ label: 'SoundCloud', url: profile.soundcloud });
  if (profile?.instagram)  links.push({ label: 'Instagram',  url: 'https://instagram.com/' + profile.instagram.replace('@', '') });

  linksEl.innerHTML = links.map(l =>
    `<a class="watt-profile-link" href="${l.url}" target="_blank">${l.label}</a>`
  ).join('');
}

function toggleEditProfile() {
  const view = document.getElementById('profileView');
  const edit = document.getElementById('profileEdit');
  const isEditing = edit.style.display !== 'none';
  if (isEditing) { cancelEditProfile(); return; }

  const profile = getArtistProfile();
  const user = getCurrentUser();
  document.getElementById('editArtistName').value  = profile?.artistName || user?.name || '';
  document.getElementById('editGenre').value       = profile?.genre || '';
  document.getElementById('editBio').value         = profile?.bio || '';
  document.getElementById('editSoundcloud').value  = profile?.soundcloud || '';
  document.getElementById('editInstagram').value   = profile?.instagram || '';

  view.style.display = 'none';
  edit.style.display = '';
}

function cancelEditProfile() {
  document.getElementById('profileView').style.display = '';
  document.getElementById('profileEdit').style.display = 'none';
}

function saveProfile() {
  const data = {
    artistName:  document.getElementById('editArtistName').value.trim(),
    genre:       document.getElementById('editGenre').value.trim(),
    bio:         document.getElementById('editBio').value.trim(),
    soundcloud:  document.getElementById('editSoundcloud').value.trim(),
    instagram:   document.getElementById('editInstagram').value.trim(),
    updatedAt:   Date.now(),
  };
  if (!data.artistName) { wattToast('Entre un nom d\'artiste.'); return; }
  saveArtistProfile(data);
  cancelEditProfile();
  renderProfile();
  updateStats();
  wattToast('Profil sauvegardé ✓');
}

// ── 8. UPLOAD ─────────────────────────────────────────────────────────────────

let selectedFile = null;

function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('wattDropzone').classList.add('drag-over');
}

function handleDragLeave(e) {
  document.getElementById('wattDropzone').classList.remove('drag-over');
}

function handleFileDrop(e) {
  e.preventDefault();
  document.getElementById('wattDropzone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) selectFile(file);
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) selectFile(file);
}

function selectFile(file) {
  const ALLOWED = ['audio/wav', 'audio/mpeg', 'audio/flac', 'audio/x-flac',
                   'audio/aac', 'audio/mp4', 'audio/ogg', 'audio/x-m4a',
                   'audio/m4a', 'audio/mp3'];
  const ext = file.name.split('.').pop().toLowerCase();
  const allowed_ext = ['wav','mp3','flac','aac','m4a','ogg'];

  if (!allowed_ext.includes(ext)) {
    wattToast('Format non supporté. Utilise WAV, MP3, FLAC, AAC ou M4A.');
    return;
  }
  if (file.size > 100 * 1024 * 1024) {
    wattToast('Fichier trop lourd (max 100 MB).');
    return;
  }

  selectedFile = file;
  const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
  document.getElementById('uploadFileInfo').textContent = `🎵 ${file.name}  ·  ${sizeMB} MB`;
  document.getElementById('uploadTrackName').value = file.name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' ');
  document.getElementById('uploadForm').style.display = '';
  document.getElementById('wattDropzone').style.display = 'none';
}

function cancelUpload() {
  selectedFile = null;
  document.getElementById('uploadForm').style.display   = 'none';
  document.getElementById('wattDropzone').style.display = '';
  document.getElementById('audioFileInput').value = '';
  document.getElementById('uploadTrackName').value = '';
  document.getElementById('uploadGenreTag').value  = '';
  document.getElementById('uploadDesc').value = '';
  document.getElementById('uploadProgressWrap').style.display = 'none';
}

async function uploadTrack() {
  const trackName = document.getElementById('uploadTrackName').value.trim();
  if (!trackName) { wattToast('Donne un titre à ton morceau.'); return; }
  if (!selectedFile) { wattToast('Aucun fichier sélectionné.'); return; }

  // ── Vérification limite freemium ─────────────────────────────────────────
  const _user = getCurrentUser();
  const _uid  = _user ? _user.id : 'guest';
  const _existing = getMyWattTracks(_uid);
  if (_existing.length >= FREE_LIMIT) {
    wattToast('Ta playlist gratuite est complète (6 / 6). PLUG WATT illimité arrive bientôt !');
    renderUploadState();
    return;
  }

  const user    = getCurrentUser();
  const profile = getArtistProfile();
  const genre   = document.getElementById('uploadGenreTag').value.trim();
  const desc    = document.getElementById('uploadDesc').value.trim();

  // Afficher la progression
  document.getElementById('uploadForm').style.display = 'none';
  document.getElementById('uploadProgressWrap').style.display = '';

  const progressFill  = document.getElementById('uploadFill');
  const progressLabel = document.getElementById('uploadLbl');

  // ── Mode Mock (pas de backend R2 configuré) ──
  // En production, remplace ce bloc par un vrai fetch('/api/watt/upload', FormData)
  // Architecture R2 cible: WATT/{userId}/{timestamp}-{filename}
  progressLabel.textContent = 'Préparation du fichier...';
  await simulateProgress(progressFill, 0, 35, 600);

  progressLabel.textContent = 'Upload vers Cloudflare R2...';
  await simulateProgress(progressFill, 35, 85, 900);

  progressLabel.textContent = 'Finalisation...';
  await simulateProgress(progressFill, 85, 100, 400);

  // Tenter l'upload via API si disponible
  let uploadedUrl = null;
  try {
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('name', trackName);
    formData.append('genre', genre);
    formData.append('description', desc);
    formData.append('userId', user ? String(user.id) : 'guest');

    const resp = await fetch('/api/watt/upload', {
      method: 'POST',
      body: formData,
    });
    if (resp.ok) {
      const data = await resp.json();
      uploadedUrl = data.url || null;
    }
  } catch (e) {
    // Backend non disponible : mode local
    console.info('[WATT] Upload API non disponible — mode local');
  }

  // Sauvegarder les métadonnées dans localStorage
  const trackId = `watt-${Date.now()}-${Math.floor(Math.random() * 9999)}`;
  const userId  = user ? user.id : 'guest';

  const track = {
    id:          trackId,
    name:        trackName,
    genre:       genre || 'Non défini',
    description: desc,
    file:        selectedFile.name,
    sizeMB:      parseFloat((selectedFile.size / (1024 * 1024)).toFixed(1)),
    url:         uploadedUrl || null,
    userId,
    artistName:  profile?.artistName || user?.name || 'Artiste',
    plays:       0,
    uploadedAt:  Date.now(),
  };

  const wattTracks = getMyWattTracks(userId);
  wattTracks.unshift(track);
  saveMyWattTracks(userId, wattTracks);

  progressLabel.textContent = '✓ Publié sur WATT !';
  progressFill.style.background = 'linear-gradient(90deg, #44cc88, #00ff99)';

  setTimeout(() => {
    cancelUpload();
    renderMyTracks();
    updateStats();
    renderWattRanking();
    wattToast(`« ${trackName} » publié sur WATT ⚡`);
  }, 1200);
}

function simulateProgress(bar, from, to, duration) {
  return new Promise(resolve => {
    const steps = 20;
    const step  = (to - from) / steps;
    let current = from;
    const iv = setInterval(() => {
      current += step;
      bar.style.width = Math.min(current, to) + '%';
      if (current >= to) { clearInterval(iv); resolve(); }
    }, duration / steps);
  });
}

// ── 9. MES SONS ───────────────────────────────────────────────────────────────

function getMyWattTracks(userId) {
  return JSON.parse(localStorage.getItem(`smyle_watt_tracks_${userId}`) || '[]');
}

function saveMyWattTracks(userId, tracks) {
  localStorage.setItem(`smyle_watt_tracks_${userId}`, JSON.stringify(tracks));
}

// ── Gestion état zone upload (affiche ou masque selon limite) ────────────────
function renderUploadState() {
  const user   = getCurrentUser();
  const userId = user ? user.id : 'guest';
  const tracks = getMyWattTracks(userId);
  const count  = tracks.length;
  const limited = count >= FREE_LIMIT;

  // Compteur visuel
  const counterVal = document.getElementById('freeCounterVal');
  const barFill    = document.getElementById('freeBarFill');
  if (counterVal) {
    counterVal.textContent = limited
      ? 'Ta playlist est complète ✓'
      : `${count} / ${FREE_LIMIT} sons utilisés`;
    counterVal.style.color = limited ? '#FFD700' : '';
  }
  if (barFill) {
    const pct = Math.min((count / FREE_LIMIT) * 100, 100);
    barFill.style.width = pct + '%';
    barFill.style.background = limited
      ? 'linear-gradient(90deg, #FFD700, #FFEC6B)'
      : 'linear-gradient(90deg, rgba(255,215,0,.7), rgba(255,215,0,.4))';
  }

  // Zone upload vs teaser premium
  const uploadZone = document.getElementById('wattUploadZone');
  const teaser     = document.getElementById('wattPremiumTeaser');
  if (uploadZone) uploadZone.style.display = limited ? 'none' : '';
  if (teaser)     teaser.style.display     = limited ? '' : 'none';
}

function renderMyTracks() {
  const user    = getCurrentUser();
  const userId  = user ? user.id : 'guest';
  const tracks  = getMyWattTracks(userId);
  const listEl  = document.getElementById('myTracksList');
  const countEl = document.getElementById('myTracksCount');

  // Compteur dans l'en-tête du panel "Mes Sons"
  if (countEl) {
    const limited = tracks.length >= FREE_LIMIT;
    countEl.textContent = tracks.length + ' / ' + FREE_LIMIT + ' son' + (tracks.length > 1 ? 's' : '');
    countEl.style.color = limited ? '#FFD700' : '';
  }

  // Mise à jour du compteur freemium
  renderUploadState();

  if (!tracks.length) {
    listEl.innerHTML = `
      <div class="watt-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="36" height="36" style="opacity:.25">
          <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
        </svg>
        <p>Aucun son publié pour l'instant.<br>Upload ton premier morceau pour créer ta playlist artiste.</p>
      </div>`;
    return;
  }

  listEl.innerHTML = tracks.map((t, i) => `
    <div class="watt-track-item">
      <span class="watt-track-num">${String(i + 1).padStart(2, '0')}</span>
      <div class="watt-track-info">
        <div class="watt-track-name">${t.name}</div>
        <div class="watt-track-meta">${t.genre}${t.sizeMB ? ' · ' + t.sizeMB + ' MB' : ''} · ${new Date(t.uploadedAt).toLocaleDateString('fr')}</div>
      </div>
      <div class="watt-track-plays">${fmtPlaysW(t.plays)} ▶</div>
      <button class="watt-track-del" onclick="deleteTrack('${t.id}')" title="Retirer">✕</button>
    </div>
  `).join('');
}

function deleteTrack(trackId) {
  const user = getCurrentUser();
  const userId = user ? user.id : 'guest';
  let tracks = getMyWattTracks(userId);
  tracks = tracks.filter(t => t.id !== trackId);
  saveMyWattTracks(userId, tracks);
  renderMyTracks();
  updateStats();
  renderWattRanking();
  wattToast('Son retiré.');
}

// ── 10. STATS ─────────────────────────────────────────────────────────────────

function updateStats() {
  const user   = getCurrentUser();
  const userId = user ? user.id : 'guest';
  const tracks = getMyWattTracks(userId);

  const totalPlays  = tracks.reduce((s, t) => s + (t.plays || 0), 0);
  const totalTracks = tracks.length;
  const followers   = parseInt(localStorage.getItem(`smyle_watt_followers_${userId}`) || '0');

  setEl('statTotalPlays',  fmtPlaysW(totalPlays));
  setEl('statTotalTracks', String(totalTracks));
  setEl('statFollowers',   String(followers));

  // Calcul rang
  const ranking = computeMyRank(userId, totalPlays, followers);
  setEl('statRanking', ranking ? '#' + ranking : '—');
}

function computeMyRank(userId, myPlays, myFollowers) {
  const allUsers  = getUsers();
  const scores = allUsers.map(u => {
    const tracks    = getMyWattTracks(u.id);
    const plays     = tracks.reduce((s, t) => s + (t.plays || 0), 0);
    const followers = parseInt(localStorage.getItem(`smyle_watt_followers_${u.id}`) || '0');
    return { userId: u.id, plays, followers };
  }).filter(u => u.plays > 0 || u.followers > 0);

  scores.sort((a, b) => b.plays - a.plays || b.followers - a.followers);
  const idx = scores.findIndex(s => s.userId === userId);
  return idx >= 0 ? idx + 1 : null;
}

// ── 11. CLASSEMENT WATT ───────────────────────────────────────────────────────

function renderWattRanking() {
  const listEl = document.getElementById('wattRankingList');
  if (!listEl) return;

  const allUsers = getUsers();
  const artistData = allUsers.map(u => {
    const tracks    = getMyWattTracks(u.id);
    if (!tracks.length) return null;
    const profile   = JSON.parse(localStorage.getItem(`smyle_watt_profile_${u.id}`) || 'null');
    const plays     = tracks.reduce((s, t) => s + (t.plays || 0), 0);
    const followers = parseInt(localStorage.getItem(`smyle_watt_followers_${u.id}`) || '0');
    return {
      name:       profile?.artistName || u.name,
      plays,
      followers,
      trackCount: tracks.length,
    };
  }).filter(Boolean);

  // Trier : écoutes d'abord, puis abonnés
  artistData.sort((a, b) => b.plays - a.plays || b.followers - a.followers);

  if (!artistData.length) {
    listEl.innerHTML = `
      <div class="watt-empty" style="padding:28px">
        <p>Aucun artiste dans le classement pour l'instant.<br>Publie des sons pour y apparaître.</p>
      </div>`;
    return;
  }

  listEl.innerHTML = artistData.map((a, i) => `
    <div class="watt-rank-item rank-${i < 3 ? i + 1 : 'other'}">
      <span class="watt-rank-num">${String(i + 1).padStart(2, '0')}</span>
      <div class="watt-rank-info">
        <div class="watt-rank-name">${a.name}</div>
        <div class="watt-rank-stats">${a.followers} abonnés · ${a.trackCount} son${a.trackCount > 1 ? 's' : ''}</div>
      </div>
      <div class="watt-rank-plays">${fmtPlaysW(a.plays)} ▶</div>
    </div>
  `).join('');
}

// ── 11b. CLASSEMENT PUBLIC — chargé depuis l'API ─────────────────────────────

async function renderPublicRanking() {
  const el = document.getElementById('wattPublicRankingList');
  if (!el) return;

  // Skeleton pendant le chargement
  el.innerHTML = `<div class="watt-loading">Chargement du classement…</div>`;

  let artistData = [];
  try {
    const res  = await fetch('/api/artists');
    const json = await res.json();
    artistData = json.artists || [];
  } catch (_) {
    // Fallback localStorage si API indisponible (dev sans DB)
    const allUsers = getUsers();
    artistData = allUsers.map(u => {
      const tracks  = getMyWattTracks(u.id);
      if (!tracks.length) return null;
      const profile = JSON.parse(safeStorage.getItem(`smyle_watt_profile_${u.id}`) || 'null');
      const plays   = tracks.reduce((s, t) => s + (t.plays || 0), 0);
      const name    = profile?.artistName || u.name;
      const slug    = profile?.slug || slugify(name);
      const genre   = profile?.genre || '';
      return { artistName: name, genre, plays, trackCount: tracks.length, slug };
    }).filter(Boolean).sort((a, b) => b.plays - a.plays);
  }

  if (!artistData.length) {
    el.innerHTML = `
      <div class="watt-empty-state">
        <div class="watt-empty-icon">🎵</div>
        <p class="watt-empty-title">Le classement est vide pour l'instant</p>
        <p class="watt-empty-sub">Sois le premier artiste à rejoindre WATT et à publier tes sons.</p>
      </div>`;
    return;
  }

  // Normaliser les champs (API retourne artistName, localStorage retourne name)
  const normalize = a => ({
    name:  a.artistName || a.name || '?',
    genre: a.genre || '',
    plays: a.plays || 0,
    trackCount: a.trackCount || 0,
    slug:  a.slug || '',
  });

  const data = artistData.map(normalize);
  const top3 = data.slice(0, 3);
  const rest = data.slice(3);

  const podiumLabel = ['', '🥇', '🥈', '🥉'];

  const podiumHtml = `<div class="wpr-podium">` + top3.map((a, i) => `
    <div class="wpr-card wpr-pos-${i + 1}"
         onclick="window.location.href='/artiste/${a.slug}'"
         role="button" tabindex="0"
         onkeydown="if(event.key==='Enter')window.location.href='/artiste/${a.slug}'">
      <div class="wpr-card-medal">${podiumLabel[i + 1]}</div>
      <div class="wpr-card-rank">${String(i + 1).padStart(2, '0')}</div>
      <div class="wpr-card-name">${a.name}</div>
      <div class="wpr-card-genre">${a.genre}</div>
      <div class="wpr-card-plays">${fmtPlaysW(a.plays)} <span class="wpr-card-plays-ico">▶</span></div>
    </div>
  `).join('') + `</div>`;

  const listHtml = rest.length ? `<div class="wpr-rest">` + rest.map((a, i) => `
    <div class="wpr-rest-item"
         onclick="window.location.href='/artiste/${a.slug}'"
         role="button" tabindex="0"
         onkeydown="if(event.key==='Enter')window.location.href='/artiste/${a.slug}'">
      <span class="wpr-rest-num">${String(i + 4).padStart(2, '0')}</span>
      <div class="wpr-rest-info">
        <span class="wpr-rest-name">${a.name}</span>
        <span class="wpr-rest-genre">${a.genre}</span>
      </div>
      <span class="wpr-rest-plays">${fmtPlaysW(a.plays)} ▶</span>
    </div>
  `).join('') + `</div>` : '';

  el.innerHTML = podiumHtml + listHtml;
}

// ── Helpers avatar ────────────────────────────────────────────────────────────

const _AVATAR_COLORS = [
  ['#7B2FFF','#A06AFF'], ['#FF6B35','#FF9E70'], ['#00C9A7','#4EFFD6'],
  ['#FF3A8C','#FF7AB8'], ['#2563EB','#5B91F4'], ['#D97706','#FBB53A'],
];
function _avatarColor(name) {
  let h = 0;
  for (let i = 0; i < (name || '').length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xFFFF;
  return _AVATAR_COLORS[h % _AVATAR_COLORS.length];
}
function _initials(name) {
  const parts = (name || '?').trim().split(/\s+/);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : (name || '?').slice(0, 2).toUpperCase();
}

// ── Derniers sons — chargés depuis l'API ──────────────────────────────────────

async function renderPublicTracks() {
  const el = document.getElementById('wattPublicRecentList');
  if (!el) return;

  el.innerHTML = `<div class="watt-loading">Chargement des sons…</div>`;

  let tracks = [];
  try {
    const res  = await fetch('/api/tracks/recent');
    const json = await res.json();
    tracks = (json.tracks || []).slice(0, 4);
  } catch (_) {
    // Fallback localStorage
    const allUsers = getUsers();
    let all = [];
    allUsers.forEach(u => {
      const uTracks = getMyWattTracks(u.id);
      const profile = JSON.parse(safeStorage.getItem(`smyle_watt_profile_${u.id}`) || 'null');
      const artist  = profile?.artistName || u.name;
      const slug    = profile?.slug || slugify(artist);
      uTracks.forEach(t => all.push({ ...t, artistName: artist, artistSlug: slug }));
    });
    all.sort((a, b) => (b.uploadedAt || 0) - (a.uploadedAt || 0));
    tracks = all.slice(0, 4);
  }

  if (!tracks.length) {
    el.innerHTML = `
      <div class="watt-empty-state">
        <div class="watt-empty-icon">🎧</div>
        <p class="watt-empty-title">Aucun son publié pour l'instant</p>
        <p class="watt-empty-sub">Les prochains sons d'artistes WATT apparaîtront ici.</p>
      </div>`;
    return;
  }

  const voirPlusBtn = `<a href="/watt" class="wpt-voir-plus">Voir plus →</a>`;

  el.innerHTML = `<div class="wpt-grid">` + tracks.map(t => {
    const artistName = t.artistName || '?';
    const slug       = t.artistSlug || t.slug || '';
    const d          = new Date(t.uploadedAt || Date.now());
    const dateStr    = d.toLocaleDateString('fr', { day: 'numeric', month: 'short' });
    const [c1, c2]   = _avatarColor(artistName);
    const ini        = _initials(artistName);
    return `
      <div class="wpt-card"
           onclick="window.location.href='/artiste/${slug}'"
           role="button" tabindex="0"
           onkeydown="if(event.key==='Enter')window.location.href='/artiste/${slug}'">
        <div class="wpt-card-top">
          <div class="wpt-avatar" style="background:linear-gradient(135deg,${c1},${c2})">${ini}</div>
          <div class="wpt-date-badge">${dateStr}</div>
        </div>
        <div class="wpt-track-name">${t.name || 'Sans titre'}</div>
        <div class="wpt-artist-name">${artistName}</div>
        <div class="wpt-genre-tag">${t.genre || ''}</div>
        <div class="wpt-card-footer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10" style="opacity:.4"><polygon points="5 3 19 12 5 21 5 3" fill="currentColor"/></svg>
          <span>Voir le profil</span>
        </div>
      </div>
    `;
  }).join('') + `</div>` + voirPlusBtn;
}

// ── 12. CANVAS RÉSEAU (panel visual) ─────────────────────────────────────────

let networkInstance = null;

function initNetworkCanvas() {
  const canvas = document.getElementById('watt-network-canvas');
  if (!canvas || networkInstance) return;
  networkInstance = new WattNetwork(canvas);
}

// ── 13. TOAST ─────────────────────────────────────────────────────────────────

function wattToast(msg) {
  const t = document.getElementById('watt-toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('visible');
  clearTimeout(t._tmr);
  t._tmr = setTimeout(() => t.classList.remove('visible'), 2800);
}

// ── 14. HELPERS ───────────────────────────────────────────────────────────────

function fmtPlaysW(n) {
  if (!n) return '0';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── 15. INIT ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Canvas fond page
  const bgCanvas = document.getElementById('watt-canvas');
  if (bgCanvas) new ElectricWebBg(bgCanvas);

  // État de la page
  renderPageState();

  // Fermeture modal auth sur clic overlay
  document.getElementById('wattAuthModal').addEventListener('click', e => {
    if (e.target === document.getElementById('wattAuthModal')) closeWattAuthModal();
  });

  // Raccourci Escape
  document.addEventListener('keydown', e => {
    if (e.code === 'Escape') closeWattAuthModal();
  });
});
