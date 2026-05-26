/**
 * SMYLE SEARCH — Panneau de recherche unifié (loupe topbar)
 *
 * Design : panneau large deux colonnes
 *   Gauche  — CONNECT : profils artistes  (/watt/search/artists)
 *   Droite  — DNA     : morceaux / sons   (/watt/search/tracks)
 *
 * Les deux colonnes se mettent à jour en parallèle à chaque frappe.
 * Chips de filtre :
 *   - CONNECT : rôle (producteur, beatmaker, vocalist…)
 *   - DNA     : mood (chill, dark, énergique…)
 *
 * Auto-injection : bouton loupe dans .dash-topbar-right / .ap-topbar-right /
 *   .lib-topbar-right / .topbar-right. Présent sur toutes les pages.
 * Raccourci : Ctrl+K / Cmd+K ouvre le panneau.
 */
(function () {
  'use strict';

  if (window.__smyleSearchInstalled) return;
  window.__smyleSearchInstalled = true;

  const API_BASE = (typeof window !== 'undefined' && window.API_BASE)
    ? String(window.API_BASE).replace(/\/+$/, '')
    : 'http://localhost:8000';

  const DEBOUNCE_MS = 260;

  // ── SVG icons ─────────────────────────────────────────────────────────
  const ICO_SEARCH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="16.65" y1="16.65" x2="21" y2="21"/></svg>`;
  const ICO_CLOSE  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
  const ICO_USER   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
  const ICO_DISC   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>`;
  const ICO_PLAY   = `<svg viewBox="0 0 24 24" fill="currentColor" stroke="none" width="12" height="12"><polygon points="5,3 19,12 5,21"/></svg>`;

  // Chips connect (rôles artistes) — valeurs = ROLE_CODES backend (schemas/user.py)
  const CONNECT_CHIPS = [
    { label: 'Producteur',    val: 'producteur'    },
    { label: 'Beatmaker',     val: 'beatmaker'     },
    { label: 'Compositeur',   val: 'compositeur'   },
    { label: 'Topliner',      val: 'topliner'      },
    { label: 'DJ',            val: 'dj'            },
    { label: 'Ghostwriter',   val: 'ghostwriter'   },
    { label: 'Ingé son',      val: 'ingenieur_son' },
    { label: 'Artiste',       val: 'artiste'       },
  ];

  // Chips DNA (moods)
  const DNA_CHIPS = [
    { label: 'chill',        val: 'chill'        },
    { label: 'énergique',    val: 'énergique'    },
    { label: 'dark',         val: 'dark'         },
    { label: 'festif',       val: 'festif'       },
    { label: 'romantique',   val: 'romantique'   },
    { label: 'mélancolique', val: 'mélancolique' },
    { label: 'instrumental', val: 'instrumental' },
    { label: 'vocal',        val: 'vocal'        },
  ];

  // ── Styles ────────────────────────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById('smyle-search-styles')) return;
    const s = document.createElement('style');
    s.id = 'smyle-search-styles';
    s.textContent = `
/* ── Bouton loupe ────────────────────────────────────────────────────── */
.smyle-search-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.1);
  background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.72); cursor: pointer;
  transition: all .15s ease; padding: 0;
}
.smyle-search-btn:hover {
  background: rgba(255,215,0,.1); border-color: rgba(255,215,0,.3); color: #FFD700;
}
.smyle-search-btn svg { width: 18px; height: 18px; }

/* ── Overlay ─────────────────────────────────────────────────────────── */
.smyle-search-overlay {
  position: fixed; inset: 0; z-index: 9998;
  background: rgba(0,0,0,.82);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  display: none; align-items: flex-start; justify-content: center;
  padding: 48px 16px 24px; overflow: auto;
}
.smyle-search-overlay.is-open { display: flex; }

/* ── Panneau principal ───────────────────────────────────────────────── */
.smyle-search-panel {
  background: #0f0c18;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  width: 100%; max-width: 960px;
  box-shadow: 0 32px 80px rgba(0,0,0,.7), 0 0 0 1px rgba(204,136,255,.06);
  overflow: hidden;
  display: flex; flex-direction: column;
}

/* ── Header : barre de recherche ─────────────────────────────────────── */
.smyle-search-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255,255,255,.06);
  background: rgba(255,255,255,.02);
}
.smyle-search-header-ico {
  color: rgba(255,255,255,.35); flex-shrink: 0;
}
.smyle-search-header-ico svg { width: 18px; height: 18px; display: block; }
.smyle-search-input {
  flex: 1; background: transparent; border: 0; outline: none;
  font-size: 17px; font-weight: 500; color: #fff;
  font-family: inherit; letter-spacing: -.01em;
}
.smyle-search-input::placeholder { color: rgba(255,255,255,.28); }
.smyle-search-kbd {
  font-size: 11px; color: rgba(255,255,255,.25);
  border: 1px solid rgba(255,255,255,.1); border-radius: 5px;
  padding: 2px 6px; flex-shrink: 0; letter-spacing: .04em;
}
.smyle-search-close {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.5); cursor: pointer; flex-shrink: 0;
  transition: all .12s ease; padding: 0;
}
.smyle-search-close:hover { background: rgba(255,255,255,.1); color: #fff; }
.smyle-search-close svg { width: 14px; height: 14px; }

/* ── Corps deux colonnes ─────────────────────────────────────────────── */
.smyle-search-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 480px;
  max-height: 70vh;
  overflow: hidden;
}
@media (max-width: 680px) {
  .smyle-search-body { grid-template-columns: 1fr; max-height: none; }
}

/* ── Colonne commune ─────────────────────────────────────────────────── */
.smyle-search-col {
  display: flex; flex-direction: column;
  overflow: hidden;
  border-right: 1px solid rgba(255,255,255,.05);
}
.smyle-search-col:last-child { border-right: 0; }

.smyle-search-col-hdr {
  display: flex; align-items: center; gap: 7px;
  padding: 10px 16px 8px;
  font-size: 10px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: rgba(255,255,255,.35);
  border-bottom: 1px solid rgba(255,255,255,.04);
  flex-shrink: 0;
}
.smyle-search-col-hdr svg { width: 12px; height: 12px; }
.smyle-search-col-hdr.connect { color: rgba(100,200,255,.6); }
.smyle-search-col-hdr.dna     { color: rgba(204,136,255,.7); }

/* Chips filtre */
.smyle-search-chips {
  display: flex; flex-wrap: wrap; gap: 5px;
  padding: 8px 14px 6px; border-bottom: 1px solid rgba(255,255,255,.04);
  flex-shrink: 0;
}
.smyle-search-chip {
  padding: 3px 10px; border-radius: 999px; font-size: 11px;
  cursor: pointer; transition: all .12s ease; border: 1px solid;
}
.smyle-search-chip.connect-chip {
  border-color: rgba(100,200,255,.2); background: rgba(100,200,255,.06);
  color: rgba(100,200,255,.7);
}
.smyle-search-chip.connect-chip:hover,
.smyle-search-chip.connect-chip.is-active {
  border-color: rgba(100,200,255,.6); background: rgba(100,200,255,.16);
  color: #64C8FF;
}
.smyle-search-chip.dna-chip {
  border-color: rgba(204,136,255,.2); background: rgba(204,136,255,.06);
  color: rgba(204,136,255,.7);
}
.smyle-search-chip.dna-chip:hover,
.smyle-search-chip.dna-chip.is-active {
  border-color: rgba(204,136,255,.6); background: rgba(204,136,255,.18);
  color: #cc88ff;
}

/* Liste résultats (scrollable) */
.smyle-search-results {
  flex: 1; overflow-y: auto; padding: 6px 0;
}
.smyle-search-results::-webkit-scrollbar { width: 4px; }
.smyle-search-results::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 2px; }

/* ── Cards artistes ──────────────────────────────────────────────────── */
.ss-artist-card {
  display: flex; align-items: center; gap: 11px;
  padding: 9px 14px; text-decoration: none;
  transition: background .1s ease; cursor: pointer;
}
.ss-artist-card:hover { background: rgba(255,255,255,.04); }
.ss-artist-avatar {
  width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700; color: #fff;
  overflow: hidden;
}
.ss-artist-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ss-artist-body { flex: 1; min-width: 0; }
.ss-artist-name {
  font-size: 13px; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-artist-sub {
  font-size: 11px; color: rgba(255,255,255,.4); margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-artist-meta { font-size: 10px; color: rgba(255,255,255,.28); flex-shrink: 0; text-align: right; }

/* ── Cards sons ──────────────────────────────────────────────────────── */
.ss-track-card {
  display: flex; align-items: center; gap: 11px;
  padding: 8px 14px; text-decoration: none;
  transition: background .1s ease; cursor: pointer;
}
.ss-track-card:hover { background: rgba(255,255,255,.04); }
.ss-track-cover {
  width: 40px; height: 40px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; position: relative;
}
.ss-track-cover img { width: 100%; height: 100%; object-fit: cover; }
.ss-track-cover-fallback {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.ss-track-play-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .12s;
  color: #fff; border-radius: 8px;
}
.ss-track-card:hover .ss-track-play-overlay { opacity: 1; }
.ss-track-body { flex: 1; min-width: 0; }
.ss-track-title {
  font-size: 13px; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-track-sub {
  font-size: 11px; color: rgba(255,255,255,.4); margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-track-tags { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
.ss-track-tag {
  font-size: 10px; padding: 0 5px; border-radius: 99px;
  background: rgba(204,136,255,.1); border: 1px solid rgba(204,136,255,.18);
  color: rgba(204,136,255,.85);
}
.ss-track-meta { font-size: 10px; color: rgba(255,255,255,.28); flex-shrink: 0; text-align: right; }

/* ── États vide / chargement ─────────────────────────────────────────── */
.ss-empty {
  padding: 32px 16px; text-align: center;
  color: rgba(255,255,255,.3); font-size: 12px; line-height: 1.6;
}
.ss-loading { padding: 28px 16px; text-align: center; }
.ss-loading-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,.25); margin: 0 3px;
  animation: ssPulse 1.2s ease-in-out infinite;
}
.ss-loading-dot:nth-child(2) { animation-delay: .2s; }
.ss-loading-dot:nth-child(3) { animation-delay: .4s; }
@keyframes ssPulse { 0%,80%,100%{transform:scale(.8);opacity:.4} 40%{transform:scale(1);opacity:1} }
    `;
    document.head.appendChild(s);
  }

  // ── Injection bouton ──────────────────────────────────────────────────
  function injectButton() {
    const container = document.querySelector(
      '.dash-topbar-right, .ap-topbar-right, .lib-topbar-right, .topbar-right'
    );
    if (!container || container.querySelector('.smyle-search-btn')) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'smyle-search-btn';
    btn.setAttribute('aria-label', 'Rechercher');
    btn.title = 'Rechercher  (Ctrl+K)';
    btn.innerHTML = ICO_SEARCH;
    btn.addEventListener('click', openModal);
    container.insertBefore(btn, container.firstChild);
  }

  // ── State ─────────────────────────────────────────────────────────────
  let modalRoot    = null;
  let inputEl      = null;
  let connectEl    = null; // résultats gauche
  let dnaEl        = null; // résultats droite
  let debounce     = null;
  let lastQuery    = '';
  // Multi-select : Sets de valeurs actives par colonne
  let activeConnectChips = new Set();
  let activeDnaChips     = new Set();

  // ── Build modal ───────────────────────────────────────────────────────
  function buildModal() {
    if (modalRoot) return;
    modalRoot = document.createElement('div');
    modalRoot.className = 'smyle-search-overlay';
    modalRoot.setAttribute('role', 'dialog');
    modalRoot.setAttribute('aria-modal', 'true');
    modalRoot.setAttribute('aria-label', 'Recherche WATT');

    const connectChipsHtml = CONNECT_CHIPS.map(c =>
      `<button type="button" class="smyle-search-chip connect-chip" data-val="${c.val}">${c.label}</button>`
    ).join('');

    const dnaChipsHtml = DNA_CHIPS.map(c =>
      `<button type="button" class="smyle-search-chip dna-chip" data-val="${c.val}">${c.label}</button>`
    ).join('');

    modalRoot.innerHTML = `
      <div class="smyle-search-panel" role="document">

        <!-- Barre de recherche -->
        <div class="smyle-search-header">
          <span class="smyle-search-header-ico">${ICO_SEARCH}</span>
          <input type="search" class="smyle-search-input"
                 placeholder="Artiste, son, mood, ville…"
                 autocomplete="off" spellcheck="false" />
          <span class="smyle-search-kbd">ESC</span>
          <button type="button" class="smyle-search-close" aria-label="Fermer">${ICO_CLOSE}</button>
        </div>

        <!-- Corps 2 colonnes -->
        <div class="smyle-search-body">

          <!-- Colonne CONNECT -->
          <div class="smyle-search-col" id="ss-col-connect">
            <div class="smyle-search-col-hdr connect">
              ${ICO_USER} CONNECT — Artistes
            </div>
            <div class="smyle-search-chips" id="ss-connect-chips">${connectChipsHtml}</div>
            <div class="smyle-search-results" id="ss-results-connect" aria-live="polite"></div>
          </div>

          <!-- Colonne DNA -->
          <div class="smyle-search-col" id="ss-col-dna">
            <div class="smyle-search-col-hdr dna">
              ${ICO_DISC} DNA — Sons
            </div>
            <div class="smyle-search-chips" id="ss-dna-chips">${dnaChipsHtml}</div>
            <div class="smyle-search-results" id="ss-results-dna" aria-live="polite"></div>
          </div>

        </div>
      </div>
    `;

    document.body.appendChild(modalRoot);

    // Refs
    inputEl   = modalRoot.querySelector('.smyle-search-input');
    connectEl = modalRoot.querySelector('#ss-results-connect');
    dnaEl     = modalRoot.querySelector('#ss-results-dna');

    // Events — overlay
    modalRoot.addEventListener('click', e => { if (e.target === modalRoot) closeModal(); });
    modalRoot.querySelector('.smyle-search-close').addEventListener('click', closeModal);

    // Input
    inputEl.addEventListener('input', onInput);
    inputEl.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); closeModal(); } });

    // Chips CONNECT
    modalRoot.querySelectorAll('#ss-connect-chips .smyle-search-chip').forEach(chip => {
      chip.addEventListener('click', () => onChipClick(chip, 'connect'));
    });

    // Chips DNA
    modalRoot.querySelectorAll('#ss-dna-chips .smyle-search-chip').forEach(chip => {
      chip.addEventListener('click', () => onChipClick(chip, 'dna'));
    });

    document.addEventListener('keydown', onGlobalKey);
  }

  function onGlobalKey(e) {
    // Ctrl+K / Cmd+K — ouvre le panneau
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (modalRoot && modalRoot.classList.contains('is-open')) closeModal();
      else openModal();
      return;
    }
    if (!modalRoot || !modalRoot.classList.contains('is-open')) return;
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
  }

  function openModal() {
    buildModal();
    modalRoot.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    setTimeout(() => inputEl && inputEl.focus(), 30);
    _trigger();
  }

  function closeModal() {
    if (!modalRoot) return;
    modalRoot.classList.remove('is-open');
    document.body.style.overflow = '';
    // Reset chips à la fermeture
    activeConnectChips.clear();
    activeDnaChips.clear();
    if (inputEl) inputEl.value = '';
    lastQuery = '';
  }

  function onInput() {
    lastQuery = (inputEl.value || '').trim();
    clearTimeout(debounce);
    debounce = setTimeout(_trigger, DEBOUNCE_MS);
  }

  function onChipClick(chip, side) {
    const val = chip.dataset.val;
    const set  = side === 'connect' ? activeConnectChips : activeDnaChips;
    if (set.has(val)) {
      set.delete(val);
      chip.classList.remove('is-active');
    } else {
      set.add(val);
      chip.classList.add('is-active');
    }
    _trigger();
  }

  // Lance la recherche avec le texte + les chips actifs
  function _trigger() {
    clearTimeout(debounce);
    runSearch(lastQuery, activeConnectChips, activeDnaChips);
  }

  // ── Fetch parallèle ───────────────────────────────────────────────────
  async function runSearch(q, connectChips, dnaChips) {
    setLoading(connectEl);
    setLoading(dnaEl);
    const [artists, tracks] = await Promise.all([
      fetchArtists(q, connectChips),
      fetchTracks(q, dnaChips),
    ]);
    if (connectEl) renderArtists(artists, q);
    if (dnaEl)     renderTracks(tracks, q);
  }

  async function fetchArtists(q, rolesSet) {
    try {
      const params = new URLSearchParams({ q, limit: '12' });
      if (rolesSet && rolesSet.size > 0) {
        rolesSet.forEach(r => params.append('roles', r));
      }
      const url = `${API_BASE}/watt/search/artists?${params}`;
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) return [];
      const data = await res.json();
      return data.artists || [];
    } catch { return []; }
  }

  async function fetchTracks(q, moodsSet) {
    try {
      const params = new URLSearchParams({ q, limit: '12' });
      if (moodsSet && moodsSet.size > 0) {
        moodsSet.forEach(m => params.append('moods', m));
      }
      const url = `${API_BASE}/watt/search/tracks?${params}`;
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) return [];
      const data = await res.json();
      return data.tracks || [];
    } catch { return []; }
  }

  // ── Render ────────────────────────────────────────────────────────────
  function setLoading(el) {
    if (!el) return;
    el.innerHTML = `<div class="ss-loading"><span class="ss-loading-dot"></span><span class="ss-loading-dot"></span><span class="ss-loading-dot"></span></div>`;
  }

  function renderArtists(list, q) {
    if (!connectEl) return;
    if (!list.length) {
      connectEl.innerHTML = `<div class="ss-empty">${q ? `Aucun artiste pour "${escHtml(q)}"` : 'Explore les artistes WATT'}</div>`;
      return;
    }
    connectEl.innerHTML = list.map(a => artistCardHtml(a)).join('');
  }

  function renderTracks(list, q) {
    if (!dnaEl) return;
    if (!list.length) {
      dnaEl.innerHTML = `<div class="ss-empty">${q ? `Aucun son pour "${escHtml(q)}"` : 'Explore les sons du catalogue'}</div>`;
      return;
    }
    dnaEl.innerHTML = list.map(t => trackCardHtml(t)).join('');
  }

  function artistCardHtml(a) {
    const color    = a.brandColor || '#7C3AED';
    const initials = (a.artistName || '?').slice(0, 2).toUpperCase();
    const avatar   = a.avatarUrl
      ? `<img src="${escAttr(a.avatarUrl)}" alt="" />`
      : initials;
    const sub  = [a.genre, a.city].filter(Boolean).join(' · ') || (a.bio || '').slice(0, 60) || 'Artiste WATT';
    const meta = `${_fmt(a.plays || 0)} écoutes`;
    const href = `/u/${encodeURIComponent(a.slug || '')}`;
    return `
      <a class="ss-artist-card" href="${escAttr(href)}">
        <span class="ss-artist-avatar" style="background:${escAttr(color)};color:#fff">${avatar}</span>
        <span class="ss-artist-body">
          <span class="ss-artist-name">${escHtml(a.artistName || 'Artiste')}</span>
          <span class="ss-artist-sub">${escHtml(sub)}</span>
        </span>
        <span class="ss-artist-meta">${escHtml(meta)}</span>
      </a>`;
  }

  function trackCardHtml(t) {
    const color = t.color || '#7C3AED';
    const cover = t.coverUrl
      ? `<img src="${escAttr(t.coverUrl)}" alt="" />`
      : `<div class="ss-track-cover-fallback" style="background:${escAttr(color)}33">🎵</div>`;
    const sub  = [t.artistName, t.universe].filter(Boolean).join(' · ');
    const meta = `${_fmt(t.plays || 0)} écoutes`;
    const tags = t.tags
      ? t.tags.split(',').slice(0, 3).map(tag =>
          `<span class="ss-track-tag">${escHtml(tag.trim())}</span>`
        ).join('')
      : '';
    const href = t.artistSlug
      ? `/u/${encodeURIComponent(t.artistSlug)}#track-${encodeURIComponent(t.id)}`
      : '#';
    return `
      <a class="ss-track-card" href="${escAttr(href)}">
        <span class="ss-track-cover" style="background:${escAttr(color)}22">
          ${cover}
          <span class="ss-track-play-overlay">${ICO_PLAY}</span>
        </span>
        <span class="ss-track-body">
          <span class="ss-track-title">${escHtml(t.title || 'Sans titre')}</span>
          <span class="ss-track-sub">${escHtml(sub)}</span>
          ${tags ? `<span class="ss-track-tags">${tags}</span>` : ''}
        </span>
        <span class="ss-track-meta">${escHtml(meta)}</span>
      </a>`;
  }

  // ── Utils ─────────────────────────────────────────────────────────────
  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escAttr(s) { return escHtml(s); }
  function _fmt(n) {
    const num = parseInt(n, 10) || 0;
    return num >= 1000 ? (num / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(num);
  }

  // ── Init ──────────────────────────────────────────────────────────────
  function init() {
    injectStyles();
    injectButton();
  }

  // API publique — ouverture depuis un autre script ou raccourci
  window.SmyleSearch = { open: openModal, close: closeModal };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
