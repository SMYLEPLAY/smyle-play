/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — library.js
   Page /library · contenu possédé (prompts IA + ADN Playlists débloqués)
   Backend : GET /me/library/prompts · GET /me/library/adns (auth requis)
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s || '');
  return d.innerHTML;
}

function getEl(id) { return document.getElementById(id); }

function setEl(id, v) {
  const el = getEl(id);
  if (el) el.textContent = String(v ?? '');
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch (_) { return '—'; }
}

let _libData = { prompts: [], adns: [] };


/* ── Init + auth gate ────────────────────────────────────────────────────── */

async function init() {
  // Pas connecté → page verrouillée
  if (typeof getAuthToken !== 'function' || !getAuthToken()) {
    _showLocked();
    return;
  }

  // Connecté mais token invalide → on teste /users/me, sinon lock
  try {
    await apiFetch('/users/me');
  } catch (err) {
    if (err && err.status === 401) {
      if (typeof clearAuthToken === 'function') clearAuthToken();
      _showLocked();
      return;
    }
    // Autres erreurs : on laisse passer et on tente quand même le chargement
  }

  _showMain();
  loadAll();
}

function _showLocked() {
  const locked = getEl('lib-locked');
  const main   = getEl('lib-main');
  if (locked) locked.style.display = '';
  if (main)   main.style.display   = 'none';
}
function _showMain() {
  const locked = getEl('lib-locked');
  const main   = getEl('lib-main');
  if (locked) locked.style.display = 'none';
  if (main)   main.style.display   = '';
}


/* ── Chargement (en parallèle) ───────────────────────────────────────────── */

async function loadAll() {
  const [promptsRes, adnsRes] = await Promise.allSettled([
    apiFetch('/me/library/prompts?per_page=100'),
    apiFetch('/me/library/adns?per_page=100'),
  ]);

  if (promptsRes.status === 'fulfilled') {
    _libData.prompts = promptsRes.value.items || [];
    renderPrompts(_libData.prompts);
  } else {
    _renderError('lib-prompts-list', promptsRes.reason);
  }

  if (adnsRes.status === 'fulfilled') {
    _libData.adns = adnsRes.value.items || [];
    renderAdns(_libData.adns);
  } else {
    _renderError('lib-adns-list', adnsRes.reason);
  }

  setEl('lib-count-prompts', _libData.prompts.length);
  setEl('lib-count-adns',    _libData.adns.length);
}

function _renderError(containerId, err) {
  const el = getEl(containerId);
  if (!el) return;
  if (err && err.status === 401) {
    _showLocked();
    return;
  }
  console.warn('[library] erreur chargement :', err);
  el.innerHTML = `<div class="lib-empty">Impossible de charger ce contenu — réessaie plus tard.</div>`;
}


/* ── Tabs ────────────────────────────────────────────────────────────────── */

function switchTab(tab) {
  document.querySelectorAll('.lib-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  document.querySelectorAll('.lib-tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `lib-panel-${tab}`);
  });
}


/* ── Render prompts ──────────────────────────────────────────────────────── */

function renderPrompts(items) {
  const el = getEl('lib-prompts-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu ne possèdes pas encore de recette.<br>
        <a href="/" class="lib-empty-cta">Explorer la marketplace →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((p, i) => {
    const artist   = p.artist || {};
    const hasLyrics= !!(p.lyrics && p.lyrics.trim());
    const slug     = artist.slug || '';
    const artistLink = slug
      ? `<a href="/u/${esc(slug)}">${esc(artist.artist_name || artist.artistName || 'Artiste')}</a>`
      : esc(artist.artist_name || artist.artistName || 'Artiste');

    const lyricsBlock = hasLyrics ? `
      <div class="lib-content-block lyrics">
        <div class="lib-content-header">
          <span class="lib-content-label">🎤 Paroles</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-lyrics-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-lyrics-${i}">${esc(p.lyrics)}</div>
      </div>
    ` : '';

    return `
      <div class="lib-item">
        <div class="lib-item-head">
          <div class="lib-item-title">${esc(p.title || 'Recette IA')}</div>
          <div class="lib-item-meta">Débloqué le ${fmtDate(p.unlocked_at)}</div>
        </div>
        <div class="lib-item-artist">par ${artistLink}</div>
        ${p.description ? `<div class="lib-item-desc">${esc(p.description)}</div>` : ''}

        <div class="lib-content-block">
          <div class="lib-content-header">
            <span class="lib-content-label">🎛 Prompt IA</span>
            <button class="lib-copy-btn" onclick="copyContent('lib-prompt-${i}', this)">Copier</button>
          </div>
          <div class="lib-content-body" id="lib-prompt-${i}">${esc(p.prompt_text || '')}</div>
        </div>

        ${lyricsBlock}
      </div>`;
  }).join('');
}


/* ── Render ADN ──────────────────────────────────────────────────────────── */

function renderAdns(items) {
  const el = getEl('lib-adns-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu ne possèdes pas encore d'ADN.<br>
        <span class="lib-empty-note">L'ADN se décline en deux types&nbsp;: <b>ADN Playlist</b> (univers sonore) ou <b>ADN Artiste</b> (signature complète d'un profil).</span><br>
        <a href="/" class="lib-empty-cta">Explorer les univers →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((a, i) => {
    const artist   = a.artist || {};
    const slug     = artist.slug || '';
    const brand    = artist.brand_color || artist.brandColor || '#FFD700';
    const artistLink = slug
      ? `<a href="/u/${esc(slug)}">${esc(artist.artist_name || artist.artistName || 'Artiste')}</a>`
      : esc(artist.artist_name || artist.artistName || 'Artiste');

    const usageBlock = a.usage_guide ? `
      <span class="lib-adn-section-title">Guide d'utilisation</span>
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">📘 Usage</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-usage-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-usage-${i}">${esc(a.usage_guide)}</div>
      </div>
    ` : '';

    const exampleBlock = a.example_outputs ? `
      <span class="lib-adn-section-title">Exemples de sorties</span>
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">✨ Exemples</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-ex-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-ex-${i}">${esc(a.example_outputs)}</div>
      </div>
    ` : '';

    // Détection du sous-type d'ADN :
    //   - "artist" → ADN Artiste (signature complète de profil)
    //   - "playlist" (ou défaut) → ADN Playlist (univers sonore)
    const rawKind = String(a.kind || a.adn_type || a.type || 'playlist').toLowerCase();
    const isArtist = rawKind === 'artist' || rawKind === 'artiste' || rawKind === 'profile';
    const kindLabel = isArtist ? 'ADN Artiste' : 'ADN Playlist';
    const kindSub   = isArtist
      ? `signature complète de ${artistLink}`
      : `univers signature de ${artistLink}`;
    const kindBadgeCls = isArtist ? 'lib-adn-kind-artist' : 'lib-adn-kind-playlist';

    return `
      <div class="lib-item" style="border-left: 3px solid ${esc(brand)}">
        <div class="lib-item-head">
          <div class="lib-item-title">
            <svg class="lib-adn-dna-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14" aria-hidden="true">
              <path d="M7 3c0 4 10 6 10 10M7 11c0 4 10 6 10 10M7 21c0-4 10-6 10-10"/>
              <path d="M8 5h8M8 8h8M8 13h8M8 16h8M8 19h8" stroke-width="1.1" opacity="0.55"/>
            </svg>
            ADN — ${esc(artist.artist_name || artist.artistName || 'Artiste')}
            <span class="lib-adn-kind ${kindBadgeCls}">${kindLabel}</span>
          </div>
          <div class="lib-item-meta">Acquis le ${fmtDate(a.owned_at)}</div>
        </div>
        <div class="lib-item-artist">${kindSub}</div>
        ${a.description ? `<div class="lib-item-desc">${esc(a.description)}</div>` : ''}
        ${usageBlock}
        ${exampleBlock}
      </div>`;
  }).join('');
}


/* ── Copy ────────────────────────────────────────────────────────────────── */

function copyContent(sourceId, btn) {
  const src = getEl(sourceId);
  if (!src) return;
  const text = src.textContent;

  const done = () => {
    if (!btn) return;
    const prev = btn.textContent;
    btn.textContent = '✓ Copié';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = prev;
      btn.classList.remove('copied');
    }, 1600);
    showToast('Contenu copié dans le presse-papiers');
  };

  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(done).catch(() => _fallbackCopy(text, done));
  } else {
    _fallbackCopy(text, done);
  }
}

function _fallbackCopy(text, cb) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); cb && cb(); }
  catch (_) { showToast('Copie impossible.'); }
  document.body.removeChild(ta);
}


/* ── Toast ───────────────────────────────────────────────────────────────── */

let _toastTimer = null;
function showToast(msg) {
  const el = getEl('lib-toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}


/* ── Init ────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', init);
