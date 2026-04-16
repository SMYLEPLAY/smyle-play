/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/panels/watt-panel.js
   WATT Panel — DNA + CONNECT + ARTIST (hub central)

   Remplace l'ancien Control Center (ui/panels/agent.js).
   Lit le state partagé de ui/core/state.js : PLAYLISTS, loadTrack, openPlaylist.
   ───────────────────────────────────────────────────────────────────────── */

'use strict';

// ══════════════════════════════════════════════════════════════════════════
//  CONSTANTS — Couleurs alignées sur le site
// ══════════════════════════════════════════════════════════════════════════

const WATT = {
  colors: {
    sunset:  { hex: '#FF9500', rgb: '255,149,0',    label: 'Sunset Lover',  key: 'sunset-lover' },
    jungle:  { hex: '#00E676', rgb: '0,230,118',    label: 'Jungle Osmose', key: 'jungle-osmose' },
    night:   { hex: '#2266FF', rgb: '34,102,255',   label: 'Night City',    key: 'night-city' },
    hitmix:  { hex: '#AA00FF', rgb: '170,0,255',    label: 'Hit Mix',       key: 'hit-mix' },
  },
  connect: { hex: '#FF1744', rgb: '255,23,68' },
  artist:  { hex: '#FFD700', rgb: '255,215,0' },
  violet:  '#8800ff',
};

const WATT_UNIVERSES = ['sunset', 'jungle', 'night', 'hitmix'];

// Émotions rapides mappées aux univers
const EMOTION_MAP = {
  // Sunset Lover — chaleur, soleil, détente
  'Chill':     { universe: 'sunset', weight: .9 },
  'Sunset':    { universe: 'sunset', weight: 1 },
  'Détente':   { universe: 'sunset', weight: .85 },
  'Été':       { universe: 'sunset', weight: .8 },
  'Romance':   { universe: 'sunset', weight: .75 },
  'Groove':    { universe: 'sunset', weight: .7 },
  // Jungle Osmose — nature, énergie, tribal
  'Énergie':   { universe: 'jungle', weight: .9 },
  'Tropical':  { universe: 'jungle', weight: 1 },
  'Danse':     { universe: 'jungle', weight: .85 },
  'Festival':  { universe: 'jungle', weight: .8 },
  'Tribal':    { universe: 'jungle', weight: .75 },
  // Night City — nuit, mélancolie, urbain
  'Mélancolie':{ universe: 'night', weight: .9 },
  'Nuit':      { universe: 'night', weight: 1 },
  'Urbain':    { universe: 'night', weight: .85 },
  'Introspection': { universe: 'night', weight: .8 },
  'Jazz':      { universe: 'night', weight: .75 },
  // Hit Mix — éclectique, explosif
  'Explosif':  { universe: 'hitmix', weight: .9 },
  'Mix':       { universe: 'hitmix', weight: 1 },
  'Surprise':  { universe: 'hitmix', weight: .85 },
  'Éclectique':{ universe: 'hitmix', weight: .8 },
};

// ══════════════════════════════════════════════════════════════════════════
//  STATE
// ══════════════════════════════════════════════════════════════════════════

const _watt = {
  activeTab: 'dna',
  dnaResult: null,
  dnaCanvas: null,
  dnaCtx: null,
  connectCanvas: null,
  connectCtx: null,
  dnaNodes: [],
  connectNodes: [],
  dnaAnim: null,
  connectAnim: null,
};

// ══════════════════════════════════════════════════════════════════════════
//  OPEN / CLOSE / TOGGLE
// ══════════════════════════════════════════════════════════════════════════

function openWattPanel() {
  closePanel();
  closeMixPanel();
  // Close old agent panel if it exists
  const oldPanel = document.getElementById('agentPanel');
  if (oldPanel) oldPanel.classList.remove('open');

  const panel = document.getElementById('wattPanel');
  if (!panel) return;
  panel.classList.add('open');
  document.getElementById('overlay').classList.add('show');

  // Init the active tab
  _wattRenderTab(_watt.activeTab);
}

function closeWattPanel() {
  const panel = document.getElementById('wattPanel');
  if (!panel) return;
  panel.classList.remove('open');

  // Stop animations
  if (_watt.dnaAnim) { cancelAnimationFrame(_watt.dnaAnim); _watt.dnaAnim = null; }
  if (_watt.connectAnim) { cancelAnimationFrame(_watt.connectAnim); _watt.connectAnim = null; }

  const trackOpen = document.getElementById('trackPanel')?.classList.contains('open');
  const mixOpen = document.getElementById('mixPanel')?.classList.contains('open');
  if (!trackOpen && !mixOpen) {
    document.getElementById('overlay').classList.remove('show');
  }
}

function toggleWattPanel() {
  const panel = document.getElementById('wattPanel');
  if (!panel) return;
  panel.classList.contains('open') ? closeWattPanel() : openWattPanel();
}

// ══════════════════════════════════════════════════════════════════════════
//  TAB SWITCHING
// ══════════════════════════════════════════════════════════════════════════

function wattTab(tabKey) {
  _watt.activeTab = tabKey;
  document.querySelectorAll('.watt-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabKey);
  });
  _wattRenderTab(tabKey);
}

function _wattRenderTab(tabKey) {
  const body = document.getElementById('watt-body');
  if (!body) return;

  // Stop all animations when switching tabs
  if (_watt.dnaAnim) { cancelAnimationFrame(_watt.dnaAnim); _watt.dnaAnim = null; }
  if (_watt.connectAnim) { cancelAnimationFrame(_watt.connectAnim); _watt.connectAnim = null; }

  if (tabKey === 'dna') {
    _renderDNATab(body);
  } else if (tabKey === 'connect') {
    _renderConnectTab(body);
  } else if (tabKey === 'artist') {
    _renderArtistTab(body);
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  DNA TAB — Recommandation musicale
// ══════════════════════════════════════════════════════════════════════════

function _renderDNATab(container) {
  const emotionChips = Object.keys(EMOTION_MAP).map(e =>
    `<button class="dna-emotion-chip" onclick="_dnaQuickEmotion('${e}')">${e}</button>`
  ).join('');

  let resultHTML = '';
  if (_watt.dnaResult) {
    resultHTML = _buildDNAResultHTML(_watt.dnaResult);
  }

  container.innerHTML = `
    <div class="dna-canvas-wrap">
      <canvas id="dna-mini-canvas"></canvas>
      <div class="dna-dice-wrap">
        <button class="dna-dice-btn" onclick="_dnaRollDice()" title="Recommandation aléatoire">
          <svg id="dna-dice-svg" viewBox="0 0 100 100"></svg>
        </button>
      </div>
    </div>
    <div class="dna-form">
      <input class="dna-input" id="dna-emotion-input" type="text"
             placeholder="Décris ton mood… (ex: nuit calme, énergie tropicale)"
             onkeydown="if(event.key==='Enter'){_dnaAnalyze();}" />
      <button class="dna-submit" onclick="_dnaAnalyze()">Analyser</button>
    </div>
    <div class="dna-quick-emotions">${emotionChips}</div>
    <div id="dna-result-zone">${resultHTML}</div>
  `;

  // Init canvas
  requestAnimationFrame(() => {
    _initDNACanvas();
    _drawDice();
  });
}

// ── DNA Canvas (particules des 4 univers) ─────────────────────────────────

function _initDNACanvas() {
  const c = document.getElementById('dna-mini-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  const rect = c.parentElement.getBoundingClientRect();
  c.width = rect.width * 2;
  c.height = rect.height * 2;
  ctx.scale(2, 2);
  _watt.dnaCanvas = c;
  _watt.dnaCtx = ctx;

  const w = rect.width, h = rect.height;

  // Create nodes for each universe
  _watt.dnaNodes = [];
  WATT_UNIVERSES.forEach((u, ui) => {
    const col = WATT.colors[u];
    const cx = (ui + 0.5) * (w / 4);
    for (let i = 0; i < 8; i++) {
      _watt.dnaNodes.push({
        x: cx + (Math.random() - 0.5) * (w / 5),
        y: h * 0.2 + Math.random() * h * 0.6,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: 2 + Math.random() * 3,
        universe: u,
        color: col.hex,
        rgb: col.rgb,
      });
    }
  });

  _animDNA(w, h);
}

function _animDNA(w, h) {
  const ctx = _watt.dnaCtx;
  if (!ctx) return;

  ctx.clearRect(0, 0, w, h);

  // Update + draw connections
  const nodes = _watt.dnaNodes;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    n.x += n.vx;
    n.y += n.vy;
    if (n.x < 0 || n.x > w) n.vx *= -1;
    if (n.y < 0 || n.y > h) n.vy *= -1;
    n.x = Math.max(0, Math.min(w, n.x));
    n.y = Math.max(0, Math.min(h, n.y));

    // Connections to nearby same-universe nodes
    for (let j = i + 1; j < nodes.length; j++) {
      const m = nodes[j];
      const dx = n.x - m.x, dy = n.y - m.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const maxDist = n.universe === m.universe ? 100 : 60;
      if (dist < maxDist) {
        const alpha = n.universe === m.universe
          ? 0.15 + (1 - dist / maxDist) * 0.35
          : 0.04 + (1 - dist / maxDist) * 0.08;
        const lw = n.universe === m.universe
          ? 0.6 + (1 - dist / maxDist) * 1.5
          : 0.3;

        // Bezier curve
        const mx = (n.x + m.x) / 2 + (Math.random() - 0.5) * 8;
        const my = (n.y + m.y) / 2 + (Math.random() - 0.5) * 8;

        ctx.beginPath();
        ctx.moveTo(n.x, n.y);
        ctx.quadraticCurveTo(mx, my, m.x, m.y);
        ctx.strokeStyle = `rgba(${n.rgb},${alpha})`;
        ctx.lineWidth = lw;
        ctx.stroke();
      }
    }
  }

  // Draw nodes
  for (const n of nodes) {
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
    ctx.fillStyle = n.color;
    ctx.globalAlpha = 0.7;
    ctx.fill();
    ctx.globalAlpha = 1;

    // Glow
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r + 4, 0, Math.PI * 2);
    const grd = ctx.createRadialGradient(n.x, n.y, n.r, n.x, n.y, n.r + 6);
    grd.addColorStop(0, `rgba(${n.rgb},.2)`);
    grd.addColorStop(1, 'transparent');
    ctx.fillStyle = grd;
    ctx.fill();
  }

  _watt.dnaAnim = requestAnimationFrame(() => _animDNA(w, h));
}

// ── Dice (3D isometric, playlist colors) ──────────────────────────────────

function _drawDice() {
  const svg = document.getElementById('dna-dice-svg');
  if (!svg) return;

  const c = WATT.colors;
  svg.innerHTML = `
    <!-- Top face — Sunset orange -->
    <polygon points="50,15 85,35 50,55 15,35" fill="${c.sunset.hex}" opacity="0.85"/>
    <polygon points="50,15 85,35 50,55 15,35" fill="url(#diceTopGrad)" opacity="0.3"/>
    <!-- Left face — Night blue -->
    <polygon points="15,35 50,55 50,90 15,70" fill="${c.night.hex}" opacity="0.7"/>
    <!-- Right face — Jungle green -->
    <polygon points="85,35 50,55 50,90 85,70" fill="${c.jungle.hex}" opacity="0.6"/>
    <!-- "D" letter — HitMix violet with glow -->
    <defs>
      <linearGradient id="diceTopGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#fff" stop-opacity="0.3"/>
        <stop offset="1" stop-color="#000" stop-opacity="0.1"/>
      </linearGradient>
      <filter id="diceGlow">
        <feGaussianBlur stdDeviation="2" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    <text x="50" y="59" text-anchor="middle" dominant-baseline="central"
          font-family="'Helvetica Neue',Helvetica,Arial,sans-serif"
          font-size="20" font-weight="900" letter-spacing="1"
          fill="${c.hitmix.hex}" filter="url(#diceGlow)">D</text>
    <!-- Edge highlights -->
    <line x1="50" y1="15" x2="85" y2="35" stroke="rgba(255,255,255,.15)" stroke-width="0.5"/>
    <line x1="50" y1="15" x2="15" y2="35" stroke="rgba(255,255,255,.12)" stroke-width="0.5"/>
    <line x1="15" y1="35" x2="15" y2="70" stroke="rgba(255,255,255,.06)" stroke-width="0.5"/>
    <line x1="85" y1="35" x2="85" y2="70" stroke="rgba(255,255,255,.06)" stroke-width="0.5"/>
  `;
}

// ── DNA Analysis ──────────────────────────────────────────────────────────

function _dnaQuickEmotion(emotion) {
  const input = document.getElementById('dna-emotion-input');
  if (input) input.value = emotion;
  _dnaAnalyze();
}

function _dnaRollDice() {
  // Random universe pick with animation
  const btn = document.querySelector('.dna-dice-btn');
  if (btn) {
    btn.style.transform = 'scale(.85) rotate(360deg)';
    setTimeout(() => { btn.style.transform = ''; }, 400);
  }

  // Pick random emotion
  const emotions = Object.keys(EMOTION_MAP);
  const pick = emotions[Math.floor(Math.random() * emotions.length)];
  const input = document.getElementById('dna-emotion-input');
  if (input) input.value = pick;
  setTimeout(() => _dnaAnalyze(), 300);
}

function _dnaAnalyze() {
  const input = document.getElementById('dna-emotion-input');
  const query = (input?.value || '').trim();
  if (!query) return;

  // Score each universe
  const scores = { sunset: 0, jungle: 0, night: 0, hitmix: 0 };
  const words = query.toLowerCase().split(/[\s,;.!?]+/);

  // Match against emotion map
  for (const [emotion, data] of Object.entries(EMOTION_MAP)) {
    for (const word of words) {
      if (emotion.toLowerCase().includes(word) || word.includes(emotion.toLowerCase())) {
        scores[data.universe] += data.weight;
      }
    }
  }

  // Keyword matching fallback
  const kw = {
    sunset:  ['soleil','chaleur','plage','chill','relax','été','warm','sun','beach','groove','deep','house','disco','cocktail','doux','calm','soir'],
    jungle:  ['jungle','tropical','afro','beat','énergie','danse','dance','festival','tribal','reggae','island','carib','latin','rumba','salsa','bongo'],
    night:   ['nuit','night','jazz','soul','lofi','lo-fi','mélancolie','pluie','rain','city','urban','piano','froid','dark','blue','introspect','calm','smoke'],
    hitmix:  ['mix','hit','best','eclectique','surprise','boom','party','fire','top','electro','drop','bass','trap','hype','energy','explos'],
  };

  for (const [u, keywords] of Object.entries(kw)) {
    for (const word of words) {
      for (const k of keywords) {
        if (word.includes(k) || k.includes(word)) {
          scores[u] += 0.5;
        }
      }
    }
  }

  // If no match, add small random scores
  const total = Object.values(scores).reduce((a, b) => a + b, 0);
  if (total < 0.1) {
    WATT_UNIVERSES.forEach(u => { scores[u] = 0.2 + Math.random() * 0.6; });
  }

  // Normalize to percentages
  const sum = Object.values(scores).reduce((a, b) => a + b, 0);
  const pcts = {};
  let winner = 'sunset';
  let maxScore = 0;
  for (const u of WATT_UNIVERSES) {
    pcts[u] = Math.round((scores[u] / sum) * 100);
    if (scores[u] > maxScore) { maxScore = scores[u]; winner = u; }
  }

  // Get tracks from real playlists
  const playlistKey = WATT.colors[winner].key;
  const pl = PLAYLISTS[playlistKey];
  let tracks = [];
  if (pl && pl.tracks) {
    // Pick 5 random tracks
    const shuffled = [...pl.tracks].sort(() => Math.random() - 0.5);
    tracks = shuffled.slice(0, 5);
  }

  // Build result
  _watt.dnaResult = {
    query,
    winner,
    pcts,
    tracks,
    playlistKey,
    mood: _getMoodDescription(winner, query),
    sunoPrompt: _buildSunoPrompt(winner, query),
  };

  // Render
  const zone = document.getElementById('dna-result-zone');
  if (zone) {
    zone.innerHTML = _buildDNAResultHTML(_watt.dnaResult);
  }

  // Highlight winning nodes on canvas
  _watt.dnaNodes.forEach(n => {
    if (n.universe === winner) {
      n.r = 4 + Math.random() * 3;
    } else {
      n.r = 2 + Math.random() * 2;
    }
  });
}

function _getMoodDescription(universe, query) {
  const moods = {
    sunset:  `"${query}" évoque un coucher de soleil, des vibrations deep house et nu-disco. Laisse-toi porter par les ondes dorées.`,
    jungle:  `"${query}" résonne avec les rythmes tropicaux et l'énergie afrobeat. La jungle t'appelle.`,
    night:   `"${query}" te guide vers les ruelles nocturnes, entre jazz et soul. La ville respire à ton rythme.`,
    hitmix:  `"${query}" est un concentré d'éclectisme. Le meilleur du lab, sans frontières.`,
  };
  return moods[universe] || moods.hitmix;
}

function _buildSunoPrompt(universe, query) {
  const prompts = {
    sunset:  `Deep house mélodique, nu-disco, groove ensoleillé. Ambiance ${query}. Synthés chauds, basse ronde, hi-hats délicats, pad atmosphérique. Tempo 118-124 BPM. Feeling Sunset Lover.`,
    jungle:  `Afrobeat tropical, dancehall, reggaeton fusion. Énergie ${query}. Percussions organiques, steel drums, basse rebondissante, chœurs lointains. Tempo 95-110 BPM. Feeling Jungle Osmose.`,
    night:   `Lo-fi jazz, neo-soul, ambient nocturne. Atmosphère ${query}. Piano Rhodes, contrebasse feutrée, vinyle crackle, pads brumeux. Tempo 70-85 BPM. Feeling Night City.`,
    hitmix:  `Electro-pop, future bass, crossover. Mood ${query}. Drops percutants, synthés brillants, bass design, build-ups cinématiques. Tempo 125-140 BPM. Feeling Hit Mix.`,
  };
  return prompts[universe] || prompts.hitmix;
}

function _buildDNAResultHTML(result) {
  if (!result) return '';

  const col = WATT.colors[result.winner];

  // Score bars
  let scoreBars = '';
  for (const u of WATT_UNIVERSES) {
    const c = WATT.colors[u];
    const isWinner = u === result.winner;
    scoreBars += `
      <div class="dna-score-row ${isWinner ? 'winner' : ''}">
        <span class="dna-score-label" style="color:${isWinner ? c.hex : ''}">${c.label}</span>
        <div class="dna-score-bar-wrap">
          <div class="dna-score-bar ${u}" style="width:${result.pcts[u]}%"></div>
        </div>
        <span class="dna-score-pct">${result.pcts[u]}%</span>
      </div>`;
  }

  // Track list
  let trackItems = '';
  if (result.tracks && result.tracks.length) {
    trackItems = result.tracks.map((t, i) => {
      const dur = t.duration ? `${Math.floor(t.duration / 60)}:${String(Math.floor(t.duration % 60)).padStart(2, '0')}` : '';
      return `
        <div class="dna-track-row" onclick="_dnaPlayTrack('${result.playlistKey}', ${i})">
          <div class="dna-track-play-icon ${result.winner}">▶</div>
          <div class="dna-track-info">
            <div class="dna-track-name">${_esc(t.name || t.file)}</div>
            <div class="dna-track-meta">${col.label}</div>
          </div>
          <span class="dna-track-dur">${dur}</span>
        </div>`;
    }).join('');
  }

  return `
    <div class="dna-result">
      <div class="dna-result-badge ${result.winner}">${col.label}</div>
      <div class="dna-result-mood">${result.mood}</div>
      <div class="dna-scores">${scoreBars}</div>
    </div>
    ${trackItems ? `
      <div class="dna-tracks-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="${col.hex}" stroke-width="1.8" width="12" height="12">
          <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
        </svg>
        Écouter maintenant
      </div>
      <div class="dna-track-list">${trackItems}</div>
    ` : ''}
    <div class="dna-suno-box">
      <div class="dna-suno-label">Prompt Suno généré</div>
      <div class="dna-suno-prompt">${_esc(result.sunoPrompt)}</div>
      <button class="dna-suno-copy" onclick="_dnaCopyPrompt()">Copier</button>
    </div>
  `;
}

function _dnaPlayTrack(playlistKey, idx) {
  // Find the track in the real PLAYLISTS data and play it
  const pl = PLAYLISTS[playlistKey];
  if (!pl || !pl.tracks) return;

  // The idx here is relative to the shuffled subset — find real index
  const result = _watt.dnaResult;
  if (!result || !result.tracks[idx]) return;

  const track = result.tracks[idx];
  // Find real index in playlist
  const realIdx = pl.tracks.findIndex(t => t.id === track.id || t.file === track.file);
  if (realIdx >= 0) {
    loadTrack(playlistKey, realIdx);
    showPlayerUI();
  }
}

function _dnaCopyPrompt() {
  if (!_watt.dnaResult) return;
  navigator.clipboard.writeText(_watt.dnaResult.sunoPrompt).then(() => {
    const btn = document.querySelector('.dna-suno-copy');
    if (btn) { btn.textContent = 'Copié ✓'; setTimeout(() => { btn.textContent = 'Copier'; }, 2000); }
  }).catch(() => {});
}

// ══════════════════════════════════════════════════════════════════════════
//  CONNECT TAB — Réseau créatif rouge néon
// ══════════════════════════════════════════════════════════════════════════

function _renderConnectTab(container) {
  const categories = ['Beatmakers', 'Voix', 'Musiciens', 'Vidéastes', 'Visuels', 'Ingénieurs son', 'Topliners', 'Compositeurs'];
  const catChips = categories.map(c =>
    `<span class="connect-cat-chip">${c}</span>`
  ).join('');

  container.innerHTML = `
    <div class="connect-canvas-wrap">
      <canvas id="connect-mini-canvas"></canvas>
    </div>
    <div class="connect-stats">
      <div class="connect-stat-card">
        <div class="connect-stat-val" id="connect-artists">0</div>
        <div class="connect-stat-lbl">Artistes</div>
      </div>
      <div class="connect-stat-card">
        <div class="connect-stat-val" id="connect-collabs">0</div>
        <div class="connect-stat-lbl">Collabs</div>
      </div>
      <div class="connect-stat-card">
        <div class="connect-stat-val" id="connect-online">0</div>
        <div class="connect-stat-lbl">En ligne</div>
      </div>
    </div>
    <div class="connect-empty">
      <div class="connect-empty-title">La toile attend ses créateurs</div>
      <div class="connect-empty-sub">
        CONNECT est le réseau collaboratif de SMYLE PLAY.<br>
        Rejoins WATT pour te connecter avec d'autres artistes.
      </div>
      <div class="connect-categories">${catChips}</div>
      <div class="connect-cta">
        <a href="/watt" class="connect-cta-btn">
          <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          Rejoindre WATT
        </a>
        <span class="connect-cta-note">Bêta gratuite · Accès libre</span>
      </div>
    </div>
  `;

  // Fetch community stats
  _fetchConnectStats();

  // Init canvas
  requestAnimationFrame(() => _initConnectCanvas());
}

function _fetchConnectStats() {
  fetch('/api/watt/stats').then(r => r.json()).then(d => {
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    el('connect-artists', d.artists || 0);
    el('connect-collabs', d.collabs || 0);
    el('connect-online', d.online || 0);
  }).catch(() => {});
}

// ── Connect Canvas (réseau rouge néon) ────────────────────────────────────

function _initConnectCanvas() {
  const c = document.getElementById('connect-mini-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  const rect = c.parentElement.getBoundingClientRect();
  c.width = rect.width * 2;
  c.height = rect.height * 2;
  ctx.scale(2, 2);
  _watt.connectCanvas = c;
  _watt.connectCtx = ctx;

  const w = rect.width, h = rect.height;

  // Ghost nodes (empty state)
  _watt.connectNodes = [];
  for (let i = 0; i < 20; i++) {
    _watt.connectNodes.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: 2 + Math.random() * 3,
      pulse: Math.random() * Math.PI * 2,
    });
  }

  _animConnect(w, h);
}

function _animConnect(w, h) {
  const ctx = _watt.connectCtx;
  if (!ctx) return;

  const rgb = WATT.connect.rgb;
  ctx.clearRect(0, 0, w, h);

  const nodes = _watt.connectNodes;
  const t = Date.now() * 0.001;

  // Update and draw connections
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    n.x += n.vx;
    n.y += n.vy;
    if (n.x < 0 || n.x > w) n.vx *= -1;
    if (n.y < 0 || n.y > h) n.vy *= -1;
    n.x = Math.max(0, Math.min(w, n.x));
    n.y = Math.max(0, Math.min(h, n.y));

    for (let j = i + 1; j < nodes.length; j++) {
      const m = nodes[j];
      const dx = n.x - m.x, dy = n.y - m.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 80) {
        const alpha = 0.08 + (1 - dist / 80) * 0.2;
        const mx = (n.x + m.x) / 2 + Math.sin(t + i) * 5;
        const my = (n.y + m.y) / 2 + Math.cos(t + j) * 5;
        ctx.beginPath();
        ctx.moveTo(n.x, n.y);
        ctx.quadraticCurveTo(mx, my, m.x, m.y);
        ctx.strokeStyle = `rgba(${rgb},${alpha})`;
        ctx.lineWidth = 0.6 + (1 - dist / 80) * 1;
        ctx.stroke();
      }
    }
  }

  // Draw nodes
  for (const n of nodes) {
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.5 + n.pulse);
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r * (0.8 + pulse * 0.4), 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${rgb},${0.3 + pulse * 0.3})`;
    ctx.fill();

    // Glow
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r + 5, 0, Math.PI * 2);
    const grd = ctx.createRadialGradient(n.x, n.y, n.r, n.x, n.y, n.r + 6);
    grd.addColorStop(0, `rgba(${rgb},${0.1 + pulse * 0.1})`);
    grd.addColorStop(1, 'transparent');
    ctx.fillStyle = grd;
    ctx.fill();
  }

  // Center pulse (the "heart" of the network)
  const cx = w / 2, cy = h / 2;
  const pr = 6 + Math.sin(t * 2) * 3;
  ctx.beginPath();
  ctx.arc(cx, cy, pr, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(${rgb},${0.4 + Math.sin(t * 2) * 0.2})`;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(cx, cy, pr + 12, 0, Math.PI * 2);
  const grd = ctx.createRadialGradient(cx, cy, pr, cx, cy, pr + 15);
  grd.addColorStop(0, `rgba(${rgb},.15)`);
  grd.addColorStop(1, 'transparent');
  ctx.fillStyle = grd;
  ctx.fill();

  _watt.connectAnim = requestAnimationFrame(() => _animConnect(w, h));
}

// ══════════════════════════════════════════════════════════════════════════
//  ARTIST TAB — Espace artiste · PLUG WATT
// ══════════════════════════════════════════════════════════════════════════

// SVG inline : prise électrique néon
const _PLUG_SVG = `<svg class="artist-plug-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="plugGlow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="plugGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFE44D" stop-opacity="0.9"/>
      <stop offset="1" stop-color="#FFD700" stop-opacity="0.7"/>
    </linearGradient>
  </defs>
  <!-- Corps de la prise -->
  <rect x="28" y="32" width="44" height="38" rx="6" fill="none" stroke="url(#plugGrad)" stroke-width="2.5" filter="url(#plugGlow)"/>
  <!-- Deux broches -->
  <rect x="38" y="14" width="6" height="22" rx="3" fill="#FFD700" opacity="0.8" filter="url(#plugGlow)"/>
  <rect x="56" y="14" width="6" height="22" rx="3" fill="#FFD700" opacity="0.8" filter="url(#plugGlow)"/>
  <!-- Câble (en bas) -->
  <path d="M50 70 Q50 82 50 90" stroke="#FFD700" stroke-width="2.5" fill="none" opacity="0.5" stroke-linecap="round"/>
  <!-- Cercle intérieur (terre) -->
  <circle cx="50" cy="51" r="5" fill="none" stroke="#FFD700" stroke-width="1.5" opacity="0.4"/>
  <!-- Arcs d'énergie -->
  <path d="M22 45 Q18 51 22 57" stroke="#FFE44D" stroke-width="1.2" fill="none" opacity="0.3" stroke-linecap="round"/>
  <path d="M16 42 Q10 51 16 60" stroke="#FFE44D" stroke-width="1" fill="none" opacity="0.2" stroke-linecap="round"/>
  <path d="M78 45 Q82 51 78 57" stroke="#FFE44D" stroke-width="1.2" fill="none" opacity="0.3" stroke-linecap="round"/>
  <path d="M84 42 Q90 51 84 60" stroke="#FFE44D" stroke-width="1" fill="none" opacity="0.2" stroke-linecap="round"/>
</svg>`;

function _renderArtistTab(container) {
  // Check if user seems logged in (look for user badge in header)
  const userBadge = document.querySelector('.user-badge');
  const isLoggedIn = !!userBadge;

  // Try to get artist stats from WATT
  const statsHTML = `
    <div class="artist-stats">
      <div class="artist-stat-card">
        <div class="artist-stat-val" id="artist-tracks">—</div>
        <div class="artist-stat-lbl">Sons</div>
      </div>
      <div class="artist-stat-card">
        <div class="artist-stat-val" id="artist-plays">—</div>
        <div class="artist-stat-lbl">Écoutes</div>
      </div>
      <div class="artist-stat-card">
        <div class="artist-stat-val" id="artist-rank">—</div>
        <div class="artist-stat-lbl">Rang</div>
      </div>
    </div>
  `;

  // Menu items for the artist section
  const menuItems = [
    {
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
      name: 'Dashboard',
      desc: 'Gère tes sons, stats et profil',
      action: 'window.location.href="/dashboard"',
    },
    {
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
      name: 'Upload',
      desc: 'Publie un nouveau son',
      action: 'window.location.href="/dashboard#upload"',
    },
    {
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
      name: 'Profil',
      desc: 'Modifie ta bio, liens et style',
      action: 'window.location.href="/dashboard#profile"',
    },
    {
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
      name: 'Mes Sons',
      desc: 'Écouter et gérer ta discographie',
      action: 'window.location.href="/dashboard#tracks"',
    },
    {
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
      name: 'Statistiques',
      desc: 'Écoutes, abonnés, évolution',
      action: 'window.location.href="/dashboard#stats"',
    },
  ];

  const menuHTML = menuItems.map(m => `
    <div class="artist-menu-item" onclick="${m.action}">
      <div class="artist-menu-icon">${m.icon}</div>
      <div class="artist-menu-info">
        <div class="artist-menu-name">${m.name}</div>
        <div class="artist-menu-desc">${m.desc}</div>
      </div>
      <span class="artist-menu-arrow">›</span>
    </div>
  `).join('');

  if (isLoggedIn) {
    // Connected state
    container.innerHTML = `
      <div class="artist-plug-hero">
        ${_PLUG_SVG}
        <div class="artist-plug-title">PLUG WATT</div>
        <div class="artist-plug-sub">Espace Artiste</div>
      </div>
      ${statsHTML}
      <div class="artist-menu">${menuHTML}</div>
    `;
    // Fetch stats
    _fetchArtistStats();
  } else {
    // Not connected — auth gate
    const features = [
      { icon: '🎵', text: 'Upload tes créations sur la plateforme' },
      { icon: '⚡', text: 'Apparais dans le classement mondial WATT' },
      { icon: '📊', text: 'Suis tes écoutes et ton audience' },
      { icon: '🎛️', text: 'Crée ton profil artiste public' },
      { icon: '🤝', text: 'Reçois des demandes de collaboration' },
    ];

    const featHTML = features.map(f => `
      <div class="artist-gate-feat">
        <span class="artist-gate-feat-icon">${f.icon}</span>
        <span class="artist-gate-feat-text">${f.text}</span>
      </div>
    `).join('');

    container.innerHTML = `
      <div class="artist-plug-hero">
        ${_PLUG_SVG}
        <div class="artist-plug-title">PLUG WATT</div>
        <div class="artist-plug-sub">World Artist Ties Talent</div>
      </div>
      <div class="artist-gate">
        <div class="artist-gate-title">Branche-toi sur WATT</div>
        <div class="artist-gate-desc">
          Publie ta musique, crée ton profil artiste<br>
          et rejoins le réseau mondial WATT.
        </div>
        <div class="artist-gate-features">${featHTML}</div>
        <div class="artist-cta">
          <a href="/watt" class="artist-cta-btn">
            <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            Rejoindre WATT
          </a>
          <span class="artist-cta-note">Bêta gratuite · 6 sons offerts</span>
        </div>
      </div>
    `;
  }
}

function _fetchArtistStats() {
  fetch('/api/watt/me/stats').then(r => {
    if (!r.ok) throw new Error('not auth');
    return r.json();
  }).then(d => {
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    el('artist-tracks', d.tracks || 0);
    el('artist-plays', d.plays || 0);
    el('artist-rank', d.rank ? `#${d.rank}` : '—');
  }).catch(() => {
    // Silently fail — stats will show "—"
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════════════════════════════

function _esc(s) {
  const el = document.createElement('span');
  el.textContent = s;
  return el.innerHTML;
}
