/* ═══════════════════════════════════════════════════════════════════════════
   WATT — library.js
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

let _libData = { prompts: [], adns: [], playlist_adns: [], album_adns: [], visual_adns: [], voices: [] };


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
  // Commutateur Musique ⇄ Image : restaure le mode + câble les onglets une
  // fois la vue principale visible (le switch vit dans #lib-main).
  _libBindModeSwitch();
}


/* ── Chargement (en parallèle) ───────────────────────────────────────────── */

async function loadAll() {
  // P1-F9 — voix (3e onglet) chargées en parallèle des 2 autres.
  // Note importante sur le shape : /api/voices/me/unlocked renvoie
  // directement une liste (pas un { items: [...] }) — le backend voices
  // n'est pas paginé contrairement à /me/library/prompts. On accède donc
  // à voicesRes.value directement, pas .items.
  const [promptsRes, adnsRes, playlistAdnsRes, albumAdnsRes, visualAdnsRes, voicesRes] = await Promise.allSettled([
    apiFetch('/me/library/prompts?per_page=100'),
    apiFetch('/me/library/adns?per_page=100'),
    apiFetch('/me/library/playlist-adns?per_page=100'),
    apiFetch('/me/library/album-adns?per_page=100'),
    apiFetch('/me/library/visual-adns?per_page=100'),
    apiFetch('/api/voices/me/unlocked'),
  ]);

  if (promptsRes.status === 'fulfilled') {
    _libData.prompts = promptsRes.value.items || [];
    renderPrompts(_libData.prompts);          // colonne recettes : audio only
    renderOwnedImages(_libData.prompts);       // colonne « Mes images » : achetées
  } else {
    _renderError('lib-prompts-list', promptsRes.reason);
  }

  // C4 « Mes images » — biblio = pur possédé. Les images LIKÉES vivent
  // désormais dans My Mix (curation), plus dans la biblio. On ne compte que
  // les achetées.
  _libUpdateImagesCount();

  if (adnsRes.status === 'fulfilled') {
    _libData.adns = adnsRes.value.items || [];
    renderAdns(_libData.adns);
  } else {
    _renderError('lib-adns-list', adnsRes.reason);
  }

  if (playlistAdnsRes.status === 'fulfilled') {
    _libData.playlist_adns = playlistAdnsRes.value.items || [];
    renderPlaylistAdns(_libData.playlist_adns);
  } else {
    _renderError('lib-playlist-adns-list', playlistAdnsRes.reason);
  }

  // C4 ADN Album — monde Image. Calque ADN Playlist (génome EXPOSÉ car payé).
  if (albumAdnsRes.status === 'fulfilled') {
    _libData.album_adns = albumAdnsRes.value.items || [];
    renderAlbumAdns(_libData.album_adns);
  } else {
    _renderError('lib-album-adns-list', albumAdnsRes.reason);
  }

  // C4 ADN Visuel artiste — monde Image. Génome COMPLET exposé car possédé.
  if (visualAdnsRes.status === 'fulfilled') {
    _libData.visual_adns = visualAdnsRes.value.items || [];
    renderVisualAdns(_libData.visual_adns);
  } else {
    _renderError('lib-visual-adns-list', visualAdnsRes.reason);
  }

  if (voicesRes.status === 'fulfilled') {
    _libData.voices = Array.isArray(voicesRes.value) ? voicesRes.value : [];
    renderVoices(_libData.voices);
  } else {
    _renderError('lib-voices-list', voicesRes.reason);
  }

  // Compteurs colonnes ADN
  // Colonne recettes = audio only → on exclut les images du compteur.
  setEl('lib-count-track-adns',    _libData.prompts.filter(p => p.product_type !== 'image').length || '—');
  setEl('lib-count-voices',        _libData.voices.length        || '—');
  setEl('lib-count-artist-adns',   _libData.adns.length          || '—');
  setEl('lib-count-playlist-adns', _libData.playlist_adns.length || '—');
  setEl('lib-count-album-adns',    _libData.album_adns.length    || '—');
  setEl('lib-count-visual-adns',   _libData.visual_adns.length   || '—');
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


/* ── Mini-player inline (bouton ▶ dans les headers cellules) ─────────────── */

function libToggleAudio(btn, audioId) {
  const audio = document.getElementById(audioId);
  if (!audio) return;
  if (audio.paused) {
    // Stopper tous les autres audios lib en cours
    document.querySelectorAll('.lib-hidden-audio').forEach(a => {
      if (a !== audio) { a.pause(); a.currentTime = 0; }
    });
    document.querySelectorAll('.lib-cell-play-btn').forEach(b => {
      if (b !== btn) b.textContent = '▶';
    });
    audio.play().catch(() => {});
    btn.textContent = '⏸';
    audio.onended = () => { btn.textContent = '▶'; };
  } else {
    audio.pause();
    btn.textContent = '▶';
  }
}


/* ── Commutateur Musique ⇄ Image (C4 biblio) ─────────────────────────────────
   Deux mondes : Musique (ADN audio) / Image (espace visuel dédié). Le mode est
   persisté dans localStorage (`lib_mode`) et restauré au chargement. Défaut =
   musique. Le show/hide se fait via les classes body lib-mode-musique /
   lib-mode-image (cf. library.css). Indépendant de marketplace.js.            */

const _LIB_MODE_KEY = 'lib_mode';

const _LIB_HERO_SUB = {
  musique: 'Tes recettes IA et ADN débloqués. Copie, réutilise, re-génère.',
  image:   'Tes images IA — achetées et likées. Ton espace visuel à toi.',
};

function _libReadMode() {
  let m = null;
  try { m = localStorage.getItem(_LIB_MODE_KEY); } catch (_) {}
  return (m === 'image') ? 'image' : 'musique';
}

function _libApplyMode(mode, opts) {
  const m = (mode === 'image') ? 'image' : 'musique';
  document.body.classList.toggle('lib-mode-musique', m === 'musique');
  document.body.classList.toggle('lib-mode-image',   m === 'image');
  document.querySelectorAll('.lib-mode-btn').forEach(btn => {
    const active = btn.dataset.mode === m;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', String(active));
  });
  const sub = getEl('lib-hero-sub');
  if (sub && _LIB_HERO_SUB[m]) sub.textContent = _LIB_HERO_SUB[m];
  if (!opts || opts.persist !== false) {
    try { localStorage.setItem(_LIB_MODE_KEY, m); } catch (_) {}
  }
}

function _libBindModeSwitch() {
  const sw = getEl('lib-mode-switch');
  if (sw) {
    sw.addEventListener('click', (e) => {
      const btn = e.target.closest('.lib-mode-btn');
      if (!btn) return;
      _libApplyMode(btn.dataset.mode);
    });
  }
  // Restaure le mode persisté (sans réécrire la clé : persist=false).
  _libApplyMode(_libReadMode(), { persist: false });
}


/* ── Toggle colonne ADN dépliable ───────────────────────────────────────── */

function toggleAdnCol(col) {
  const body  = document.getElementById('lib-col-' + col + '-body');
  const arrow = document.getElementById('lib-arrow-' + col);
  const btn   = body && body.previousElementSibling;
  if (!body) return;
  const isOpen = body.classList.toggle('is-open');
  if (arrow) arrow.textContent = isOpen ? '▲' : '▼';
  if (btn)   btn.setAttribute('aria-expanded', String(isOpen));
}

/* ── Tabs (legacy, masqué en CSS) ───────────────────────────────────────── */
function switchTab(tab) {
  document.querySelectorAll('.lib-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  document.querySelectorAll('.lib-tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `lib-panel-${tab}`);
  });
}


/* ── Render image possédée (C4 ④) ────────────────────────────────────────── */

// URL same-origin de l'aperçu via le proxy backend (sert UNIQUEMENT
// images/previews/). Identique à _imgPreviewUrl de marketplace.js.
function libImgPreviewUrl(key) {
  if (!key) return '';
  return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
}

const IMG_PLATFORM_LBL_LIB = {
  midjourney: 'Midjourney', dalle: 'DALL·E', stable_diffusion: 'Stable Diffusion',
  flux: 'Flux', autre: 'Autre',
};

function renderLibraryImageCell(p, i, artistName, artistLink) {
  const previewUrl = libImgPreviewUrl(p.preview_r2_key);
  const editionBadge = (p.edition_number != null && p.max_supply != null)
    ? ` <span class="lib-edition-badge" title="Exemplaire #${p.edition_number} sur ${p.max_supply} — édition limitée" style="display:inline-block;margin-left:4px;padding:1px 7px;border-radius:999px;background:rgba(124,77,255,.18);color:#cbb3ff;font-size:11px;font-weight:700;vertical-align:middle">#${p.edition_number}/${p.max_supply}</span>`
    : '';

  // Vignette d'aperçu (publique). Fallback emoji si absente.
  const previewBlock = previewUrl
    ? `<div class="lib-content-block">
         <div class="lib-content-header"><span class="lib-content-label">🖼 Aperçu</span></div>
         <div class="lib-content-body">
           <img src="${esc(previewUrl)}" alt="${esc(p.title || 'Image')}" loading="lazy"
                style="max-width:100%;border-radius:10px;display:block;border:1px solid rgba(255,255,255,.08)">
         </div>
       </div>`
    : '';

  // Provenance plateforme · version.
  const platformLbl = IMG_PLATFORM_LBL_LIB[p.image_platform] || p.image_platform || '';
  const provBadges = [platformLbl, p.image_model_version]
    .filter(Boolean).map(s => `<span class="lib-prompt-badge">${esc(s)}</span>`).join('');
  const provBlock = provBadges ? `<div class="lib-prompt-badges">${provBadges}</div>` : '';

  // Recette image (possédé → autorisé) : prompt + réglages + négatif.
  const settingsStr = (p.image_settings && typeof p.image_settings === 'object')
    ? Object.entries(p.image_settings).map(([k, v]) => `${k}: ${v}`).join(' · ')
    : '';
  const settingsBlock = settingsStr ? `
    <div class="lib-content-block">
      <div class="lib-content-header">
        <span class="lib-content-label">🎛 Réglages</span>
        <button class="lib-copy-btn" onclick="copyContent('lib-imgset-${i}', this)">Copier</button>
      </div>
      <div class="lib-content-body lib-content-body-short" id="lib-imgset-${i}">${esc(settingsStr)}</div>
    </div>` : '';
  const negBlock = (p.negative_prompt && p.negative_prompt.trim()) ? `
    <div class="lib-content-block">
      <div class="lib-content-header">
        <span class="lib-content-label">🚫 Prompt négatif</span>
        <button class="lib-copy-btn" onclick="copyContent('lib-imgneg-${i}', this)">Copier</button>
      </div>
      <div class="lib-content-body" id="lib-imgneg-${i}">${esc(p.negative_prompt)}</div>
    </div>` : '';

  const promptBlock = `
    <div class="lib-content-block">
      <div class="lib-content-header">
        <span class="lib-content-label">🎨 Prompt image</span>
        <button class="lib-copy-btn" onclick="copyContent('lib-imgprompt-${i}', this)">Copier</button>
      </div>
      <div class="lib-content-body" id="lib-imgprompt-${i}">${esc(p.prompt_text || '')}</div>
    </div>`;

  // Download de l'ORIGINAL — endpoint DÉDIÉ image (gaté possession serveur).
  const downloadBlock = `
    <div class="lib-content-block">
      <div class="lib-content-header"><span class="lib-content-label">🖼 Image originale</span></div>
      <div class="lib-content-body">
        <button class="lib-copy-btn" onclick="libDownloadImage('${p.prompt_id}', this)">⬇ Télécharger l'image</button>
        <span style="display:block;margin-top:4px;font-size:11px;color:#a09cb8">Achat = image originale + recette — le fichier exact est à toi.</span>
      </div>
    </div>`;

  // C4 galerie avatar — set de visuels supplémentaires livrés à l'achat.
  // Chaque entrée a un downloadUrl gaté (acheteur/owner). Le bouton télécharge
  // TOUT le set d'un clic (en plus de l'original principal + la recette).
  const gallery = Array.isArray(p.gallery) ? p.gallery : [];
  const galleryBlock = gallery.length ? `
    <div class="lib-content-block">
      <div class="lib-content-header"><span class="lib-content-label">🖼 Galerie incluse (${gallery.length})</span></div>
      <div class="lib-content-body">
        <button class="lib-copy-btn" onclick='libDownloadImageSet(${JSON.stringify(gallery.map(g => g.downloadUrl))}, this)'>⬇ Télécharger le set (${gallery.length})</button>
        <span style="display:block;margin-top:4px;font-size:11px;color:#a09cb8">Tous les visuels de l'avatar en haute définition — un clic télécharge l'ensemble.</span>
      </div>
    </div>` : '';

  // Revente — bloc générique inchangé (mécanique resale partagée).
  const resaleBlock = `
    <div class="lib-content-block">
      <div class="lib-content-header"><span class="lib-content-label">💱 Revente</span></div>
      ${p.resale_price != null
        ? `<div class="lib-content-body" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
             <span style="color:#4ADE80;font-weight:700;">En vente : ${p.resale_price} Smyles</span>
             <button class="lib-copy-btn" onclick="libUnlistResale('${p.prompt_id}')">Retirer de la vente</button>
           </div>`
        : `<div class="lib-content-body" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
             <button class="lib-copy-btn" onclick="libListResale('${p.prompt_id}')">Mettre en vente</button>
             <span style="font-size:11px;color:#a09cb8;">Transfert : tu cèdes cette image. L'artiste d'origine touche une royaltie.</span>
           </div>`}
    </div>`;

  return `
    <details class="lib-item-cell" style="border-left:3px solid #7c4dff">
      <summary class="lib-item-cell-hdr">
        <span class="lib-item-cell-icon">🖼</span>
        <span class="lib-item-cell-info">
          <span class="lib-item-cell-title">${esc(p.title || 'Image IA')}${editionBadge}</span>
          <span class="lib-item-cell-meta">🖼 Image · par ${esc(artistName)} · ${fmtDate(p.unlocked_at)}</span>
        </span>
        <span class="lib-item-cell-chevron">▼</span>
      </summary>
      <div class="lib-item-cell-body">
        <div class="lib-item-artist">par ${artistLink}</div>
        ${p.description ? `<div class="lib-item-desc">${esc(p.description)}</div>` : ''}
        ${provBlock}
        ${previewBlock}
        ${promptBlock}
        ${settingsBlock}
        ${negBlock}
        ${downloadBlock}
        ${galleryBlock}
        ${resaleBlock}
      </div>
    </details>`;
}

// Download de l'ORIGINAL d'une image possédée (endpoint dédié, gaté serveur).
async function libDownloadImage(imageId, btn) {
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Téléchargement…'; }
  try {
    const resp = await apiFetch('/images/' + encodeURIComponent(imageId) + '/download', { raw: true });
    if (!resp || !resp.ok) {
      if (window.smyleToast) window.smyleToast('Téléchargement indisponible.', { type: 'error' });
      return;
    }
    const cd = resp.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = (m && m[1]) ? m[1] : 'image';
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  } catch (_) {
    if (window.smyleToast) window.smyleToast('Échec du téléchargement.', { type: 'error' });
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

// C4 galerie avatar — télécharge TOUT le set (chaque downloadUrl gaté serveur),
// séquentiellement pour ne pas saturer. Un clic = tout le set de l'avatar.
async function libDownloadImageSet(urls, btn) {
  if (!Array.isArray(urls) || !urls.length) return;
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; }
  let okCount = 0;
  for (let i = 0; i < urls.length; i++) {
    if (btn) btn.textContent = 'Téléchargement ' + (i + 1) + '/' + urls.length + '…';
    try {
      const resp = await apiFetch(urls[i], { raw: true });
      if (!resp || !resp.ok) continue;
      const cd = resp.headers.get('Content-Disposition') || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = (m && m[1]) ? m[1] : ('visuel-' + (i + 1));
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      okCount++;
      // Petit délai entre les téléchargements (les navigateurs throttlent
      // les clics programmatiques trop rapprochés).
      await new Promise(r => setTimeout(r, 350));
    } catch (_) { /* on continue le set malgré un échec ponctuel */ }
  }
  if (btn) { btn.disabled = false; btn.textContent = old; }
  if (window.smyleToast) {
    window.smyleToast(
      okCount === urls.length ? 'Set téléchargé ✓' : (okCount + '/' + urls.length + ' visuels téléchargés.'),
      { type: okCount ? 'success' : 'error' }
    );
  }
}

if (typeof window !== 'undefined') {
  window.libDownloadImage = libDownloadImage;
  window.libDownloadImageSet = libDownloadImageSet;
}


/* ── Colonne « Mes images » — Achetées (C4) ──────────────────────────────────
   Réutilise renderLibraryImageCell (card image possédée complète : aperçu +
   recette image + download original + revente). On filtre les images dans la
   liste /me/library/prompts (les mêmes items, juste routés ici au lieu de la
   colonne recettes audio).                                                    */

function renderOwnedImages(items) {
  const el = getEl('lib-images-owned-list');
  if (!el) return;

  const imgs = (items || []).filter(p => p.product_type === 'image');
  if (!imgs.length) {
    el.innerHTML = `<div class="lib-empty">Aucune image achetée.<br>
      <a href="/images" class="lib-empty-cta">Explorer le monde Visuel →</a></div>`;
    return;
  }

  el.innerHTML = imgs.map((p, i) => {
    const artist     = p.artist || {};
    const slug       = artist.slug || '';
    const artistName = artist.artist_name || artist.artistName || 'Artiste';
    const artistLink = slug
      ? `<a href="/@${esc(slug)}">${esc(artistName)}</a>`
      : esc(artistName);
    // Index unique préfixé pour ne pas collisionner avec d'autres cellules.
    return renderLibraryImageCell(p, 'own' + i, artistName, artistLink);
  }).join('');
}


/* ── Colonne « Mes images » — compteur (C4) ──────────────────────────────────
   La biblio = pur POSSÉDÉ. Les images LIKÉES ont migré dans My Mix (monde
   curation). On ne compte donc QUE les images achetées.                      */

// Compteur colonne « Mes images » : nombre d'images achetées uniquement.
function _libUpdateImagesCount() {
  const owned = (_libData.prompts || []).filter(p => p.product_type === 'image').length;
  setEl('lib-count-images', owned ? String(owned) : '—');
}

if (typeof window !== 'undefined') {
  window.renderOwnedImages = renderOwnedImages;
}


/* ── Render prompts ──────────────────────────────────────────────────────── */

function renderPrompts(items) {
  const el = getEl('lib-prompts-list');
  if (!el) return;

  // C4 « Mes images » — la colonne recettes redevient 100 % AUDIO. Les images
  // possédées (product_type==='image') partent dans la colonne « Mes images »
  // (renderOwnedImages, appelé séparément depuis loadAll). On les exclut ici.
  items = (items || []).filter(p => p.product_type !== 'image');

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu ne possèdes pas encore de recette.<br>
        <a href="/" class="lib-empty-cta">Explorer la marketplace →</a>
      </div>`;
    return;
  }

  // P1-F4 enrichi (Sprint 1 PR3 2026-05-04) — affichage des réglages
  // génération révélés après achat. Plateforme + Modèle + Vocal sont
  // visibles partout. Weirdness + Style Influence sont GATED (cachés
  // sur la card publique, révélés ici dans /library après unlock).
  const PROMPT_PLATFORM_LBL = {
    suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion',
    stable_audio: 'Stable Audio', autre: 'Autre',
  };
  const PROMPT_VOCAL_LBL = {
    masculin: '🎙 Voix masculine',
    feminin: '🎙 Voix féminine',
    instrumental: '🎵 Instrumental',
  };

  el.innerHTML = items.map((p, i) => {
    const artist   = p.artist || {};
    const hasLyrics= !!(p.lyrics && p.lyrics.trim());
    const slug     = artist.slug || '';
    const artistName = artist.artist_name || artist.artistName || 'Artiste';
    const artistLink = slug
      ? `<a href="/@${esc(slug)}">${esc(artistName)}</a>`
      : esc(artistName);

    // C4 ④ — une image possédée se rend différemment d'un son (pas de Track,
    // donc pas d'audio/cover ; vignette d'aperçu + recette image + download
    // via /images/{id}/download au lieu de /products/{id}/download).
    if (p.product_type === 'image') {
      return renderLibraryImageCell(p, i, artistName, artistLink);
    }

    const lyricsBlock = hasLyrics ? `
      <div class="lib-content-block lyrics">
        <div class="lib-content-header">
          <span class="lib-content-label">🎤 Paroles</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-lyrics-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-lyrics-${i}">${esc(p.lyrics)}</div>
      </div>` : '';

    const platformLbl = PROMPT_PLATFORM_LBL[p.prompt_platform] || p.prompt_platform || '';
    const vocalLbl = PROMPT_VOCAL_LBL[p.prompt_vocal_gender] || '';
    const settingsBadges = [platformLbl, p.prompt_model_version, vocalLbl]
      .filter(Boolean).map(s => `<span class="lib-prompt-badge">${esc(s)}</span>`).join('');
    const settingsBadgesBlock = settingsBadges
      ? `<div class="lib-prompt-badges">${settingsBadges}</div>` : '';

    const weirdnessBlock = p.prompt_weirdness ? `
      <div class="lib-content-block">
        <div class="lib-content-header"><span class="lib-content-label">🎛 Weirdness</span></div>
        <div class="lib-content-body lib-content-body-short">${esc(p.prompt_weirdness)}</div>
      </div>` : '';

    const styleInfluenceBlock = p.prompt_style_influence ? `
      <div class="lib-content-block">
        <div class="lib-content-header"><span class="lib-content-label">✨ Style influence</span></div>
        <div class="lib-content-body lib-content-body-short">${esc(p.prompt_style_influence)}</div>
      </div>` : '';

    const audioBlock = p.audio_url ? `
      <div class="lib-content-block">
        <div class="lib-content-header"><span class="lib-content-label">🔊 Morceau</span></div>
        <div class="lib-content-body lib-voice-audio-wrap">
          <audio controls preload="none" src="${esc(p.audio_url)}" class="lib-voice-audio"></audio>
        </div>
      </div>` : '';

    // Marché secondaire — mettre en vente / retirer (transfert de propriété).
    const resaleBlock = `
      <div class="lib-content-block">
        <div class="lib-content-header"><span class="lib-content-label">💱 Revente</span></div>
        ${p.resale_price != null
          ? `<div class="lib-content-body" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
               <span style="color:#4ADE80;font-weight:700;">En vente : ${p.resale_price} Smyles</span>
               <button class="lib-copy-btn" onclick="libUnlistResale('${p.prompt_id}')">Retirer de la vente</button>
             </div>`
          : `<div class="lib-content-body" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
               <button class="lib-copy-btn" onclick="libListResale('${p.prompt_id}')">Mettre en vente</button>
               <span style="font-size:11px;color:#a09cb8;">Transfert : tu cèdes ce son. L'artiste d'origine touche une royaltie.</span>
             </div>`}
      </div>`;

    // C2 — DOWNLOAD UNIVERSEL : tout exemplaire possédé donne droit au
    // fichier (« achat = fichier + recette »), plus seulement les beats.
    const downloadBlock = `
      <div class="lib-content-block">
        <div class="lib-content-header"><span class="lib-content-label">${p.product_type === 'beat' ? '🎚 Beat' : '🎵 Fichier audio'}</span></div>
        <div class="lib-content-body">
          <button class="lib-copy-btn" onclick="libDownloadProduct('${p.prompt_id}', this)">⬇ Télécharger le fichier</button>
          <span style="display:block;margin-top:4px;font-size:11px;color:#a09cb8">Achat = fichier + recette — le fichier exact est à toi.</span>
        </div>
      </div>`;

    const cellStyle = p.track_color ? ` style="border-left:3px solid ${esc(p.track_color)}"` : '';
    const playBtn = p.audio_url ? `
      <audio id="lib-audio-${i}" src="${esc(p.audio_url)}" preload="none" class="lib-hidden-audio"></audio>
      <button class="lib-cell-play-btn" onclick="event.stopPropagation();event.preventDefault();libToggleAudio(this,'lib-audio-${i}')" aria-label="Écouter">▶</button>` : '';
    return `
      <details class="lib-item-cell"${cellStyle}>
        <summary class="lib-item-cell-hdr">
          <span class="lib-item-cell-icon">🎵</span>
          <span class="lib-item-cell-info">
            <span class="lib-item-cell-title">${esc(p.title || 'Recette IA')}${(p.edition_number != null && p.max_supply != null) ? ` <span class="lib-edition-badge" title="Exemplaire #${p.edition_number} sur ${p.max_supply} — édition limitée" style="display:inline-block;margin-left:4px;padding:1px 7px;border-radius:999px;background:rgba(124,77,255,.18);color:#cbb3ff;font-size:11px;font-weight:700;vertical-align:middle">#${p.edition_number}/${p.max_supply}</span>` : ''}</span>
            <span class="lib-item-cell-meta">par ${esc(artistName)} · ${fmtDate(p.unlocked_at)}</span>
          </span>
          ${playBtn}
          <span class="lib-item-cell-chevron">▼</span>
        </summary>
        <div class="lib-item-cell-body">
          <div class="lib-item-artist">par ${artistLink}</div>
          ${p.description ? `<div class="lib-item-desc">${esc(p.description)}</div>` : ''}
          ${settingsBadgesBlock}
          ${audioBlock}
          <div class="lib-content-block">
            <div class="lib-content-header">
              <span class="lib-content-label">🎛 Prompt IA</span>
              <button class="lib-copy-btn" onclick="copyContent('lib-prompt-${i}', this)">Copier</button>
            </div>
            <div class="lib-content-body" id="lib-prompt-${i}">${esc(p.prompt_text || '')}</div>
          </div>
          ${weirdnessBlock}
          ${styleInfluenceBlock}
          ${lyricsBlock}
          ${downloadBlock}
          ${resaleBlock}
        </div>
      </details>`;
  }).join('');
}

// ── Marché secondaire : mettre en vente / retirer (transfert de propriété) ──
async function libListResale(promptId) {
  // Avertissement EXPLICITE : la revente = transfert de propriété. Le vendeur
  // PERD définitivement l'accès au prompt une fois acheté.
  const ok = window.confirm(
    '⚠️ Mettre en revente = TRANSFERT de propriété.\n\n' +
    'Dès qu\'un acheteur l\'achète, tu PERDS définitivement l\'accès à cette recette ' +
    '(comme une carte que tu vends — tu ne pourras plus l\'utiliser).\n\n' +
    'En échange : tu touches le prix de revente, et le créateur d\'origine touche une royaltie.\n\n' +
    'Veux-tu vraiment la mettre en revente ?'
  );
  if (!ok) return;
  const raw = window.prompt('Prix de revente en Smyles ?');
  if (raw == null) return;
  const price = parseInt(raw, 10);
  if (!Number.isInteger(price) || price < 1) {
    if (window.smyleToast) window.smyleToast('Prix invalide.', { type: 'error' });
    return;
  }
  try {
    await apiFetch(`/resale/prompts/${promptId}/list`, { method: 'POST', json: { price } });
    if (window.smyleToast) window.smyleToast('Mis en vente sur le marché secondaire ✓', { type: 'success' });
    location.reload();
  } catch (e) {
    if (window.smyleToast) window.smyleToast('Échec de la mise en vente.', { type: 'error' });
  }
}

async function libUnlistResale(promptId) {
  try {
    await apiFetch(`/resale/prompts/${promptId}/list`, { method: 'DELETE' });
    if (window.smyleToast) window.smyleToast('Retiré de la vente ✓', { type: 'success' });
    location.reload();
  } catch (e) {
    if (window.smyleToast) window.smyleToast('Échec du retrait.', { type: 'error' });
  }
}

// C2 — Télécharge le fichier de TOUT exemplaire possédé (download gaté
// côté serveur : GET /products/{id}/download, recette OU beat legacy).
// apiFetch ajoute le Bearer ; raw:true renvoie la Response brute → blob.
async function libDownloadProduct(productId, btn) {
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Téléchargement…'; }
  try {
    const resp = await apiFetch('/products/' + encodeURIComponent(productId) + '/download', { raw: true });
    if (!resp || !resp.ok) {
      if (window.smyleToast) window.smyleToast('Téléchargement indisponible.', { type: 'error' });
      return;
    }
    const cd = resp.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = (m && m[1]) ? m[1] : 'exemplaire';
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  } catch (_) {
    if (window.smyleToast) window.smyleToast('Échec du téléchargement.', { type: 'error' });
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

if (typeof window !== 'undefined') {
  window.libListResale = libListResale;
  window.libUnlistResale = libUnlistResale;
  window.libDownloadProduct = libDownloadProduct;
  window.libDownloadBeat = libDownloadProduct; // alias rétro-compat
}


/* ── Render ADN Playlist ─────────────────────────────────────────────────── */

function renderPlaylistAdns(items) {
  const el = getEl('lib-playlist-adns-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Aucun ADN Playlist débloqué.<br>
        <a href="/" class="lib-empty-cta">Explorer les univers →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((p, i) => {
    const owner = p.owner || {};
    const slug  = owner.slug || '';
    const ownerName = owner.artist_name || 'Artiste';
    const color = p.color || '#cc88ff';
    const ownerLink = slug
      ? `<a href="/@${esc(slug)}">${esc(ownerName)}</a>`
      : esc(ownerName);

    const seedBlock = p.seed_prompt ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🧬 ADN</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-pl-adn-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-pl-adn-${i}">${esc(p.seed_prompt)}</div>
      </div>` : '';

    return `
      <details class="lib-item-cell" style="border-left:3px solid ${esc(color)}">
        <summary class="lib-item-cell-hdr">
          <span class="lib-item-cell-icon" style="color:${esc(color)}">🧬</span>
          <span class="lib-item-cell-info">
            <span class="lib-item-cell-title">${esc(p.title || 'Playlist')}</span>
            <span class="lib-item-cell-meta">univers ${esc(ownerName)} · ${fmtDate(p.owned_at)}</span>
          </span>
          <span class="lib-item-cell-chevron">▼</span>
        </summary>
        <div class="lib-item-cell-body">
          <div class="lib-item-artist">univers de ${ownerLink}</div>
          <div class="lib-item-desc">-20% sur tous les ADN Track de cette playlist</div>
          ${seedBlock}
          ${slug ? `<a href="/@${esc(slug)}" class="lib-cell-goto-btn" style="border-color:${esc(color)};color:${esc(color)}">→ Voir la playlist</a>` : ''}
        </div>
      </details>`;
  }).join('');
}


/* ── Render ADN Album (monde Image) ───────────────────────────────────────────
   Calque renderPlaylistAdns. Le génome (seed_prompt + adn_palette) est EXPOSÉ
   ici car l'utilisateur a payé (cf. /me/library/album-adns).                  */

function renderAlbumAdns(items) {
  const el = getEl('lib-album-adns-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Aucun ADN Album débloqué.<br>
        <a href="/images" class="lib-empty-cta">Explorer le monde Visuel →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((a, i) => {
    const owner = a.owner || {};
    const slug  = owner.slug || '';
    const ownerName = owner.artist_name || owner.artistName || 'Artiste';
    const ownerLink = slug
      ? `<a href="/@${esc(slug)}">${esc(ownerName)}</a>`
      : esc(ownerName);
    const styleChip = a.adn_style
      ? `<span class="lib-adn-style-chip">${esc(a.adn_style)}</span>` : '';

    const seedBlock = a.seed_prompt ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🧬 Génome</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-al-adn-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-al-adn-${i}">${esc(a.seed_prompt)}</div>
      </div>` : '';

    const paletteBlock = a.adn_palette ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🎨 Palette</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-al-pal-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-al-pal-${i}">${esc(a.adn_palette)}</div>
      </div>` : '';

    return `
      <details class="lib-item-cell" style="border-left:3px solid #cc88ff">
        <summary class="lib-item-cell-hdr">
          <span class="lib-item-cell-icon" style="color:#cc88ff">🎨</span>
          <span class="lib-item-cell-info">
            <span class="lib-item-cell-title">${esc(a.title || 'Album')} ${styleChip}</span>
            <span class="lib-item-cell-meta">univers ${esc(ownerName)} · ${fmtDate(a.owned_at)}</span>
          </span>
          <span class="lib-item-cell-chevron">▼</span>
        </summary>
        <div class="lib-item-cell-body">
          <div class="lib-item-artist">univers de ${ownerLink}</div>
          ${a.dna_description ? `<div class="lib-item-desc">${esc(a.dna_description)}</div>` : ''}
          ${paletteBlock}
          ${seedBlock}
          ${slug ? `<a href="/@${esc(slug)}" class="lib-cell-goto-btn" style="border-color:#cc88ff;color:#cc88ff">→ Voir l'univers</a>` : ''}
        </div>
      </details>`;
  }).join('');
}


/* ── Render ADN Visuel artiste (monde Image) ──────────────────────────────────
   Calque renderAlbumAdns. Génome COMPLET exposé (description + palette +
   example_outputs) car possédé (cf. /me/library/visual-adns).                 */

function renderVisualAdns(items) {
  const el = getEl('lib-visual-adns-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Aucun ADN Visuel débloqué.<br>
        <a href="/images" class="lib-empty-cta">Explorer le monde Visuel →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((a, i) => {
    const artist = a.artist || {};
    const slug   = artist.slug || '';
    const artistName = artist.artist_name || artist.artistName || 'Artiste';
    const artistLink = slug
      ? `<a href="/@${esc(slug)}">${esc(artistName)}</a>`
      : esc(artistName);
    const styleChip = a.style
      ? `<span class="lib-adn-style-chip">${esc(a.style)}</span>` : '';

    const descBlock = a.description ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🧬 Génome</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-vadn-desc-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-vadn-desc-${i}">${esc(a.description)}</div>
      </div>` : '';

    const paletteBlock = a.palette ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🎨 Palette</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-vadn-pal-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-vadn-pal-${i}">${esc(a.palette)}</div>
      </div>` : '';

    const guideBlock = a.usage_guide ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">📘 Guide d'usage</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-vadn-guide-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-vadn-guide-${i}">${esc(a.usage_guide)}</div>
      </div>` : '';

    const examplesBlock = a.example_outputs ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🖼️ Exemples</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-vadn-ex-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-vadn-ex-${i}">${esc(a.example_outputs)}</div>
      </div>` : '';

    return `
      <details class="lib-item-cell" style="border-left:3px solid #cc88ff">
        <summary class="lib-item-cell-hdr">
          <span class="lib-item-cell-icon" style="color:#cc88ff">🎨</span>
          <span class="lib-item-cell-info">
            <span class="lib-item-cell-title">ADN visuel · ${esc(artistName)} ${styleChip}</span>
            <span class="lib-item-cell-meta">signature visuelle · ${fmtDate(a.owned_at)}</span>
          </span>
          <span class="lib-item-cell-chevron">▼</span>
        </summary>
        <div class="lib-item-cell-body">
          <div class="lib-item-artist">signature de ${artistLink}</div>
          ${paletteBlock}
          ${descBlock}
          ${guideBlock}
          ${examplesBlock}
          ${slug ? `<a href="/@${esc(slug)}" class="lib-cell-goto-btn" style="border-color:#cc88ff;color:#cc88ff">→ Voir l'univers</a>` : ''}
        </div>
      </details>`;
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
    const artistName = artist.artist_name || artist.artistName || 'Artiste';
    const artistLink = slug
      ? `<a href="/@${esc(slug)}">${esc(artistName)}</a>`
      : esc(artistName);

    const usageBlock = a.usage_guide ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">📘 Usage</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-usage-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-usage-${i}">${esc(a.usage_guide)}</div>
      </div>` : '';

    const exampleBlock = a.example_outputs ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">✨ Exemples</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-ex-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-ex-${i}">${esc(a.example_outputs)}</div>
      </div>` : '';

    const rawKind = String(a.kind || a.adn_type || a.type || 'playlist').toLowerCase();
    const isArtist = rawKind === 'artist' || rawKind === 'artiste' || rawKind === 'profile';
    const kindLabel = isArtist ? 'ADN Artiste' : 'ADN Playlist';
    const kindSub   = isArtist ? `signature complète de ${artistLink}` : `univers de ${artistLink}`;

    return `
      <details class="lib-item-cell" style="border-left:3px solid ${esc(brand)}">
        <summary class="lib-item-cell-hdr">
          <span class="lib-item-cell-icon">🧬</span>
          <span class="lib-item-cell-info">
            <span class="lib-item-cell-title">${esc(artistName)}</span>
            <span class="lib-item-cell-meta">${kindLabel} · ${fmtDate(a.owned_at)}</span>
          </span>
          <span class="lib-item-cell-chevron">▼</span>
        </summary>
        <div class="lib-item-cell-body">
          <div class="lib-item-artist">${kindSub}</div>
          ${a.description ? `<div class="lib-item-desc">${esc(a.description)}</div>` : ''}
          ${usageBlock}
          ${exampleBlock}
        </div>
      </details>`;
  }).join('');
}


/* ── Render Voices (P1-F9) ───────────────────────────────────────────────
   Affiche les voix unlock par l'user (GET /api/voices/me/unlocked).
   Chaque card expose :
   - nom + style + licence
   - genres compatibles
   - lecteur audio inline (sample_url R2)
   - bouton "Télécharger" (a download de sample_url)

   Note sur l'absence de nom d'artiste : le backend /api/voices renvoie
   uniquement artist_id (pas le payload artist enrichi). Pour la 1re
   version, on laisse l'utilisateur cliquer "Voir l'artiste" → /u/<id>
   (résolu côté serveur). On enrichira plus tard si besoin (effort
   minimal côté backend pour ajouter artist_name + slug).                  */

const VOICE_LICENSE_LBL_LIB = {
  personnel:  'Personnel',
  commercial: 'Commercial',
  exclusif:   'Exclusif',
};

const VOICE_GENRES_LBL_LIB = {
  rnb: 'RnB', pop: 'Pop', trap: 'Trap', rap: 'Rap', electro: 'Electro',
  house: 'House', afro: 'Afro', jazz: 'Jazz', soul: 'Soul', rock: 'Rock',
  autre: 'Autre',
};

function _libVoiceGenresStr(keys) {
  if (!Array.isArray(keys) || !keys.length) return '';
  return keys.map(k => VOICE_GENRES_LBL_LIB[k] || k).join(' · ');
}

function renderVoices(items) {
  const el = getEl('lib-voices-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu n'as pas encore débloqué de voix.<br>
        <span class="lib-empty-note">Une voix débloquée te donne le fichier vocal complet. Choisis-la sur le profil de l'artiste ou sur la page /voix.</span><br>
        <a href="/voix" class="lib-empty-cta">Explorer les voix →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((v, i) => {
    // Chantier Voix — rareté #X/N à la place du vocabulaire licence.
    const license = (v.max_supply != null)
      ? (v.max_supply === 1 ? '1/1 vente unique' : 'Édition limitée · ' + v.max_supply + ' ex.')
      : '';
    const genres  = _libVoiceGenresStr(v.genres);
    const artist = v.artist || null;
    const artistName = (artist && artist.artist_name) || '';
    const artistSlug = (artist && artist.slug) || '';
    const brandColor = (artist && artist.brand_color) || '';
    const artistBlock = artistName
      ? (artistSlug
          ? `<div class="lib-item-artist">par <a href="/@${esc(artistSlug)}">${esc(artistName)}</a></div>`
          : `<div class="lib-item-artist">par ${esc(artistName)}</div>`)
      : '';
    const dlBtn = v.sample_url
      ? `<a href="${esc(v.sample_url)}" download class="lib-copy-btn">Télécharger</a>`
      : `<span class="lib-copy-btn" style="opacity:.5">Indisponible</span>`;
    const audioBlock = v.sample_url
      ? `<div class="lib-content-block">
           <div class="lib-content-header">
             <span class="lib-content-label">🎙 Sample</span>
             ${dlBtn}
           </div>
           <div class="lib-content-body lib-voice-audio-wrap">
             <audio controls preload="none" src="${esc(v.sample_url)}" class="lib-voice-audio"></audio>
           </div>
         </div>` : '';
    const cellStyle = brandColor ? ` style="border-left:3px solid ${esc(brandColor)}"` : '';
    const voicePlayBtn = v.sample_url ? `
      <audio id="lib-vaudio-${i}" src="${esc(v.sample_url)}" preload="none" class="lib-hidden-audio"></audio>
      <button class="lib-cell-play-btn" onclick="event.stopPropagation();event.preventDefault();libToggleAudio(this,'lib-vaudio-${i}')" aria-label="Écouter">▶</button>` : '';
    return `
      <details class="lib-item-cell"${cellStyle}>
        <summary class="lib-item-cell-hdr">
          <span class="lib-item-cell-icon">🎙</span>
          <span class="lib-item-cell-info">
            <span class="lib-item-cell-title">${esc(v.name || 'Voix')}</span>
            <span class="lib-item-cell-meta">${esc(license)}${artistName ? ' · ' + esc(artistName) : ''}</span>
          </span>
          ${voicePlayBtn}
          <span class="lib-item-cell-chevron">▼</span>
        </summary>
        <div class="lib-item-cell-body">
          ${artistBlock}
          ${v.style ? `<div class="lib-item-desc">${esc(v.style)}</div>` : ''}
          ${genres ? `<div class="lib-item-artist">Genres : ${esc(genres)}</div>` : ''}
          ${audioBlock}
        </div>
      </details>`;
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
