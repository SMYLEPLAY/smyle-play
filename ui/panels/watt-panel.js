/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/panels/watt-panel.js
   WATT Panel — WATTBOARD (espace artiste)

   Refonte : DNA + CONNECT ont été retirés de ce panneau. Leur logique de
   scoring (analyse d'émotion → univers gagnant, matching de catégories
   collaborateur) est maintenant exposée comme modules window.WattDNA et
   window.WattConnect, consommés par la marketplace (ui/hub/marketplace.js)
   pour enrichir les deux barres de recherche du hero de façon discrète.

   Ce fichier ne rend plus qu'un seul contenu : l'espace artiste
   (PLUG WATT / wattboard). Pas de canvas, pas d'animation — on garde
   uniquement ce qui a une utilité business directe : un accès rapide
   vers le dashboard artiste + stats + menu.
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

// Émotions rapides mappées aux univers — utilisé par WattDNA.analyze
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

// Mots-clés libres par univers — fallback pour les queries qui ne tapent
// pas sur un nom d'émotion exact. Réutilisé par la marketplace pour
// re-ranker les sons.
const UNIVERSE_KEYWORDS = {
  sunset:  ['soleil','chaleur','plage','chill','relax','été','warm','sun','beach','groove','deep','house','disco','cocktail','doux','calm','soir','nu-disco','lover'],
  jungle:  ['jungle','tropical','afro','beat','afrobeat','énergie','danse','dance','festival','tribal','reggae','reggaeton','island','carib','latin','rumba','salsa','bongo','dancehall'],
  night:   ['nuit','night','jazz','soul','lofi','lo-fi','mélancolie','pluie','rain','city','urban','piano','froid','dark','blue','introspect','smoke','rhodes','ambient','neo-soul'],
  hitmix:  ['mix','hit','best','eclectique','surprise','boom','party','fire','top','electro','drop','bass','trap','hype','energy','explos','future','pop','crossover'],
};

// Catégories CONNECT — utilisées par WattConnect.match pour tagger la
// recherche profils en fonction du métier / rôle cherché.
const CONNECT_CATEGORIES = [
  { key: 'beatmakers', label: 'Beatmakers',     keywords: ['beatmaker','beat','prod','producer','producteur','beatmaking'] },
  { key: 'voix',       label: 'Voix',           keywords: ['voix','chanteur','chanteuse','vocal','singer','voice','rap','rappeur','rappeuse'] },
  { key: 'musiciens',  label: 'Musiciens',      keywords: ['musicien','guitariste','bassiste','pianiste','batteur','drums','guitar','bass','piano','instrument'] },
  { key: 'videastes',  label: 'Vidéastes',      keywords: ['vidéaste','videaste','vidéo','video','clip','réalisateur','realisateur','director'] },
  { key: 'visuels',    label: 'Visuels',        keywords: ['visuel','visual','graphiste','designer','artwork','cover','illustrateur','illustrator','photo','photographe'] },
  { key: 'ingsons',    label: 'Ingénieurs son', keywords: ['ingénieur','ingenieur','mix','mixage','mastering','sound engineer','sonorisation'] },
  { key: 'topliners',  label: 'Topliners',      keywords: ['topliner','topline','hook','songwriter','songwriting','songwritter'] },
  { key: 'composit',   label: 'Compositeurs',   keywords: ['composit','arrangeur','arrangement','score','orchestra','classique'] },
];

// ══════════════════════════════════════════════════════════════════════════
//  MODULE : WattDNA — Analyseur d'univers exposé pour la marketplace
// ══════════════════════════════════════════════════════════════════════════

/**
 * Analyse une query libre et retourne l'univers gagnant (ou null si la
 * query est trop vague pour déclencher un match fort).
 * @param {string} query
 * @returns {{
 *   winner: string|null,
 *   confidence: number,   // 0..1
 *   pcts: Record<string, number>,
 *   label: string|null,
 *   color: string|null,
 *   playlistKey: string|null,
 *   keywords: string[]    // mots de l'univers gagnant, utiles pour re-ranker
 * }}
 */
function dnaAnalyze(query) {
  const empty = { winner: null, confidence: 0, pcts: {}, label: null, color: null, playlistKey: null, keywords: [] };
  const q = (query || '').trim().toLowerCase();
  if (!q) return empty;

  const scores = { sunset: 0, jungle: 0, night: 0, hitmix: 0 };
  const words = q.split(/[\s,;.!?]+/).filter(Boolean);

  // Helper : match strict = soit égalité, soit un des deux contient l'autre
  // MAIS seulement si le token contenu fait au moins 4 caractères. Ça évite
  // les collisions genre "rap" ⊂ "g-rap-histe" qui sortaient CONNECT=Voix
  // sur une query "graphiste".
  const strictMatch = (word, token) => {
    if (!word || !token) return false;
    if (word === token) return true;
    if (token.length >= 4 && word.includes(token)) return true;
    if (word.length >= 4 && token.includes(word)) return true;
    return false;
  };

  // 1) Match strict sur l'emotion map (mots précis, poids fort)
  for (const [emotion, data] of Object.entries(EMOTION_MAP)) {
    const emo = emotion.toLowerCase();
    for (const word of words) {
      if (strictMatch(word, emo)) scores[data.universe] += data.weight;
    }
  }

  // 2) Match libre sur les keywords par univers (poids modéré)
  for (const [u, keywords] of Object.entries(UNIVERSE_KEYWORDS)) {
    for (const word of words) {
      for (const k of keywords) {
        if (strictMatch(word, k)) scores[u] += 0.5;
      }
    }
  }

  const total = Object.values(scores).reduce((a, b) => a + b, 0);
  // Seuil : en dessous, on ne prétend pas avoir détecté un univers —
  // on laisse la recherche textuelle classique opérer sans pill coloré.
  if (total < 0.5) return empty;

  let winner = 'sunset';
  let max = 0;
  const pcts = {};
  for (const u of WATT_UNIVERSES) {
    pcts[u] = Math.round((scores[u] / total) * 100);
    if (scores[u] > max) { max = scores[u]; winner = u; }
  }

  const col = WATT.colors[winner];
  // Confidence = écart du gagnant au total, borné 0..1
  const confidence = Math.min(1, max / Math.max(total, 1));

  return {
    winner,
    confidence,
    pcts,
    label: col.label,
    color: col.hex,
    playlistKey: col.key,
    keywords: UNIVERSE_KEYWORDS[winner] || [],
  };
}

// ══════════════════════════════════════════════════════════════════════════
//  MODULE : WattConnect — Matcher de catégories collaborateur
// ══════════════════════════════════════════════════════════════════════════

/**
 * Détecte si une query CONNECT cible une catégorie de collaborateur
 * (beatmaker, voix, visuel, etc.).
 * @param {string} query
 * @returns {{ key: string, label: string, keywords: string[] }|null}
 */
function connectMatch(query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return null;
  const words = q.split(/[\s,;.!?]+/).filter(Boolean);

  // Même logique stricte que dnaAnalyze pour éviter les collisions de
  // substrings trop courts (ex: "rap" dans "graphiste").
  const strictMatch = (word, token) => {
    if (!word || !token) return false;
    if (word === token) return true;
    if (token.length >= 4 && word.includes(token)) return true;
    if (word.length >= 4 && token.includes(word)) return true;
    return false;
  };

  let best = null;
  let bestScore = 0;
  for (const cat of CONNECT_CATEGORIES) {
    let s = 0;
    for (const word of words) {
      for (const k of cat.keywords) {
        if (strictMatch(word, k)) s += 1;
      }
    }
    if (s > bestScore) { bestScore = s; best = cat; }
  }
  return bestScore > 0 ? best : null;
}

// Exposition globale — la marketplace lira ces modules.
if (typeof window !== 'undefined') {
  window.WattDNA = {
    analyze:    dnaAnalyze,
    UNIVERSES:  WATT_UNIVERSES,
    COLORS:     WATT.colors,
    EMOTIONS:   EMOTION_MAP,
    KEYWORDS:   UNIVERSE_KEYWORDS,
  };
  window.WattConnect = {
    match:      connectMatch,
    CATEGORIES: CONNECT_CATEGORIES,
    COLOR:      WATT.connect,
  };
}

// ══════════════════════════════════════════════════════════════════════════
//  OPEN / CLOSE / TOGGLE — panneau WATTBOARD seul
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

  // Un seul contenu possible désormais : l'espace artiste.
  const body = document.getElementById('watt-body');
  if (body) _renderArtistTab(body);
}

function closeWattPanel() {
  const panel = document.getElementById('wattPanel');
  if (!panel) return;
  panel.classList.remove('open');

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

// Compat : anciens appels wattTab(...) éventuellement encore présents.
// On n'expose plus de tabs, mais on évite le runtime error.
function wattTab(_tabKey) {
  const body = document.getElementById('watt-body');
  if (body) _renderArtistTab(body);
}

// ══════════════════════════════════════════════════════════════════════════
//  ARTIST / WATTBOARD — seul contenu du panneau
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

  // Menu items for the artist section.
  // mode 'link'  → navigue vers le wattboard complet.
  // mode 'panel' → se déplie EN ACCORDÉON dans la cellule (_wattCellToggle),
  //                le contenu est chargé à l'ouverture (_wattCellLoad).
  const menuItems = [
    {
      key: 'dashboard',
      mode: 'link',
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
      name: 'Dashboard',
      desc: 'Ouvrir le wattboard complet',
      action: 'window.location.href="/dashboard"',
    },
    {
      key: 'upload',
      mode: 'panel',
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
      name: 'Upload',
      desc: 'Publie un nouveau son',
    },
    {
      key: 'profil',
      mode: 'panel',
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
      name: 'Profil',
      desc: 'Modifie ta bio, liens et style',
    },
    {
      key: 'tracks',
      mode: 'panel',
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
      name: 'Mes Sons',
      desc: 'Écouter et gérer ta discographie',
    },
    {
      key: 'stats',
      mode: 'panel',
      icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
      name: 'Statistiques',
      desc: 'Écoutes, abonnés, évolution',
    },
  ];

  const menuHTML = menuItems.map(m => {
    if (m.mode === 'link') {
      return `
    <div class="artist-menu-item" onclick='${m.action}'>
      <div class="artist-menu-icon">${m.icon}</div>
      <div class="artist-menu-info">
        <div class="artist-menu-name">${m.name}</div>
        <div class="artist-menu-desc">${m.desc}</div>
      </div>
      <span class="artist-menu-arrow">›</span>
    </div>`;
    }
    return `
    <div class="artist-menu-block" data-key="${m.key}">
      <div class="artist-menu-item" onclick="_wattCellToggle('${m.key}')" role="button" tabindex="0">
        <div class="artist-menu-icon">${m.icon}</div>
        <div class="artist-menu-info">
          <div class="artist-menu-name">${m.name}</div>
          <div class="artist-menu-desc">${m.desc}</div>
        </div>
        <span class="artist-menu-arrow" id="wcell-arrow-${m.key}" style="transition:transform .2s">›</span>
      </div>
      <div class="artist-menu-content" id="wcell-content-${m.key}" style="display:none;padding:12px 14px;border-top:1px solid rgba(255,255,255,.08);font-size:13px;line-height:1.5;"></div>
    </div>`;
  }).join('');

  if (isLoggedIn) {
    // Connected state — la prise DEVIENT le bouton principal vers le wattboard
    container.innerHTML = `
      <a class="artist-plug-hero artist-plug-hero-link" href="/dashboard" title="Ouvrir le wattboard — poster, analytique, profil">
        ${_PLUG_SVG}
        <div class="artist-plug-title">PLUG WATT</div>
        <div class="artist-plug-sub">Ouvrir le wattboard →</div>
      </a>
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
          Ton espace artiste est inclus dans ton compte WATT —<br>
          publie ta musique et rejoins le réseau mondial WATT.
        </div>
        <div class="artist-gate-features">${featHTML}</div>
        <div class="artist-cta">
          <a href="/?auth=signup" class="artist-cta-btn">
            <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            Créer mon compte
          </a>
          <span class="artist-cta-note">Bêta gratuite · 6 sons offerts</span>
        </div>
      </div>
    `;
  }
}

function _fetchArtistStats() {
  apiFetch('/watt/me/stats').then(d => {
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    // Pas connecté → l'API renvoie authenticated:false avec des zéros.
    // On affiche "—" partout plutôt que de faux "0 sons / 0 écoutes"
    // alors que l'artiste a peut-être 81 sons (constat audit 2026-06-10).
    if (d && d.authenticated === false) {
      el('artist-tracks', '—');
      el('artist-plays', '—');
      el('artist-rank', '—');
      return;
    }
    el('artist-tracks', d.tracks || 0);
    el('artist-plays', d.plays || 0);
    el('artist-rank', d.rank ? `#${d.rank}` : '—');
  }).catch(() => {
    // Silently fail — stats will show "—" (user probably not logged in)
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  CELLULE WATT BOARD — sections dépliables + actions inline
//  Chaque section "panel" s'ouvre en accordéon DANS la cellule (pas de
//  navigation). Incrément 1 : Statistiques + Mes Sons (affichage direct).
//  Upload + Profil : aperçu + bouton (formulaires inline = incrément 2).
// ══════════════════════════════════════════════════════════════════════════

function _wattCellToggle(key) {
  const content = document.getElementById('wcell-content-' + key);
  if (!content) return;
  const arrow = document.getElementById('wcell-arrow-' + key);
  const isOpen = content.style.display !== 'none';

  // Accordéon : referme les autres sections déjà ouvertes.
  document.querySelectorAll('.artist-menu-content').forEach(c => {
    if (c !== content) c.style.display = 'none';
  });
  document.querySelectorAll('.artist-menu-arrow').forEach(a => {
    if (a !== arrow) a.style.transform = '';
  });

  if (isOpen) {
    content.style.display = 'none';
    if (arrow) arrow.style.transform = '';
    return;
  }
  content.style.display = 'block';
  if (arrow) arrow.style.transform = 'rotate(90deg)';
  _wattCellLoad(key, content);
}

function _wattCellLoad(key, content) {
  if (key === 'stats') {
    content.innerHTML = '<div style="opacity:.6">Chargement…</div>';
    apiFetch('/watt/me/stats').then(d => {
      // Pas connecté → message clair plutôt que de faux zéros.
      if (d && d.authenticated === false) {
        content.innerHTML = '<div style="opacity:.6">Connecte-toi pour voir tes stats.</div>';
        return;
      }
      content.innerHTML = `
        <div style="display:flex;gap:18px;flex-wrap:wrap">
          <div><strong style="font-size:18px">${d.tracks || 0}</strong><br><span style="opacity:.6">Sons</span></div>
          <div><strong style="font-size:18px">${d.plays || 0}</strong><br><span style="opacity:.6">Écoutes</span></div>
          <div><strong style="font-size:18px">${d.rank ? '#' + d.rank : '—'}</strong><br><span style="opacity:.6">Rang</span></div>
        </div>`;
    }).catch(() => { content.innerHTML = '<div style="opacity:.6">Stats indisponibles.</div>'; });
    return;
  }

  if (key === 'tracks') {
    content.innerHTML = '<div style="opacity:.6">Chargement…</div>';
    apiFetch('/tracks/me').then(list => {
      if (!Array.isArray(list) || list.length === 0) {
        content.innerHTML = '<div style="opacity:.6">Aucun son publié pour l\'instant.</div>';
        return;
      }
      const rows = list.map(t => {
        const title = String(t.title || 'Sans titre').replace(/"/g, '&quot;');
        const id = encodeURIComponent(String(t.id || ''));
        // Clic → ouvre l'éditeur "Modifier le son" du dashboard sur ce son.
        return `
        <div class="wcell-track-row" data-title="${title.toLowerCase()}" title="Modifier ce son" onclick="window.location.href='/dashboard?edit-track=${id}'" style="cursor:pointer;display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05)">
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${title}</span>
          <span style="opacity:.6;white-space:nowrap">▶ ${t.plays || 0} ✏️</span>
        </div>`;
      }).join('');
      content.innerHTML = `
        <input type="text" placeholder="Rechercher un son…" oninput="_wattCellFilterTracks(this.value)"
          style="width:100%;box-sizing:border-box;margin-bottom:8px;padding:7px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.05);color:inherit;font-size:13px;outline:none" />
        <div id="wcell-tracks-list">${rows}</div>
        <div id="wcell-tracks-empty" style="display:none;opacity:.6;padding:6px 0">Aucun son ne correspond.</div>`;
    }).catch(() => { content.innerHTML = '<div style="opacity:.6">Liste indisponible.</div>'; });
    return;
  }

  if (key === 'upload') {
    content.innerHTML = `
      <div style="opacity:.8;margin-bottom:8px">Poster un son directement ici arrive bientôt.</div>
      <button onclick='window.location.href="/dashboard#sec-upload"' style="background:#FFD700;color:#000;border:none;border-radius:8px;padding:8px 12px;font-weight:600;cursor:pointer">Ouvrir l'upload →</button>`;
    return;
  }

  if (key === 'profil') {
    content.innerHTML = `
      <div style="opacity:.8;margin-bottom:8px">Éditer ton profil directement ici arrive bientôt.</div>
      <button onclick='window.location.href="/dashboard#sec-identity"' style="background:#FFD700;color:#000;border:none;border-radius:8px;padding:8px 12px;font-weight:600;cursor:pointer">Éditer le profil →</button>`;
    return;
  }
}

// Filtre la liste "Mes Sons" par titre (recherche live, sans re-fetch).
function _wattCellFilterTracks(value) {
  const q = String(value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#wcell-tracks-list .wcell-track-row');
  let visible = 0;
  rows.forEach(r => {
    const title = r.getAttribute('data-title') || '';
    const show = !q || title.includes(q);
    r.style.display = show ? 'flex' : 'none';
    if (show) visible++;
  });
  const empty = document.getElementById('wcell-tracks-empty');
  if (empty) empty.style.display = visible === 0 ? 'block' : 'none';
}

// Exposition globale pour les onclick inline du menu de la cellule.
if (typeof window !== 'undefined') {
  window._wattCellToggle = _wattCellToggle;
  window._wattCellLoad = _wattCellLoad;
  window._wattCellFilterTracks = _wattCellFilterTracks;
}
