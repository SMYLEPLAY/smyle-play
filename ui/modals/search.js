/**
 * SMYLE SEARCH — Modal recherche globale Connect + DNA
 *
 * Usage :
 *   <script src="/ui/modals/search.js" defer></script>
 *
 * Auto-injection au DOMContentLoaded :
 *   1. un bouton loupe dans la topbar (détection multi-classes : .dash-topbar-right,
 *      .ap-topbar-right, .lib-topbar-right, .topbar-right).
 *   2. un modal fullscreen qui s'ouvre au clic (overlay + close ESC + click fond).
 *
 * Le modal a deux onglets :
 *   - CONNECT : recherche de profils artistes (/watt/search/artists)
 *   - DNA     : recherche de morceaux / signatures (/watt/search/tracks)
 *
 * Convention : consomme window.API_BASE s'il existe (injecté par
 * /ui/core/api.js), sinon fallback sur http://localhost:8000.
 *
 * Feature flag : on n'injecte pas le bouton si le DOM déjà contient
 * [data-smyle-search] — permet à une page de s'opt-out explicitement
 * (ex : homepage qui aurait déjà sa propre barre de recherche).
 */
(function () {
  'use strict';

  if (window.__smyleSearchInstalled) return;
  window.__smyleSearchInstalled = true;

  // ── Config ────────────────────────────────────────────────────────────
  const API_BASE = (typeof window !== 'undefined' && window.API_BASE)
    ? String(window.API_BASE).replace(/\/+$/, '')
    : 'http://localhost:8000';

  const DEBOUNCE_MS = 280;
  const MIN_CHARS   = 0; // 0 = on déclenche aussi au focus (liste "top")

  // ── Icônes SVG ────────────────────────────────────────────────────────
  const ICO_SEARCH = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="7"/>
      <line x1="16.65" y1="16.65" x2="21" y2="21"/>
    </svg>`;
  const ICO_CLOSE = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/>
      <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>`;
  const ICO_USER = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>`;
  const ICO_DISC = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="9"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>`;

  // ── Styles injectés ───────────────────────────────────────────────────
  // On injecte un <style> plutôt que de toucher aux feuilles de chaque
  // page : zéro couplage avec dashboard.css / artiste.css / etc.
  const STYLES = `
  .smyle-search-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,.1);
    background: rgba(255,255,255,.04);
    color: rgba(255,255,255,.72);
    cursor: pointer;
    transition: all .15s ease;
    padding: 0;
  }
  .smyle-search-btn:hover {
    background: rgba(255,215,0,.1);
    border-color: rgba(255,215,0,.3);
    color: #FFD700;
  }
  .smyle-search-btn svg { width: 18px; height: 18px; }

  .smyle-search-overlay {
    position: fixed;
    inset: 0;
    z-index: 9998;
    background: rgba(0,0,0,.78);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    display: none;
    align-items: flex-start;
    justify-content: center;
    padding: 56px 16px 16px;
    overflow: auto;
  }
  .smyle-search-overlay.is-open { display: flex; }

  .smyle-search-panel {
    width: 100%;
    max-width: 720px;
    background: #0d0a1a;
    border: 1px solid rgba(255,215,0,.22);
    border-radius: 10px;
    box-shadow: 0 40px 80px rgba(0,0,0,.6);
    overflow: hidden;
    color: #fff;
    animation: smyleSearchIn .18s ease-out;
  }
  @keyframes smyleSearchIn {
    from { transform: translateY(-8px); opacity: 0; }
    to   { transform: translateY(0);    opacity: 1; }
  }

  .smyle-search-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 18px;
    border-bottom: 1px solid rgba(255,255,255,.06);
  }
  .smyle-search-input {
    flex: 1 1 auto;
    min-width: 0;
    padding: 10px 14px;
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 6px;
    color: #fff;
    font-size: 15px;
    outline: none;
    transition: border-color .15s ease;
  }
  .smyle-search-input::placeholder { color: rgba(255,255,255,.35); }
  .smyle-search-input:focus { border-color: rgba(255,215,0,.5); }
  .smyle-search-close {
    flex: 0 0 auto;
    width: 36px;
    height: 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 0;
    color: rgba(255,255,255,.55);
    cursor: pointer;
    border-radius: 6px;
  }
  .smyle-search-close:hover { color: #fff; background: rgba(255,255,255,.06); }
  .smyle-search-close svg { width: 18px; height: 18px; }

  .smyle-search-tabs {
    display: flex;
    border-bottom: 1px solid rgba(255,255,255,.06);
  }
  .smyle-search-tab {
    flex: 1 1 0;
    padding: 12px 16px;
    background: transparent;
    border: 0;
    color: rgba(255,255,255,.45);
    font-size: 13px;
    font-weight: 500;
    letter-spacing: .5px;
    text-transform: uppercase;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border-bottom: 2px solid transparent;
    transition: color .15s ease, border-color .15s ease;
  }
  .smyle-search-tab svg { width: 14px; height: 14px; }
  .smyle-search-tab.is-active {
    color: #FFD700;
    border-bottom-color: #FFD700;
  }
  .smyle-search-tab:hover:not(.is-active) { color: rgba(255,255,255,.75); }

  .smyle-search-results {
    max-height: 60vh;
    overflow-y: auto;
    padding: 8px 0;
  }
  .smyle-search-empty,
  .smyle-search-loading {
    padding: 32px 20px;
    text-align: center;
    color: rgba(255,255,255,.4);
    font-size: 13px;
  }

  .smyle-search-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 18px;
    cursor: pointer;
    transition: background .12s ease;
    text-decoration: none;
    color: inherit;
  }
  .smyle-search-row:hover { background: rgba(255,215,0,.05); }
  .smyle-search-avatar {
    flex: 0 0 auto;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: rgba(255,215,0,.2);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 700;
    color: #0d0a1a;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,.08);
  }
  .smyle-search-avatar img {
    width: 100%; height: 100%; object-fit: cover;
  }
  .smyle-search-row-body {
    flex: 1 1 auto;
    min-width: 0;
  }
  .smyle-search-row-title {
    font-size: 14px;
    font-weight: 600;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .smyle-search-row-sub {
    font-size: 12px;
    color: rgba(255,255,255,.48);
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .smyle-search-row-meta {
    flex: 0 0 auto;
    font-size: 11px;
    color: rgba(255,255,255,.35);
    text-align: right;
  }

  @media (max-width: 560px) {
    .smyle-search-overlay { padding: 20px 10px; }
    .smyle-search-header { padding: 10px 12px; }
    .smyle-search-input { font-size: 14px; }
  }
  `;

  function injectStyles() {
    if (document.getElementById('smyle-search-styles')) return;
    const s = document.createElement('style');
    s.id = 'smyle-search-styles';
    s.textContent = STYLES;
    document.head.appendChild(s);
  }

  // ── Bouton loupe (topbar) ─────────────────────────────────────────────
  // On essaie chaque classe de topbar connue et on injecte dans la
  // première trouvée. On place le bouton EN PREMIER dans le conteneur
  // (flex order) pour rester visible à côté du dropdown profil / balance.
  const TOPBAR_CONTAINERS = [
    '.dash-topbar-right',
    '.ap-topbar-right',
    '.lib-topbar-right',
    '.topbar-right',
  ];

  function injectButton() {
    // Escape hatch : une page peut placer un marker pour bloquer l'injection
    if (document.querySelector('[data-smyle-search-skip]')) return;
    // Évite les doublons si plusieurs scripts se relancent
    if (document.querySelector('.smyle-search-btn')) return;

    let host = null;
    for (const sel of TOPBAR_CONTAINERS) {
      const el = document.querySelector(sel);
      if (el) { host = el; break; }
    }
    if (!host) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'smyle-search-btn';
    btn.setAttribute('aria-label', 'Rechercher');
    btn.title = 'Rechercher';
    btn.innerHTML = ICO_SEARCH;
    btn.addEventListener('click', openModal);
    // Flex order négatif : s'affiche en premier dans la topbar.
    btn.style.order = '-1';
    host.prepend(btn);
  }

  // ── Modal ─────────────────────────────────────────────────────────────
  let modalRoot = null;
  let inputEl   = null;
  let resultsEl = null;
  let currentTab = 'artists'; // 'artists' | 'tracks'
  let debounceTimer = null;
  let lastQuery = '';

  function buildModal() {
    if (modalRoot) return;
    modalRoot = document.createElement('div');
    modalRoot.className = 'smyle-search-overlay';
    modalRoot.setAttribute('role', 'dialog');
    modalRoot.setAttribute('aria-modal', 'true');
    modalRoot.innerHTML = `
      <div class="smyle-search-panel" role="document">
        <div class="smyle-search-header">
          <input type="search" class="smyle-search-input"
                 placeholder="Rechercher un artiste, un son, un univers…"
                 autocomplete="off" spellcheck="false" />
          <button type="button" class="smyle-search-close"
                  aria-label="Fermer">${ICO_CLOSE}</button>
        </div>
        <div class="smyle-search-tabs" role="tablist">
          <button type="button" class="smyle-search-tab is-active"
                  data-tab="artists" role="tab" aria-selected="true">
            ${ICO_USER}<span>Connect — artistes</span>
          </button>
          <button type="button" class="smyle-search-tab"
                  data-tab="tracks" role="tab" aria-selected="false">
            ${ICO_DISC}<span>DNA — morceaux</span>
          </button>
        </div>
        <div class="smyle-search-results" aria-live="polite"></div>
      </div>
    `;
    document.body.appendChild(modalRoot);

    // Refs
    inputEl   = modalRoot.querySelector('.smyle-search-input');
    resultsEl = modalRoot.querySelector('.smyle-search-results');

    // Events
    modalRoot.addEventListener('click', (e) => {
      if (e.target === modalRoot) closeModal();
    });
    modalRoot.querySelector('.smyle-search-close')
      .addEventListener('click', closeModal);

    modalRoot.querySelectorAll('.smyle-search-tab').forEach((tab) => {
      tab.addEventListener('click', () => setTab(tab.dataset.tab));
    });

    inputEl.addEventListener('input', onInputChange);
    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
    });

    document.addEventListener('keydown', onGlobalKey);
  }

  function onGlobalKey(e) {
    if (!modalRoot || !modalRoot.classList.contains('is-open')) return;
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
  }

  function openModal() {
    buildModal();
    modalRoot.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    setTimeout(() => inputEl && inputEl.focus(), 30);
    // Premier run : liste "top" (q="")
    runSearch('');
  }

  function closeModal() {
    if (!modalRoot) return;
    modalRoot.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  function setTab(tab) {
    if (tab !== 'artists' && tab !== 'tracks') return;
    currentTab = tab;
    modalRoot.querySelectorAll('.smyle-search-tab').forEach((t) => {
      const active = t.dataset.tab === tab;
      t.classList.toggle('is-active', active);
      t.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    runSearch(lastQuery);
  }

  function onInputChange() {
    const q = (inputEl.value || '').trim();
    lastQuery = q;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => runSearch(q), DEBOUNCE_MS);
  }

  // ── Fetch + render ────────────────────────────────────────────────────
  async function runSearch(q) {
    if (!resultsEl) return;
    if (q.length < MIN_CHARS) {
      resultsEl.innerHTML = emptyState('Tape quelques lettres pour chercher.');
      return;
    }
    resultsEl.innerHTML = `<div class="smyle-search-loading">Recherche…</div>`;

    const endpoint = currentTab === 'artists'
      ? '/watt/search/artists'
      : '/watt/search/tracks';
    const url = `${API_BASE}${endpoint}?q=${encodeURIComponent(q)}`;

    try {
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      // L'utilisateur a peut-être tapé entretemps — on n'écrase pas si
      // la query n'est plus d'actualité.
      if (lastQuery !== q) return;
      if (currentTab === 'artists') renderArtists(data.artists || []);
      else                          renderTracks(data.tracks || []);
    } catch (err) {
      console.warn('[smyle-search] fetch échoué', err);
      if (lastQuery === q) {
        resultsEl.innerHTML = emptyState(
          'Impossible de joindre le moteur de recherche pour le moment.'
        );
      }
    }
  }

  function emptyState(msg) {
    return `<div class="smyle-search-empty">${escapeHtml(msg)}</div>`;
  }

  function renderArtists(list) {
    if (!list.length) {
      resultsEl.innerHTML = emptyState(
        'Aucun artiste trouvé — essaie un autre terme.'
      );
      return;
    }
    resultsEl.innerHTML = list.map(artistRowHtml).join('');
  }

  function renderTracks(list) {
    if (!list.length) {
      resultsEl.innerHTML = emptyState(
        'Aucun morceau trouvé — essaie un autre terme.'
      );
      return;
    }
    resultsEl.innerHTML = list.map(trackRowHtml).join('');
  }

  function artistRowHtml(a) {
    const initials = (a.artistName || '?').trim().slice(0, 2).toUpperCase();
    const color    = a.brandColor || '#FFD700';
    const avatar   = a.avatarUrl
      ? `<img src="${escapeAttr(a.avatarUrl)}" alt="" />`
      : initials;
    const sub = [a.genre, a.city].filter(Boolean).join(' · ')
             || (a.bio ? a.bio.slice(0, 80) : 'Artiste WATT');
    const meta = `${a.plays || 0} écoutes · ${a.followersCount || 0} abonnés`;
    const href = `/u/${encodeURIComponent(a.slug || '')}`;
    return `
      <a class="smyle-search-row" href="${escapeAttr(href)}">
        <span class="smyle-search-avatar"
              style="background:${escapeAttr(color)}">${avatar}</span>
        <span class="smyle-search-row-body">
          <span class="smyle-search-row-title">${escapeHtml(a.artistName || 'Sans nom')}</span>
          <span class="smyle-search-row-sub">${escapeHtml(sub)}</span>
        </span>
        <span class="smyle-search-row-meta">${escapeHtml(meta)}</span>
      </a>
    `;
  }

  function trackRowHtml(t) {
    const color = t.color || '#FFD700';
    const sub   = [t.artistName, t.universe].filter(Boolean).join(' · ');
    const meta  = `${t.plays || 0} écoutes`;
    // Deep-link vers la page artiste, ancre sur la track — /u/slug existe ;
    // l'ancre sera supportée quand Étape 5 rendra les cellules tracks.
    const href = t.artistSlug
      ? `/u/${encodeURIComponent(t.artistSlug)}#track-${encodeURIComponent(t.id)}`
      : '#';
    return `
      <a class="smyle-search-row" href="${escapeAttr(href)}">
        <span class="smyle-search-avatar"
              style="background:${escapeAttr(color)}">${ICO_DISC}</span>
        <span class="smyle-search-row-body">
          <span class="smyle-search-row-title">${escapeHtml(t.title || 'Sans titre')}</span>
          <span class="smyle-search-row-sub">${escapeHtml(sub)}</span>
        </span>
        <span class="smyle-search-row-meta">${escapeHtml(meta)}</span>
      </a>
    `;
  }

  // ── Escaping helpers ──────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escapeAttr(s) { return escapeHtml(s); }

  // ── Init ──────────────────────────────────────────────────────────────
  function init() {
    injectStyles();
    injectButton();
  }

  // API publique minimale (utile pour les tests ou l'ouverture depuis
  // un autre script — ex : shortcut Ctrl+K si on l'ajoute plus tard).
  window.SmyleSearch = {
    open:  openModal,
    close: closeModal,
    setTab,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
