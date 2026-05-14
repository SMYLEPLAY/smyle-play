/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/playlists.js
   Câblage frontend des endpoints playlists API (backend déjà complet).

   Fournit :
     • Helpers fetch typés : loadMyPlaylists, createPlaylist, deletePlaylist,
       togglePlaylistVisibility, loadArtistPublicPlaylists
     • Renderer dashboard : section "Mes playlists" (CRUD + toggle visibility)
     • Renderer profil public : section "Playlists publiques"
     • Modale création : prompt name + radio public/private (default private)

   Auth : utilise window.apiFetch ou fetch avec Bearer token via getAuthToken.
   Endpoint pour scope tracks/tracks à venir : voir PR 2a-bis (ajout
   track→playlist + lecture playlist) — pas inclus ici.

   À charger après ui/core/api.js. Modules consumers (dashboard.js,
   artiste.js) appellent renderDashboardPlaylists / renderArtistPlaylists
   après leur propre boot.
   ───────────────────────────────────────────────────────────────────────── */

(function(){
  'use strict';

  // ── 1. HELPERS API ─────────────────────────────────────────────────────────

  // Fallback minimal si apiFetch n'est pas dispo (rare — api.js charge avant)
  function _authHeaders() {
    const h = { 'Accept': 'application/json' };
    if (typeof getAuthToken === 'function') {
      const t = getAuthToken();
      if (t) h['Authorization'] = 'Bearer ' + t;
    }
    return h;
  }

  async function _req(url, opts) {
    opts = opts || {};
    const headers = Object.assign({}, _authHeaders(), opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      headers['Content-Type'] = 'application/json';
    }
    const resp = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts, { headers }));
    if (!resp.ok) {
      let detail = '';
      try {
        const body = await resp.json();
        const d = body.detail;
        if (typeof d === 'string') detail = d;
        else if (d && typeof d === 'object') detail = d.message || JSON.stringify(d);
      } catch (_) {}
      const err = new Error(detail || ('Erreur HTTP ' + resp.status));
      err.status = resp.status;
      throw err;
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  async function loadMyPlaylists() {
    return _req('/playlists/me');
  }

  async function createPlaylist(title, visibility, color, seedPrompt, adnForSale, adnPrice) {
    const body = { title: title, visibility: visibility || 'private' };
    if (color)                body.color        = color;
    if (seedPrompt)           body.seed_prompt  = seedPrompt;
    if (adnForSale)           body.adn_for_sale = true;
    if (adnPrice)             body.adn_price    = adnPrice;
    return _req('/playlists', { method: 'POST', body: body });
  }

  async function updatePlaylist(id, patch) {
    return _req('/playlists/' + encodeURIComponent(id), { method: 'PATCH', body: patch });
  }

  async function deletePlaylist(id) {
    return _req('/playlists/' + encodeURIComponent(id), { method: 'DELETE' });
  }

  async function togglePlaylistVisibility(id, currentVis) {
    const next = currentVis === 'public' ? 'private' : 'public';
    return _req('/playlists/' + encodeURIComponent(id), {
      method: 'PATCH',
      body: { visibility: next }
    });
  }

  async function loadArtistPublicPlaylists(slug) {
    return _req('/watt/users/' + encodeURIComponent(slug) + '/playlists');
  }

  // ── 2. MODALE CRÉATION ────────────────────────────────────────────────────

  function openCreatePlaylistModal(onCreated) {
    // Modal légère, injectée à la volée. Si déjà ouverte, no-op.
    if (document.getElementById('pl-create-modal')) return;

    const overlay = document.createElement('div');
    overlay.id = 'pl-create-modal';
    overlay.className = 'pl-modal-overlay';
    const DEFAULT_COLOR = '#cc88ff';

    overlay.innerHTML = (
      '<div class="pl-modal" role="dialog" aria-labelledby="pl-modal-title">' +
        '<button type="button" class="pl-modal-close" aria-label="Fermer">✕</button>' +
        '<h3 id="pl-modal-title" class="pl-modal-title">Nouvelle playlist</h3>' +

        // Nom + aperçu neon live
        '<label class="pl-modal-label">Nom' +
          '<input type="text" id="pl-modal-name" maxlength="200" placeholder="Ma playlist…" autofocus />' +
        '</label>' +
        '<div class="pl-neon-preview" id="pl-neon-preview" style="--nc:' + DEFAULT_COLOR + '">Ma playlist…</div>' +

        // Couleur neon
        '<div class="pl-modal-color-row">' +
          '<span class="pl-modal-color-label">Couleur neon</span>' +
          '<div class="pl-color-swatches" id="pl-color-swatches">' +
            ['#cc88ff','#ff6b6b','#ff9500','#ffcc00','#00e676','#00d4ff','#4488ff','#ff44cc'].map(function(c) {
              return '<button type="button" class="pl-swatch' + (c === DEFAULT_COLOR ? ' active' : '') + '" data-color="' + c + '" style="background:' + c + ';box-shadow:0 0 8px ' + c + '"></button>';
            }).join('') +
            '<input type="color" id="pl-modal-color" value="' + DEFAULT_COLOR + '" title="Couleur personnalisée" class="pl-swatch pl-swatch-custom" />' +
          '</div>' +
        '</div>' +

        // Seed prompt (ADN de la playlist)
        '<label class="pl-modal-label pl-modal-seed-label">ADN de la playlist <span class="pl-optional">(optionnel)</span>' +
          '<textarea id="pl-modal-seed" rows="2" maxlength="1000" placeholder="Décris l\'ambiance, le style, le mood… ex : deep afro house, nuit tropicale, basses lourdes"></textarea>' +
        '</label>' +

        // ADN en vente
        '<div class="pl-modal-adn-row">' +
          '<label class="pl-adn-toggle-label">' +
            '<input type="checkbox" id="pl-modal-adn-sale" /> ' +
            '<span class="pl-adn-toggle-txt">🧬 Vendre l\'ADN de cette playlist</span>' +
          '</label>' +
          '<p class="pl-adn-hint" style="margin:6px 0 0;padding:0">La playlist reste écoutable librement. L\'ADN (synthèse des prompts) est un produit séparé que les fans peuvent acheter pour recréer l\'univers.</p>' +
          '<div class="pl-adn-price-wrap" id="pl-adn-price-wrap" style="display:none">' +
            '<label class="pl-modal-label" style="margin-bottom:0">Prix en Smyles' +
              '<input type="number" id="pl-modal-adn-price" min="1" max="100000" placeholder="ex : 50" />' +
            '</label>' +
            '<p class="pl-adn-hint">⚠️ Recommandé si tous les morceaux partagent le même univers créatif</p>' +
          '</div>' +
        '</div>' +

        // Visibilité
        '<fieldset class="pl-modal-vis">' +
          '<legend>Visibilité</legend>' +
          '<label class="pl-vis-opt">' +
            '<input type="radio" name="pl-vis" value="private" checked /> ' +
            '<span><strong>Privée</strong> · visible uniquement par toi</span>' +
          '</label>' +
          '<label class="pl-vis-opt">' +
            '<input type="radio" name="pl-vis" value="public" /> ' +
            '<span><strong>Publique</strong> · visible sur ton profil</span>' +
          '</label>' +
        '</fieldset>' +

        '<div class="pl-modal-actions">' +
          '<button type="button" class="pl-btn pl-btn-ghost" id="pl-modal-cancel">Annuler</button>' +
          '<button type="button" class="pl-btn pl-btn-primary" id="pl-modal-create">Créer</button>' +
        '</div>' +
        '<div class="pl-modal-err" id="pl-modal-err" style="display:none"></div>' +
      '</div>'
    );
    document.body.appendChild(overlay);
    _injectModalStyles();

    // Live preview : nom + couleur
    const nameInput   = overlay.querySelector('#pl-modal-name');
    const colorInput  = overlay.querySelector('#pl-modal-color');
    const preview     = overlay.querySelector('#pl-neon-preview');
    const swatches    = overlay.querySelector('#pl-color-swatches');

    function _applyColor(hex) {
      colorInput.value = hex;
      preview.style.setProperty('--nc', hex);
      swatches.querySelectorAll('.pl-swatch[data-color]').forEach(function(s) {
        s.classList.toggle('active', s.dataset.color === hex);
      });
    }

    nameInput.addEventListener('input', function() {
      preview.textContent = nameInput.value.trim() || 'Ma playlist…';
    });
    colorInput.addEventListener('input', function() {
      preview.style.setProperty('--nc', colorInput.value);
      swatches.querySelectorAll('.pl-swatch[data-color]').forEach(function(s) { s.classList.remove('active'); });
    });
    swatches.addEventListener('click', function(e) {
      const sw = e.target.closest('.pl-swatch[data-color]');
      if (sw) _applyColor(sw.dataset.color);
    });

    // Toggle ADN en vente
    const adnCheckbox  = overlay.querySelector('#pl-modal-adn-sale');
    const adnPriceWrap = overlay.querySelector('#pl-adn-price-wrap');
    adnCheckbox.addEventListener('change', function() {
      adnPriceWrap.style.display = adnCheckbox.checked ? '' : 'none';
    });

    const close = () => overlay.remove();
    overlay.querySelector('.pl-modal-close').onclick = close;
    overlay.querySelector('#pl-modal-cancel').onclick = close;
    overlay.addEventListener('click', function(e) { if (e.target === overlay) close(); });

    overlay.querySelector('#pl-modal-create').onclick = async function() {
      const name       = nameInput.value.trim();
      const vis        = overlay.querySelector('input[name="pl-vis"]:checked').value;
      const color      = colorInput.value || DEFAULT_COLOR;
      const seed       = overlay.querySelector('#pl-modal-seed').value.trim();
      const adnForSale = adnCheckbox.checked;
      const adnPrice   = adnForSale ? parseInt(overlay.querySelector('#pl-modal-adn-price').value, 10) || null : null;
      const errBox = overlay.querySelector('#pl-modal-err');
      errBox.style.display = 'none';
      if (!name) {
        errBox.textContent = 'Donne un nom à ta playlist.';
        errBox.style.display = 'block';
        return;
      }
      try {
        if (adnForSale && !adnPrice) {
          errBox.textContent = 'Indique un prix en Smyles pour l\'ADN.';
          errBox.style.display = 'block';
          return;
        }
        const created = await createPlaylist(name, vis, color, seed || null, adnForSale, adnPrice);
        close();
        if (typeof onCreated === 'function') onCreated(created);
      } catch (e) {
        errBox.textContent = (e && e.status === 401)
          ? 'Connecte-toi pour créer une playlist.'
          : 'Création impossible (' + (e && e.message || 'erreur') + ').';
        errBox.style.display = 'block';
      }
    };
  }

  function _injectModalStyles() {
    if (document.getElementById('pl-modal-styles')) return;
    const css = (
      '.pl-modal-overlay {' +
        'position: fixed; inset: 0; background: rgba(0,0,0,.65);' +
        'display: flex; align-items: center; justify-content: center;' +
        'z-index: 9999; padding: 20px;' +
      '}' +
      '.pl-modal {' +
        'background: #0c0c14; color: #e8e6f5;' +
        'border: 1px solid rgba(204,136,255,.28); border-radius: 16px;' +
        'padding: 28px 26px; width: 100%; max-width: 460px;' +
        'box-shadow: 0 24px 60px rgba(0,0,0,.5); position: relative;' +
      '}' +
      '.pl-modal-close {' +
        'position: absolute; top: 12px; right: 14px;' +
        'background: transparent; color: #a09cb8; border: none;' +
        'font-size: 20px; cursor: pointer; padding: 4px 8px;' +
      '}' +
      '.pl-modal-title { margin: 0 0 18px; font-size: 20px; }' +
      '.pl-modal-label { display: flex; flex-direction: column; gap: 8px; font-size: 13px; color: #a09cb8; margin-bottom: 18px; }' +
      '.pl-modal-label input {' +
        'background: rgba(255,255,255,.04); color: #fff;' +
        'border: 1px solid rgba(204,136,255,.22); border-radius: 10px;' +
        'padding: 11px 14px; font-size: 15px; outline: none;' +
      '}' +
      '.pl-modal-label input:focus { border-color: rgba(204,136,255,.5); }' +
      '.pl-modal-vis { border: none; padding: 0; margin: 0 0 22px; }' +
      '.pl-modal-vis legend { font-size: 13px; color: #a09cb8; margin-bottom: 10px; padding: 0; }' +
      '.pl-vis-opt { display: flex; gap: 10px; padding: 10px 0; font-size: 14px; color: #c7c4d8; cursor: pointer; align-items: flex-start; }' +
      '.pl-vis-opt input { margin-top: 3px; }' +
      '.pl-vis-opt strong { color: #fff; font-weight: 600; }' +
      '.pl-modal-actions { display: flex; gap: 10px; justify-content: flex-end; }' +
      '.pl-btn { padding: 10px 18px; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; border: 1px solid transparent; }' +
      '.pl-btn-ghost { background: transparent; color: #a09cb8; border-color: rgba(255,255,255,.12); }' +
      '.pl-btn-ghost:hover { color: #fff; border-color: rgba(255,255,255,.3); }' +
      '.pl-btn-primary { background: #cc88ff; color: #0a0a12; }' +
      '.pl-btn-primary:hover { background: #d8a0ff; }' +
      '.pl-modal-err { margin-top: 14px; color: #ff8888; font-size: 13px; }' +
      // Aperçu neon live
      '@keyframes pl-neon-live { 0%,19%,21%,54%,56%,100%{text-shadow:0 0 8px var(--nc,#cc88ff),0 0 22px var(--nc,#cc88ff),0 0 45px var(--nc,#cc88ff);opacity:1}20%,55%{text-shadow:none;opacity:.72}22%{text-shadow:0 0 6px var(--nc,#cc88ff);opacity:.88} }' +
      '.pl-neon-preview { font-size:18px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; color:var(--nc,#cc88ff); animation:pl-neon-live 4s infinite; text-align:center; padding:14px 8px 10px; min-height:46px; }' +
      // Couleur swatches
      '.pl-modal-color-row { display:flex; align-items:center; gap:12px; margin-bottom:18px; }' +
      '.pl-modal-color-label { font-size:13px; color:#a09cb8; flex-shrink:0; }' +
      '.pl-color-swatches { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }' +
      '.pl-swatch { width:22px; height:22px; border-radius:50%; border:2px solid transparent; cursor:pointer; transition:transform .15s,border-color .15s; flex-shrink:0; }' +
      '.pl-swatch:hover { transform:scale(1.2); }' +
      '.pl-swatch.active { border-color:#fff; transform:scale(1.15); }' +
      '.pl-swatch-custom { width:26px; height:26px; border-radius:50%; padding:0; cursor:pointer; border:2px solid rgba(255,255,255,.2); overflow:hidden; background:conic-gradient(#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00); }' +
      // Seed prompt
      '.pl-modal-seed-label textarea { background:rgba(255,255,255,.03); color:#e8e6f5; border:1px solid rgba(204,136,255,.22); border-radius:10px; padding:10px 14px; font-size:13px; line-height:1.5; resize:vertical; outline:none; width:100%; box-sizing:border-box; font-family:inherit; }' +
      '.pl-modal-seed-label textarea:focus { border-color:rgba(204,136,255,.5); }' +
      '.pl-optional { font-size:11px; color:#6b677f; font-weight:400; margin-left:4px; }' +
      // Toggle ADN en vente
      '.pl-modal-adn-row { margin-bottom:18px; }' +
      '.pl-adn-toggle-label { display:flex; align-items:center; gap:10px; cursor:pointer; font-size:14px; color:#e8e6f5; }' +
      '.pl-adn-toggle-label input[type=checkbox] { width:16px; height:16px; accent-color:#cc88ff; cursor:pointer; }' +
      '.pl-adn-toggle-txt { font-weight:600; }' +
      '.pl-adn-price-wrap { margin-top:12px; padding:14px; background:rgba(204,136,255,.06); border:1px solid rgba(204,136,255,.2); border-radius:10px; }' +
      '.pl-adn-hint { font-size:11px; color:#6b677f; margin:8px 0 0; }' +
      // Badge ADN sur les cards (cliquable)
      '.ap-pl-adn-badge { position:absolute; top:8px; right:8px; background:rgba(0,0,0,.72); backdrop-filter:blur(6px); border:1px solid rgba(204,136,255,.4); border-radius:999px; padding:3px 8px; font-size:10px; color:#cc88ff; font-weight:700; z-index:8; letter-spacing:.02em; cursor:pointer; transition:background .18s,border-color .18s; }' +
      '.ap-pl-adn-badge:hover { background:rgba(204,136,255,.18); border-color:rgba(204,136,255,.8); }' +
      '.ap-pl-adn-badge.is-owned { color:#6fffb0; border-color:rgba(111,255,176,.4); }' +
      // Modale achat ADN playlist
      '.adn-buy-overlay { position:fixed; inset:0; background:rgba(0,0,0,.78); backdrop-filter:blur(8px); z-index:10000; display:flex; align-items:center; justify-content:center; padding:16px; }' +
      '.adn-buy-modal { background:#14111f; border:1px solid rgba(204,136,255,.25); border-radius:18px; padding:28px 24px; max-width:420px; width:100%; position:relative; }' +
      '.adn-buy-close { position:absolute; top:14px; right:16px; background:transparent; border:none; color:#a09cb8; font-size:20px; cursor:pointer; line-height:1; }' +
      '.adn-buy-close:hover { color:#fff; }' +
      '.adn-buy-eyebrow { font-size:10px; letter-spacing:.12em; text-transform:uppercase; color:#cc88ff; font-weight:700; margin:0 0 8px; }' +
      '.adn-buy-title { font-size:20px; font-weight:700; color:#fff; margin:0 0 14px; line-height:1.25; }' +
      '.adn-buy-desc { font-size:13px; color:#a09cb8; line-height:1.6; margin:0 0 18px; border-left:2px solid rgba(204,136,255,.3); padding-left:12px; }' +
      '.adn-buy-perks { list-style:none; padding:0; margin:0 0 22px; display:flex; flex-direction:column; gap:6px; }' +
      '.adn-buy-perks li { font-size:12px; color:#c8c4e0; display:flex; gap:8px; align-items:flex-start; }' +
      '.adn-buy-price-row { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }' +
      '.adn-buy-price { font-size:22px; font-weight:800; color:#fff; }' +
      '.adn-buy-price span { font-size:13px; color:#a09cb8; font-weight:400; margin-left:4px; }' +
      '.adn-buy-btn { width:100%; padding:13px; background:linear-gradient(135deg,rgba(204,136,255,.9),rgba(136,80,255,.9)); border:none; border-radius:12px; color:#fff; font-size:15px; font-weight:700; cursor:pointer; transition:opacity .18s; }' +
      '.adn-buy-btn:hover { opacity:.88; }' +
      '.adn-buy-btn:disabled { opacity:.45; cursor:not-allowed; }' +
      '.adn-buy-owned { text-align:center; padding:12px 0 4px; color:#6fffb0; font-weight:700; font-size:14px; }' +
      '.adn-buy-error { margin-top:12px; font-size:12px; color:#ff6b6b; text-align:center; }' +
      // Dashboard section
      '.pl-dash-section { background: rgba(255,255,255,.02); border: 1px solid rgba(204,136,255,.14); border-radius: 14px; padding: 20px; margin: 20px 0; }' +
      '.pl-dash-hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }' +
      '.pl-dash-title { font-size: 16px; margin: 0; color: #fff; }' +
      '.pl-dash-sub { font-size: 12px; color: #a09cb8; margin: 4px 0 0; }' +
      '.pl-create-btn { background: rgba(204,136,255,.14); color: #cc88ff; border: 1px solid rgba(204,136,255,.4); padding: 8px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; }' +
      '.pl-create-btn:hover { background: rgba(204,136,255,.24); }' +
      '.pl-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }' +
      '.pl-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 14px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.05); border-radius: 10px; }' +
      '.pl-row-name { color: #fff; font-size: 14px; font-weight: 500; }' +
      '.pl-row-meta { display: flex; gap: 8px; align-items: center; font-size: 11px; color: #a09cb8; }' +
      '.pl-badge { padding: 3px 8px; border-radius: 999px; letter-spacing: .04em; text-transform: uppercase; font-weight: 600; font-size: 10px; }' +
      '.pl-badge-public { background: rgba(0,200,255,.14); color: #8bd9ff; border: 1px solid rgba(0,200,255,.3); }' +
      '.pl-badge-private { background: rgba(204,136,255,.14); color: #cc88ff; border: 1px solid rgba(204,136,255,.3); }' +
      '.pl-row-actions { display: flex; gap: 6px; }' +
      '.pl-icon-btn { background: transparent; border: 1px solid rgba(255,255,255,.1); color: #a09cb8; border-radius: 8px; padding: 6px 10px; font-size: 12px; cursor: pointer; }' +
      '.pl-icon-btn:hover { color: #fff; border-color: rgba(255,255,255,.3); }' +
      '.pl-empty { color: #6b677f; font-size: 13px; text-align: center; padding: 24px 12px; }' +
      // Dashboard cover thumb
      '.pl-row-cover { width: 32px; height: 48px; border-radius: 6px; object-fit: cover; flex: 0 0 32px; }' +
      '.pl-row-cover-fallback { width: 32px; height: 48px; border-radius: 6px; background: linear-gradient(135deg, rgba(204,136,255,.3), rgba(0,200,255,.15)); flex: 0 0 32px; display: flex; align-items: center; justify-content: center; font-size: 14px; }' +
      '.pl-cover-input { display: none; }' +
      '.pl-icon-btn-cover { background: rgba(204,136,255,.1); border: 1px solid rgba(204,136,255,.35); color: #cc88ff; border-radius: 8px; padding: 6px 10px; font-size: 11px; cursor: pointer; }' +
      '.pl-icon-btn-cover:hover { background: rgba(204,136,255,.2); }' +
      '.pl-act-adn { background: rgba(204,136,255,.12); border-color: rgba(204,136,255,.4); color: #cc88ff; }' +
      '.pl-act-adn:hover { background: rgba(204,136,255,.25); }' +
      '.pl-act-adn.adn-active { background: rgba(111,255,176,.12); border-color: rgba(111,255,176,.4); color: #6fffb0; }' +
      // Modal édition ADN playlist
      '.pl-edit-overlay { position:fixed; inset:0; background:rgba(0,0,0,.78); backdrop-filter:blur(8px); z-index:9999; display:flex; align-items:center; justify-content:center; padding:16px; }' +
      '.pl-edit-modal { background:#14111f; border:1px solid rgba(204,136,255,.25); border-radius:18px; padding:28px 24px; max-width:400px; width:100%; position:relative; }' +
      '.pl-edit-close { position:absolute; top:14px; right:16px; background:transparent; border:none; color:#a09cb8; font-size:20px; cursor:pointer; line-height:1; }' +
      '.pl-edit-close:hover { color:#fff; }' +
      '.pl-edit-title { font-size:16px; color:#fff; margin:0 0 20px; font-weight:700; }' +
      '.pl-edit-label { display:block; font-size:12px; color:#a09cb8; margin-bottom:6px; }' +
      '.pl-edit-input { width:100%; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); border-radius:10px; color:#fff; padding:10px 12px; font-size:14px; box-sizing:border-box; margin-bottom:14px; }' +
      '.pl-edit-input:focus { outline:none; border-color:rgba(204,136,255,.5); }' +
      '.pl-edit-check-row { display:flex; align-items:center; gap:10px; margin-bottom:14px; }' +
      '.pl-edit-check-row input[type=checkbox] { width:16px; height:16px; accent-color:#cc88ff; cursor:pointer; }' +
      '.pl-edit-check-label { font-size:13px; color:#e0dcf0; cursor:pointer; }' +
      '.pl-edit-price-wrap { margin-bottom:14px; }' +
      '.pl-edit-save { width:100%; background:linear-gradient(90deg,#cc88ff,#8bd9ff); color:#0d0a1a; border:none; border-radius:10px; padding:12px; font-size:14px; font-weight:700; cursor:pointer; }' +
      '.pl-edit-save:disabled { opacity:.5; cursor:not-allowed; }' +
      '.pl-edit-err { margin-top:10px; font-size:12px; color:#ff6b6b; text-align:center; }' +
      // Artiste public section — accordion + cards carrées 1:1
      '.ap-playlists-section { padding: 0 12px; margin: 20px 0 28px; }' +
      '.ap-playlists-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; background: transparent; border: none; padding: 10px 0; cursor: pointer; gap: 12px; }' +
      '.ap-playlists-toggle-left { display: flex; align-items: baseline; gap: 10px; }' +
      '.ap-playlists-title { font-size: 18px; color: #fff; margin: 0; letter-spacing: -.01em; }' +
      '.ap-playlists-count { font-size: 12px; color: #a09cb8; }' +
      '.ap-playlists-arrow { color: #a09cb8; font-size: 14px; transition: transform .25s ease; flex-shrink: 0; }' +
      '.ap-playlists-body { overflow: hidden; max-height: 0; transition: max-height .35s ease; }' +
      '.ap-playlists-body.is-open { max-height: 1200px; }' +
      '.ap-playlists-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }' +
      '@media (max-width: 480px) { .ap-playlists-list { grid-template-columns: repeat(2, 1fr); } }' +
      '.ap-playlist-card { position: relative; aspect-ratio: 1/1; border-radius: 12px; overflow: hidden; cursor: pointer; background: linear-gradient(135deg, rgba(204,136,255,.15), rgba(10,10,20,1)); border: 1px solid rgba(204,136,255,.18); }' +
      '.ap-playlist-card video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: .85; }' +
      '.ap-playlist-card-fallback { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 2rem; opacity: .4; }' +
      '.ap-playlist-card-info { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: flex-end; padding: 10px 10px 8px; background: linear-gradient(to top, rgba(0,0,0,.72) 0%, transparent 60%); }' +
      '.ap-playlist-card-title { color: #fff; font-size: 13px; font-weight: 700; margin: 0; line-height: 1.3; text-shadow: 0 1px 4px rgba(0,0,0,.6); }' +
      '.ap-playlist-card-meta { font-size: 10px; color: rgba(255,255,255,.55); margin-top: 2px; }' +
      // Neon title (couleur dynamique via --nc CSS var)
      '@keyframes ap-neon-pulse {' +
        '0%,19%,21%,54%,56%,100%{text-shadow:0 0 8px var(--nc,#cc88ff),0 0 22px var(--nc,#cc88ff),0 0 45px var(--nc,#cc88ff);opacity:1}' +
        '20%,55%{text-shadow:none;opacity:.72}' +
        '22%{text-shadow:0 0 6px var(--nc,#cc88ff);opacity:.88}' +
      '}' +
      '.ap-pl-neon { font-size:13px; font-weight:900; letter-spacing:.07em; text-transform:uppercase; line-height:1; margin:0; color:var(--nc,#cc88ff); animation:ap-neon-pulse 4.5s infinite; }' +
      '.ap-playlist-card-meta { font-size:10px; color:rgba(255,255,255,.5); margin-top:3px; }' +
      // Bouton quick-play centré (même pattern card-quick-play WATT)
      '.ap-pl-qp { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%) scale(.7); width:44px; height:44px; border-radius:50%; background:rgba(5,5,8,.72); backdrop-filter:blur(8px); border:1.5px solid rgba(255,255,255,.18); color:#fff; cursor:pointer; display:flex; align-items:center; justify-content:center; opacity:0; transition:opacity .22s,transform .22s,border-color .22s,background .22s; z-index:10; }' +
      '.ap-pl-qp svg { width:15px; height:15px; fill:currentColor; margin-left:2px; }' +
      '.ap-playlist-card:hover .ap-pl-qp { opacity:1; transform:translate(-50%,-50%) scale(1); }' +
      '.ap-playlist-card:hover .ap-pl-qp:hover { transform:translate(-50%,-50%) scale(1.1); background:rgba(var(--nc-rgb,204,136,255),.45); border-color:rgba(var(--nc-rgb,204,136,255),.55); }'
    );
    const style = document.createElement('style');
    style.id = 'pl-modal-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ── 3. RENDERER DASHBOARD ─────────────────────────────────────────────────

  async function renderDashboardPlaylists(containerId) {
    const root = document.getElementById(containerId);
    if (!root) return;
    _injectModalStyles();

    root.innerHTML = (
      '<div class="pl-dash-section">' +
        '<div class="pl-dash-hdr">' +
          '<div>' +
            '<h3 class="pl-dash-title">Mes playlists</h3>' +
            '<p class="pl-dash-sub">Crée des collections de sons. Privées par défaut.</p>' +
          '</div>' +
          '<button type="button" class="pl-create-btn" id="pl-dash-create">+ Créer</button>' +
        '</div>' +
        '<ul class="pl-list" id="pl-dash-list"><li class="pl-empty">Chargement…</li></ul>' +
      '</div>'
    );

    const reload = async () => {
      try {
        const playlists = await loadMyPlaylists();
        const ul = root.querySelector('#pl-dash-list');
        if (!playlists || playlists.length === 0) {
          ul.innerHTML = '<li class="pl-empty">Aucune playlist pour le moment.</li>';
          return;
        }
        ul.innerHTML = playlists.map(p => {
          const badge = p.visibility === 'public'
            ? '<span class="pl-badge pl-badge-public">Publique</span>'
            : '<span class="pl-badge pl-badge-private">Privée</span>';
          const adnBadge = p.adn_for_sale
            ? '<span class="pl-badge" style="background:rgba(111,255,176,.12);color:#6fffb0;border:1px solid rgba(111,255,176,.35)">🧬 ' + (p.adn_price || '?') + ' Smyles</span>'
            : '';
          const thumb = p.cover_video_url
            ? '<video class="pl-row-cover" autoplay muted loop playsinline preload="metadata"><source src="' + p.cover_video_url.replace(/"/g, '&quot;') + '" /></video>'
            : '<div class="pl-row-cover-fallback">🎵</div>';
          return (
            '<li class="pl-row" data-id="' + p.id + '" data-vis="' + p.visibility + '" ' +
                'data-adn-for-sale="' + (p.adn_for_sale ? '1' : '0') + '" ' +
                'data-adn-price="' + (p.adn_price || '') + '" ' +
                'data-title="' + (p.title || '').replace(/"/g, '&quot;') + '">' +
              thumb +
              '<div style="flex:1;min-width:0">' +
                '<div class="pl-row-name">' + _esc(p.title) + '</div>' +
                '<div class="pl-row-meta">' + badge + adnBadge + '</div>' +
              '</div>' +
              '<div class="pl-row-actions">' +
                '<label class="pl-icon-btn-cover" title="Ajouter une cover vidéo (mp4 ≤5s)">📎' +
                  '<input type="file" class="pl-cover-input pl-act-cover" accept="video/mp4,video/webm,video/quicktime" />' +
                '</label>' +
                '<button type="button" class="pl-icon-btn pl-act-adn' + (p.adn_for_sale ? ' adn-active' : '') + '" title="Configurer ADN">🧬</button>' +
                '<button type="button" class="pl-icon-btn pl-act-vis" title="Changer visibilité">' +
                  (p.visibility === 'public' ? 'Privée' : 'Publique') +
                '</button>' +
                '<button type="button" class="pl-icon-btn pl-act-del" title="Supprimer">✕</button>' +
              '</div>' +
            '</li>'
          );
        }).join('');
      } catch (e) {
        const ul = root.querySelector('#pl-dash-list');
        if (e && e.status === 401) {
          ul.innerHTML = '<li class="pl-empty">Connecte-toi pour voir tes playlists.</li>';
        } else {
          ul.innerHTML = '<li class="pl-empty">Chargement impossible (' + (e && e.message || 'erreur') + ').</li>';
        }
      }
    };

    root.querySelector('#pl-dash-create').onclick = () => openCreatePlaylistModal(() => reload());

    // Délégation pour boutons toggle / delete / edit ADN
    root.querySelector('#pl-dash-list').addEventListener('click', async (ev) => {
      const row = ev.target.closest('.pl-row');
      if (!row) return;
      const id = row.dataset.id;
      const vis = row.dataset.vis;
      if (ev.target.closest('.pl-act-adn')) {
        // Ouvrir modal édition ADN
        const plData = {
          id,
          title: row.dataset.title || '',
          visibility: vis,
          adn_for_sale: row.dataset.adnForSale === '1',
          adn_price: parseInt(row.dataset.adnPrice, 10) || null
        };
        openEditPlaylistAdnModal(plData, () => reload());
      } else if (ev.target.closest('.pl-act-vis')) {
        try {
          await togglePlaylistVisibility(id, vis);
          await reload();
        } catch (e) {
          alert('Changement impossible : ' + (e && e.message || 'erreur'));
        }
      } else if (ev.target.closest('.pl-act-del')) {
        if (!confirm('Supprimer cette playlist ? Action irréversible.')) return;
        try {
          await deletePlaylist(id);
          await reload();
        } catch (e) {
          alert('Suppression impossible : ' + (e && e.message || 'erreur'));
        }
      }
    });

    // Délégation upload cover (input file change)
    root.querySelector('#pl-dash-list').addEventListener('change', async (ev) => {
      const input = ev.target.closest('.pl-act-cover');
      if (!input || !input.files || !input.files[0]) return;
      const row = ev.target.closest('.pl-row');
      if (!row) return;
      const id   = row.dataset.id;
      const file = input.files[0];
      // Validation durée ≤ 3s côté frontend
      try {
        await new Promise((resolve, reject) => {
          const vid = document.createElement('video');
          vid.preload = 'metadata';
          vid.onloadedmetadata = () => {
            URL.revokeObjectURL(vid.src);
            if (vid.duration > 5.5) reject(new Error('La vidéo dépasse 5 secondes (' + vid.duration.toFixed(1) + 's). Raccourcis-la avant.'));
            else resolve();
          };
          vid.onerror = () => reject(new Error('Impossible de lire la vidéo.'));
          vid.src = URL.createObjectURL(file);
        });
      } catch (e) {
        alert(e.message);
        input.value = '';
        return;
      }
      // Upload R2
      const plName = row.querySelector('.pl-row-name');
      const label  = ev.target.closest('label');
      const origTxt = label ? label.textContent.trim() : '';
      if (label) label.textContent = '⏳';
      try {
        const token = (typeof getAuthToken === 'function') ? getAuthToken() : null;
        const me    = (typeof getWattProfile === 'function') ? getWattProfile() : null;
        const userId = (me && me.id) || 'guest';
        const fd = new FormData();
        fd.append('file', file);
        fd.append('userId', userId);
        fd.append('name', (plName ? plName.textContent : 'cover').slice(0, 40));
        const headers = {};
        if (token) headers['Authorization'] = 'Bearer ' + token;
        const resp = await fetch('/api/watt/upload-playlist-cover', { method: 'POST', body: fd, headers, credentials: 'same-origin' });
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || 'Upload échoué');
        // PATCH playlist avec la nouvelle cover_url
        await _req('/playlists/' + encodeURIComponent(id), { method: 'PATCH', body: { cover_video_url: data.cover_url } });
        await reload();
      } catch (e) {
        if (label) label.textContent = '📎';
        alert('Échec upload cover : ' + (e && e.message || 'erreur'));
      }
    });

    await reload();
  }

  // ── 4. RENDERER PROFIL PUBLIC ─────────────────────────────────────────────

  async function renderArtistPlaylists(slug, containerId) {
    const root = document.getElementById(containerId);
    if (!root) return;
    _injectModalStyles();
    try {
      const all = await loadArtistPublicPlaylists(slug);
      if (!all || all.length === 0) {
        root.style.display = 'none';
        return;
      }
      const playlists = all.slice(0, 6);
      root.style.display = '';

      const FALLBACK_EMOJIS = ['🎵','🎶','🔥','✨','🎸','🎹','🌙','⚡'];
      const sectionId  = 'ap-pl-body-' + containerId;
      const arrowId    = 'ap-pl-arrow-' + containerId;
      const countLabel = playlists.length + ' playlist' + (playlists.length > 1 ? 's' : '');

      root.innerHTML = (
        '<section class="ap-playlists-section" aria-label="Playlists publiques">' +
          '<button class="ap-playlists-toggle" aria-expanded="false" aria-controls="' + sectionId + '">' +
            '<span class="ap-playlists-toggle-left">' +
              '<h2 class="ap-playlists-title">Playlists</h2>' +
              '<span class="ap-playlists-count">' + countLabel + '</span>' +
            '</span>' +
            '<span class="ap-playlists-arrow" id="' + arrowId + '">▼</span>' +
          '</button>' +
          '<div class="ap-playlists-body" id="' + sectionId + '">' +
            '<ul class="ap-playlists-list">' +
              playlists.map(function(p, i) {
                const nc     = p.color || '#cc88ff';
                const ncRgb  = _hexToRgb(nc);
                const mediaBg = p.cover_video_url
                  ? '<video autoplay muted loop playsinline preload="metadata"><source src="' + p.cover_video_url.replace(/"/g, '&quot;') + '"/></video>'
                  : '<div class="ap-playlist-card-fallback" style="background:linear-gradient(135deg,' + nc + ',rgba(10,10,20,1))">' + FALLBACK_EMOJIS[i % FALLBACK_EMOJIS.length] + '</div>';
                const qpId = 'ap-qp-' + p.id;
                const adnBadge = p.adn_for_sale
                  ? '<div class="ap-pl-adn-badge" data-playlist-id="' + p.id + '" data-adn-price="' + (p.adn_price || 0) + '" data-adn-title="' + (p.title || '').replace(/"/g,'&quot;') + '" data-seed-prompt="' + (p.seed_prompt || '').replace(/"/g,'&quot;') + '">🧬 ADN · ' + (p.adn_price ? p.adn_price + ' Smyles' : 'free') + '</div>'
                  : '';
                return (
                  '<li class="ap-playlist-card" data-pl-id="' + p.id + '" style="--nc:' + nc + ';--nc-rgb:' + ncRgb + '">' +
                    mediaBg +
                    '<button class="ap-pl-qp" id="' + qpId + '" title="Lancer">' +
                      '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>' +
                    '</button>' +
                    adnBadge +
                    '<div class="ap-playlist-card-info">' +
                      '<div class="ap-pl-neon">' + _esc(p.title) + '</div>' +
                      '<div class="ap-playlist-card-meta">' + _fmtDate(p.created_at) + '</div>' +
                    '</div>' +
                  '</li>'
                );
              }).join('') +
            '</ul>' +
          '</div>' +
        '</section>'
      );

      // Brancher quick-play buttons
      playlists.forEach(function(p) {
        const btn = document.getElementById('ap-qp-' + p.id);
        if (btn) btn.addEventListener('click', function(e) { _quickPlayUserPlaylist(e, p.id); });
      });

      // Toggle accordion
      const toggleBtn = root.querySelector('.ap-playlists-toggle');
      const body      = document.getElementById(sectionId);
      const arrow     = document.getElementById(arrowId);
      if (toggleBtn && body && arrow) {
        toggleBtn.addEventListener('click', function () {
          const open = body.classList.toggle('is-open');
          toggleBtn.setAttribute('aria-expanded', String(open));
          arrow.style.transform = open ? 'rotate(180deg)' : '';
        });
      }
    } catch (e) {
      root.style.display = 'none';
      console.warn('[playlists] artist load failed:', e);
    }
  }

  // ── 5. QUICK-PLAY playlists utilisateur ───────────────────────────────────

  // Convertit #rrggbb en "r,g,b" pour les CSS variables --nc-rgb
  function _hexToRgb(hex) {
    const m = (hex || '').replace('#','').match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (!m) return '204,136,255';
    return parseInt(m[1],16) + ',' + parseInt(m[2],16) + ',' + parseInt(m[3],16);
  }

  // Charge les tracks d'une playlist publique dans PLAYLISTS puis lance la lecture
  async function _quickPlayUserPlaylist(e, playlistId) {
    e.stopPropagation();
    const key = 'user-pl-' + playlistId;
    // PLAYLISTS est un `let` global (state.js) — ne pas utiliser window.PLAYLISTS
    // car let ne se bind pas sur window. Les deux pointent vers des objets différents.
    if (typeof PLAYLISTS !== 'undefined' && PLAYLISTS[key]) {
      if (typeof loadTrack === 'function') { loadTrack(key, 0); return; }
    }
    try {
      const data = await _req('/watt/playlists/' + playlistId);
      if (!data.tracks || !data.tracks.length) {
        if (typeof showToast === 'function') showToast('Playlist vide');
        return;
      }
      PLAYLISTS[key] = {
        label:  data.title,
        theme:  data.color || 'custom',
        folder: '',
        tracks: data.tracks
          .map(function(t) {
            var url = t.audio_url || (t.r2_key ? '/watt/stream/' + t.r2_key : null);
            return { url: url, name: t.title, id: t.id };
          })
          .filter(function(t) { return t.url; })
      };
      if (!PLAYLISTS[key].tracks.length) {
        if (typeof showToast === 'function') showToast('Aucun audio disponible');
        return;
      }
      if (typeof loadTrack === 'function') loadTrack(key, 0);
    } catch (err) {
      console.warn('[playlists] quickPlay error:', err);
      if (typeof showToast === 'function') showToast('Impossible de lancer la playlist');
    }
  }

  // ── 5b. MODALE ACHAT ADN PLAYLIST ─────────────────────────────────────────

  async function _openAdnPurchaseModal(badgeEl) {
    const playlistId  = badgeEl.dataset.playlistId;
    const adnPrice    = parseInt(badgeEl.dataset.adnPrice, 10) || 0;
    const adnTitle    = badgeEl.dataset.adnTitle || 'cette playlist';
    const seedPrompt  = badgeEl.dataset.seedPrompt || '';

    // Supprimer overlay existant
    const existing = document.getElementById('adn-buy-overlay');
    if (existing) existing.remove();

    // Créer overlay
    const overlay = document.createElement('div');
    overlay.id        = 'adn-buy-overlay';
    overlay.className = 'adn-buy-overlay';

    overlay.innerHTML =
      '<div class="adn-buy-modal" role="dialog" aria-modal="true">' +
        '<button class="adn-buy-close" id="adn-buy-close" aria-label="Fermer">✕</button>' +
        '<p class="adn-buy-eyebrow">ADN Playlist</p>' +
        '<h3 class="adn-buy-title">' + _esc(adnTitle) + '</h3>' +
        (seedPrompt
          ? '<p class="adn-buy-desc">' + _esc(seedPrompt) + '</p>'
          : '<p class="adn-buy-desc">La synthèse créative de tous les sons de cette playlist — ton blueprint pour reproduire cet univers.</p>') +
        '<ul class="adn-buy-perks">' +
          '<li>🧬 Accès à l\'ADN créatif complet de la playlist</li>' +
          '<li>💎 Réduction <strong>-20%</strong> sur tous les ADN Track de cette playlist</li>' +
          '<li>🎵 La playlist reste écoutable librement — tu achètes le blueprint</li>' +
        '</ul>' +
        '<div id="adn-buy-content">' +
          '<div style="text-align:center;color:#a09cb8;padding:24px 0;font-size:13px">Chargement…</div>' +
        '</div>' +
      '</div>';

    document.body.appendChild(overlay);

    // Fermeture
    const closeBtn = document.getElementById('adn-buy-close');
    if (closeBtn) closeBtn.addEventListener('click', function() { overlay.remove(); });
    overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });

    // Vérifier ownership si connecté
    const token = typeof getAuthToken === 'function' ? getAuthToken() : null;
    const contentEl = document.getElementById('adn-buy-content');

    if (!token) {
      contentEl.innerHTML =
        '<div class="adn-buy-price-row"><div class="adn-buy-price">' + adnPrice + '<span>Smyles</span></div></div>' +
        '<button class="adn-buy-btn" id="adn-buy-confirm-btn" disabled>Connecte-toi pour acheter</button>';
      return;
    }

    try {
      const owned = await _req('/playlists/' + playlistId + '/adn-owned');
      if (owned && owned.owned) {
        contentEl.innerHTML = '<div class="adn-buy-owned">✅ Tu possèdes déjà cet ADN — profite de -20% sur les tracks !</div>';
        badgeEl.textContent  = '✅ ADN';
        badgeEl.classList.add('is-owned');
        return;
      }
    } catch (_) { /* pas connecté ou autre — on continue */ }

    // Non possédé : afficher prix + bouton
    contentEl.innerHTML =
      '<div class="adn-buy-price-row">' +
        '<div class="adn-buy-price">' + adnPrice + '<span>Smyles</span></div>' +
      '</div>' +
      '<button class="adn-buy-btn" id="adn-buy-confirm-btn">🧬 Acheter l\'ADN</button>' +
      '<div class="adn-buy-error" id="adn-buy-err" style="display:none"></div>';

    const confirmBtn = document.getElementById('adn-buy-confirm-btn');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', async function() {
        confirmBtn.disabled     = true;
        confirmBtn.textContent  = 'Traitement…';
        const errEl = document.getElementById('adn-buy-err');

        try {
          await _req('/unlocks/playlist-adn/' + playlistId, { method: 'POST' });
          contentEl.innerHTML = '<div class="adn-buy-owned">✅ ADN acheté ! Tu bénéficies maintenant de -20% sur les ADN Track de cette playlist.</div>';
          badgeEl.textContent = '✅ ADN';
          badgeEl.classList.add('is-owned');
          if (typeof showToast === 'function') showToast('ADN playlist débloqué 🧬');
        } catch (err) {
          confirmBtn.disabled = false;
          confirmBtn.textContent = '🧬 Acheter l\'ADN';
          const msg = (err && err.message) ? err.message : 'Erreur lors de l\'achat';
          if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
        }
      });
    }
  }

  // ── 6. UTILS ──────────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s || '').replace(/[&<>"']/g, c => (
      { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]
    ));
  }
  function _fmtDate(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch (_) { return ''; }
  }

  // ── 5b. MODALE ÉDITION ADN PLAYLIST ──────────────────────────────────────

  function openEditPlaylistAdnModal(playlistData, onSaved) {
    // playlistData : { id, title, visibility, adn_for_sale, adn_price }
    if (document.getElementById('pl-edit-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'pl-edit-overlay';
    overlay.className = 'pl-edit-overlay';

    overlay.innerHTML =
      '<div class="pl-edit-modal" role="dialog">' +
        '<button class="pl-edit-close" id="pl-edit-close" aria-label="Fermer">✕</button>' +
        '<h3 class="pl-edit-title">Configurer « ' + _esc(playlistData.title || 'Playlist') + ' »</h3>' +
        '<label class="pl-edit-label" for="pl-edit-vis">Visibilité</label>' +
        '<select id="pl-edit-vis" class="pl-edit-input">' +
          '<option value="private"' + (playlistData.visibility !== 'public' ? ' selected' : '') + '>🔒 Privée</option>' +
          '<option value="public"' + (playlistData.visibility === 'public' ? ' selected' : '') + '>🌐 Publique</option>' +
        '</select>' +
        '<div class="pl-edit-check-row">' +
          '<input type="checkbox" id="pl-edit-adn" ' + (playlistData.adn_for_sale ? 'checked' : '') + ' />' +
          '<label class="pl-edit-check-label" for="pl-edit-adn">🧬 Vendre l\'ADN de cette playlist</label>' +
        '</div>' +
        '<div class="pl-edit-price-wrap" id="pl-edit-price-wrap" style="display:' + (playlistData.adn_for_sale ? '' : 'none') + '">' +
          '<label class="pl-edit-label" for="pl-edit-price">Prix en Smyles (1 – 100 000)</label>' +
          '<input type="number" id="pl-edit-price" class="pl-edit-input" min="1" max="100000" placeholder="ex : 50" value="' + (playlistData.adn_price || '') + '" />' +
        '</div>' +
        '<button class="pl-edit-save" id="pl-edit-save">Enregistrer</button>' +
        '<div class="pl-edit-err" id="pl-edit-err" style="display:none"></div>' +
      '</div>';

    document.body.appendChild(overlay);

    const closeBtn = document.getElementById('pl-edit-close');
    if (closeBtn) closeBtn.addEventListener('click', function() { overlay.remove(); });
    overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });

    const adnChk = document.getElementById('pl-edit-adn');
    const priceWrap = document.getElementById('pl-edit-price-wrap');
    if (adnChk && priceWrap) {
      adnChk.addEventListener('change', function() {
        priceWrap.style.display = adnChk.checked ? '' : 'none';
      });
    }

    const saveBtn = document.getElementById('pl-edit-save');
    const errEl   = document.getElementById('pl-edit-err');
    if (saveBtn) {
      saveBtn.addEventListener('click', async function() {
        const vis      = document.getElementById('pl-edit-vis').value;
        const adnSale  = adnChk && adnChk.checked;
        const adnPrice = adnSale ? (parseInt(document.getElementById('pl-edit-price').value, 10) || null) : null;

        if (adnSale && !adnPrice) {
          if (errEl) { errEl.textContent = 'Fixe un prix en Smyles pour activer la vente d\'ADN.'; errEl.style.display = 'block'; }
          return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = 'Sauvegarde…';
        if (errEl) errEl.style.display = 'none';

        const patch = { visibility: vis, adn_for_sale: adnSale };
        if (adnSale && adnPrice) patch.adn_price = adnPrice;
        if (!adnSale) patch.adn_price = null;

        try {
          await updatePlaylist(playlistData.id, patch);
          overlay.remove();
          if (typeof onSaved === 'function') onSaved();
          if (typeof showToast === 'function') showToast('Playlist mise à jour ✓');
        } catch (e) {
          saveBtn.disabled = false;
          saveBtn.textContent = 'Enregistrer';
          const msg = (e && e.message) || 'Erreur lors de la mise à jour';
          if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
        }
      });
    }
  }

  // ── 6. EXPORTS ────────────────────────────────────────────────────────────

  window.SmylePlaylists = {
    loadMyPlaylists,
    createPlaylist,
    updatePlaylist,
    deletePlaylist,
    togglePlaylistVisibility,
    loadArtistPublicPlaylists,
    openCreatePlaylistModal,
    openEditPlaylistAdnModal,
    openAdnPurchaseModal: _openAdnPurchaseModal,
    renderDashboardPlaylists,
    renderArtistPlaylists,
    injectModalStyles: _injectModalStyles
  };
})();

// ── 7. AUTO-BOOT ────────────────────────────────────────────────────────────
// Au DOMContentLoaded, on cherche les containers connus et on render.
// Dashboard : container #dash-playlists-root → render mes playlists.
// Profil public : container #ap-playlists-root + URL /u/<slug> → render
// playlists publiques de l'artiste.
// Idempotent : si les containers n'existent pas, no-op silencieux.

(function autoBoot() {
  function boot() {
    const dashRoot = document.getElementById('dash-playlists-root');
    if (dashRoot && window.SmylePlaylists) {
      window.SmylePlaylists.renderDashboardPlaylists('dash-playlists-root')
        .catch(e => console.warn('[playlists] dashboard render failed:', e));
    }

    const apRoot = document.getElementById('ap-playlists-root');
    if (apRoot && window.SmylePlaylists) {
      // Slug parsé depuis /u/<slug>
      const match = (window.location.pathname || '').match(/^\/u\/([^/?#]+)/);
      const slug = match ? decodeURIComponent(match[1]) : null;
      if (slug) {
        window.SmylePlaylists.renderArtistPlaylists(slug, 'ap-playlists-root')
          .catch(e => console.warn('[playlists] artist render failed:', e));
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

// ── 8. ADD TO PLAYLIST MODAL ───────────────────────────────────────────────
// Modale "Choisir une playlist" pour ajouter un track. Au click :
//   1. Si user pas connecté → toast "Connecte-toi pour utiliser les playlists".
//      (la modale login existante peut être déclenchée si exposée globalement)
//   2. Sinon → charge mes playlists, affiche liste cliquable + bouton "Créer".
//   3. Click sur une playlist → POST /playlists/{id}/tracks {track_id}.
//   4. Toast de confirmation, fermeture modale.

(function(){
  'use strict';

  async function _addTrackToPlaylist(playlistId, trackId) {
    const resp = await fetch('/playlists/' + encodeURIComponent(playlistId) + '/tracks', {
      method: 'POST',
      credentials: 'same-origin',
      headers: Object.assign(
        { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        (typeof getAuthToken === 'function' && getAuthToken())
          ? { 'Authorization': 'Bearer ' + getAuthToken() } : {}
      ),
      body: JSON.stringify({ track_id: trackId })
    });
    if (!resp.ok) {
      const status = resp.status;
      let detail = '';
      try { detail = (await resp.json()).detail || ''; } catch (_) {}
      const err = new Error('HTTP ' + status + (detail ? ' — ' + detail : ''));
      err.status = status;
      throw err;
    }
    return resp.status === 204 ? null : await resp.json();
  }

  function _showToast(msg) {
    if (typeof showToast === 'function') return showToast(msg);
    if (window.showToast)               return window.showToast(msg);
    // Fallback minimal
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1a1a24;color:#fff;padding:12px 18px;border-radius:10px;border:1px solid rgba(204,136,255,.3);z-index:99999;font-size:14px';
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  function _isAuth() {
    if (typeof getAuthToken === 'function') return !!getAuthToken();
    if (typeof getCurrentUser === 'function') {
      const u = getCurrentUser();
      return !!(u && u.id);
    }
    return false;
  }

  async function openAddToPlaylistModal(trackId) {
    if (!trackId) return;
    if (!_isAuth()) {
      _showToast('Connecte-toi pour ajouter à une playlist.');
      return;
    }
    if (document.getElementById('pl-add-modal')) return;
    // Injecter les styles complets (via SmylePlaylists pour éviter le conflit avec la modale de création)
    if (window.SmylePlaylists && window.SmylePlaylists.injectModalStyles) {
      window.SmylePlaylists.injectModalStyles();
    }

    const overlay = document.createElement('div');
    overlay.id = 'pl-add-modal';
    overlay.className = 'pl-modal-overlay';
    overlay.innerHTML = (
      '<div class="pl-modal" role="dialog">' +
        '<button type="button" class="pl-modal-close" aria-label="Fermer">✕</button>' +
        '<h3 class="pl-modal-title">Ajouter à une playlist</h3>' +
        '<div id="pl-add-list" class="pl-add-list">Chargement…</div>' +
        '<div class="pl-modal-actions">' +
          '<button type="button" class="pl-btn pl-btn-ghost" id="pl-add-cancel">Annuler</button>' +
          '<button type="button" class="pl-btn pl-btn-primary" id="pl-add-new">+ Nouvelle playlist</button>' +
        '</div>' +
      '</div>'
    );
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('.pl-modal-close').onclick = close;
    overlay.querySelector('#pl-add-cancel').onclick = close;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#pl-add-new').onclick = () => {
      close();
      window.SmylePlaylists.openCreatePlaylistModal(async (created) => {
        if (created && created.id) {
          try {
            await _addTrackToPlaylist(created.id, trackId);
            _showToast('Ajouté à « ' + created.title + ' » ✓');
          } catch (e) {
            _showToast('Ajout impossible : ' + (e && e.message || 'erreur'));
          }
        }
      });
    };

    try {
      const playlists = await window.SmylePlaylists.loadMyPlaylists();
      const listEl = overlay.querySelector('#pl-add-list');
      if (!playlists || playlists.length === 0) {
        listEl.innerHTML = '<p class="pl-empty">Aucune playlist. Clique « + Nouvelle playlist » ci-dessous.</p>';
        return;
      }
      listEl.innerHTML = '<ul class="pl-picker-list">' + playlists.map(p => {
        const badge = p.visibility === 'public' ? 'Publique' : 'Privée';
        const safeTitle = String(p.title || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
        return '<li><button type="button" class="pl-picker-row" data-pl-id="' + p.id + '" data-pl-title="' + safeTitle.replace(/"/g, '&quot;') + '">' +
          '<span>' + safeTitle + '</span>' +
          '<span class="pl-picker-vis">' + badge + '</span>' +
        '</button></li>';
      }).join('') + '</ul>';

      listEl.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('.pl-picker-row');
        if (!btn) return;
        const id = btn.dataset.plId;
        const title = btn.dataset.plTitle || '';
        btn.disabled = true;
        btn.style.opacity = '.6';
        try {
          await _addTrackToPlaylist(id, trackId);
          _showToast('Ajouté à « ' + title + ' » ✓');
          close();
        } catch (e) {
          btn.disabled = false;
          btn.style.opacity = '';
          if (e && e.status === 409) {
            _showToast('Déjà dans cette playlist.');
            close();
          } else if (e && e.status === 403) {
            _showToast('Tu ne peux pas modifier cette playlist.');
          } else {
            _showToast('Ajout impossible (' + (e && e.message || 'erreur') + ').');
          }
        }
      });
    } catch (e) {
      const listEl = overlay.querySelector('#pl-add-list');
      if (e && e.status === 401) {
        listEl.innerHTML = '<p class="pl-empty">Session expirée. Reconnecte-toi.</p>';
      } else {
        listEl.innerHTML = '<p class="pl-empty">Chargement impossible.</p>';
      }
    }
  }

  // ── 9. VIEW PLAYLIST MODAL ──────────────────────────────────────────────
  // Modale "Lecture de la playlist" — fetch /playlists/{id}, render tracks
  // avec <audio> inline (reuse du listener global play counter de storage.js).

  async function openPlaylistViewModal(playlistId) {
    if (!playlistId) return;
    if (document.getElementById('pl-view-modal')) return;
    // Injecter les styles complets via SmylePlaylists
    if (window.SmylePlaylists && window.SmylePlaylists.injectModalStyles) {
      window.SmylePlaylists.injectModalStyles();
    }

    const overlay = document.createElement('div');
    overlay.id = 'pl-view-modal';
    overlay.className = 'pl-modal-overlay';
    overlay.innerHTML = (
      '<div class="pl-modal pl-modal-wide" role="dialog">' +
        '<button type="button" class="pl-modal-close" aria-label="Fermer">✕</button>' +
        '<div id="pl-view-content">Chargement…</div>' +
      '</div>'
    );
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.querySelector('.pl-modal-close').onclick = close;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    try {
      const headers = Object.assign(
        { 'Accept': 'application/json' },
        (typeof getAuthToken === 'function' && getAuthToken())
          ? { 'Authorization': 'Bearer ' + getAuthToken() } : {}
      );
      const resp = await fetch('/playlists/' + encodeURIComponent(playlistId), {
        credentials: 'same-origin', headers
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const playlist = await resp.json();
      const content = overlay.querySelector('#pl-view-content');
      const tracks = playlist.tracks || [];
      const badge = playlist.visibility === 'public' ? 'Publique' : 'Privée';
      const safeTitle = String(playlist.title || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
      content.innerHTML = (
        '<div class="pl-view-hdr">' +
          '<h3 class="pl-modal-title" style="margin:0">' + safeTitle + '</h3>' +
          '<span class="pl-badge pl-badge-' + (playlist.visibility === 'public' ? 'public' : 'private') + '">' + badge + '</span>' +
        '</div>' +
        '<p class="pl-view-sub">' + tracks.length + ' titre' + (tracks.length > 1 ? 's' : '') + '</p>' +
        (tracks.length > 0 ? '<button class="pl-btn pl-btn-primary pl-load-mix-btn" type="button" data-pl-id="' + playlist.id + '" style="margin-bottom:14px">▶ Charger dans MY MIX</button>' : '') +
        (tracks.length === 0
          ? '<p class="pl-empty">Aucune track. Ajoute des sons depuis la marketplace via le bouton +.</p>'
          : '<ul class="pl-view-list">' + tracks.map(t => {
              const safe = String(t.title || t.name || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
              const url = t.audio_url || t.stream_url || t.streamUrl || (t.r2_key ? '/watt/stream/' + t.r2_key : '') || '';
              const cover = t.cover_url || t.coverUrl || '';
              const safeUrl = url.replace(/"/g, '&quot;');
              return '<li class="pl-view-row" data-track-id="' + t.id + '">' +
                '<div class="pl-view-row-top">' +
                  (cover ? '<img class="pl-view-row-cover" src="' + cover.replace(/"/g, '&quot;') + '" alt="" />' : '') +
                  '<div class="pl-view-row-title">' + safe + '</div>' +
                  '<button type="button" class="pl-view-row-remove" data-track-remove="' + t.id + '" title="Retirer de la playlist" aria-label="Retirer">✕</button>' +
                '</div>' +
                (safeUrl ? '<audio controls preload="none" class="pl-view-audio" src="' + safeUrl + '"></audio>' : '<span class="pl-empty">Audio indisponible</span>') +
              '</li>';
            }).join('') + '</ul>'
        )
      );
      content.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('.pl-view-row-remove');
        if (!btn) return;
        ev.preventDefault();
        ev.stopPropagation();
        const tid = btn.getAttribute('data-track-remove');
        if (!tid) return;
        if (!confirm('Retirer ce son de la playlist ?')) return;
        btn.disabled = true;
        btn.style.opacity = '.5';
        try {
          const r = await fetch('/playlists/' + encodeURIComponent(playlist.id) + '/tracks/' + encodeURIComponent(tid), {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: (typeof getAuthToken === 'function' && getAuthToken()) ? { 'Authorization': 'Bearer ' + getAuthToken() } : {}
          });
          if (r.ok || r.status === 204) {
            const row = btn.closest('.pl-view-row');
            if (row) row.remove();
            _showToast('Retiré de la playlist.');
            if (typeof window.SmylePlaylists !== 'undefined' && typeof window.SmylePlaylists.loadLikedTrackIds === 'function') {
              try { await window.SmylePlaylists.loadLikedTrackIds(); } catch (_) {}
            }
          } else {
            btn.disabled = false;
            btn.style.opacity = '';
            _showToast('Suppression impossible (HTTP ' + r.status + ').');
          }
        } catch (e) {
          btn.disabled = false;
          btn.style.opacity = '';
          _showToast('Erreur réseau : ' + (e && e.message || 'inconnue'));
        }
      });

      const loadBtn = overlay.querySelector('.pl-load-mix-btn');
      if (loadBtn) {
        loadBtn.onclick = async () => {
          loadBtn.disabled = true;
          loadBtn.textContent = 'Chargement…';
          try {
            if (typeof loadSavedPlaylist === 'function') {
              await loadSavedPlaylist(playlist.id);
              close();
              if (typeof toggleMixPanel === 'function') {
                const panel = document.getElementById('mixPanel');
                if (panel && !panel.classList.contains('open')) toggleMixPanel();
              }
            } else {
              _showToast('MY MIX indisponible.');
            }
          } catch (e) {
            _showToast('Chargement impossible : ' + (e && e.message || 'erreur'));
            loadBtn.disabled = false;
            loadBtn.textContent = '▶ Charger dans MY MIX';
          }
        };
      }
    } catch (e) {
      overlay.querySelector('#pl-view-content').innerHTML = '<p class="pl-empty">Chargement impossible.</p>';
    }
  }

  // ── 10. ADDITIONAL STYLES ─────────────────────────────────────────────
  function _injectExtraStyles() {
    if (document.getElementById('pl-extra-styles')) return;
    const css = (
      '.pl-modal-wide { max-width: 640px; max-height: 80vh; overflow-y: auto; }' +
      '.pl-add-list { margin: 12px 0 18px; min-height: 80px; }' +
      '.pl-picker-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }' +
      '.pl-picker-row { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: 10px; color: #fff; cursor: pointer; text-align: left; font-size: 14px; }' +
      '.pl-picker-row:hover { background: rgba(204,136,255,.1); border-color: rgba(204,136,255,.3); }' +
      '.pl-picker-vis { font-size: 11px; color: #a09cb8; letter-spacing: .04em; text-transform: uppercase; }' +
      '.pl-view-hdr { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }' +
      '.pl-view-sub { color: #a09cb8; font-size: 12px; margin: 0 0 16px; }' +
      '.pl-view-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }' +
      '.pl-view-row { display: flex; flex-direction: column; gap: 6px; padding: 12px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.06); border-radius: 10px; }' +
      '.pl-view-row-title { color: #fff; font-size: 14px; font-weight: 500; }' +
      '.pl-view-audio { width: 100%; max-width: 100%; }' +
      '.ap-playlist-card { cursor: pointer; transition: border-color .15s ease; }' +
      '.ap-playlist-card:hover { border-color: rgba(204,136,255,.4); }' +
      '.pl-row { cursor: pointer; }' +
      '.add-to-pl-btn { background: rgba(204,136,255,.1); color: #cc88ff; border: 1px solid rgba(204,136,255,.3); padding: 4px 9px; border-radius: 8px; cursor: pointer; font-size: 14px; line-height: 1; }' +
      '.add-to-pl-btn:hover { background: rgba(204,136,255,.2); }'
    );
    const s = document.createElement('style');
    s.id = 'pl-extra-styles';
    s.textContent = css;
    document.head.appendChild(s);
  }

  // ── 11. CLICK DELEGATION ──────────────────────────────────────────────
  // - data-add-to-playlist="<track-id>" → openAddToPlaylistModal
  // - .pl-row[data-id] (dashboard playlist row) → openPlaylistViewModal
  // - .ap-playlist-card[data-pl-id] (profil public playlist card) → idem

  function _wireGlobalClicks() {
    if (window.__pl_clicks_wired) return;
    window.__pl_clicks_wired = true;
    // capture:true → intercepte AVANT marketplace.js (qui fait redirect profil)
    document.addEventListener('click', (ev) => {
      const addBtn = ev.target.closest('[data-add-to-playlist]');
      if (addBtn) {
        ev.preventDefault();
        ev.stopPropagation();
        ev.stopImmediatePropagation();
        const tid = addBtn.getAttribute('data-add-to-playlist');
        if (tid) openAddToPlaylistModal(tid);
        return;
      }
      // Open playlist view from dashboard row (avoid action buttons)
      const dashRow = ev.target.closest('.pl-row');
      if (dashRow && !ev.target.closest('.pl-row-actions')) {
        const id = dashRow.dataset.id;
        if (id) openPlaylistViewModal(id);
        return;
      }
      // ADN badge click → modale d'achat (avant le clic carte pour bloquer la propagation)
      const adnBadgeEl = ev.target.closest('.ap-pl-adn-badge[data-playlist-id]');
      if (adnBadgeEl) {
        ev.stopPropagation();
        const fn = window.SmylePlaylists && window.SmylePlaylists.openAdnPurchaseModal;
        if (fn) fn(adnBadgeEl);
        return;
      }

      // Open playlist view from profil public card
      // Exclure le bouton quick-play et le badge ADN pour ne pas intercepter leurs clicks
      const apCard = ev.target.closest('.ap-playlist-card[data-pl-id]');
      if (apCard && !ev.target.closest('.ap-pl-qp') && !ev.target.closest('.ap-pl-adn-badge')) {
        const id = apCard.dataset.plId;
        if (id) openPlaylistViewModal(id);
      }
    }, true);
  }

  // Boot styles + delegation on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { _injectExtraStyles(); _wireGlobalClicks(); });
  } else {
    _injectExtraStyles();
    _wireGlobalClicks();
  }

  // Expose
  window.SmylePlaylists.openAddToPlaylistModal = openAddToPlaylistModal;
  window.SmylePlaylists.openPlaylistViewModal  = openPlaylistViewModal;
})();

// ── 12. LIKES (via wishlist) + CSS COMPACT UNIFIÉ ──────────────────────────
// Like = ajout du track à la wishlist personnelle (playlist privée auto-créée).
// Réutilise les endpoints playlists existants : POST/DELETE /tracks.
// + Reset CSS minimaliste pour AUSSI corriger les .add-to-pl-btn déjà en prod
//   (qui faisaient une "barre blanche" sur les cards marketplace).

(function(){
  'use strict';

  const LIKES_KEY = 'smyle_liked_tracks';
  let _wishlistId = null;

  function _isAuth() {
    if (typeof getAuthToken === 'function') return !!getAuthToken();
    if (typeof getCurrentUser === 'function') {
      const u = getCurrentUser();
      return !!(u && u.id);
    }
    return false;
  }

  function _authHeaders() {
    const h = { 'Accept': 'application/json' };
    if (typeof getAuthToken === 'function') {
      const t = getAuthToken();
      if (t) h['Authorization'] = 'Bearer ' + t;
    }
    return h;
  }

  function _showToast(msg) {
    if (typeof showToast === 'function') return showToast(msg);
    if (window.showToast)               return window.showToast(msg);
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1a1a24;color:#fff;padding:12px 18px;border-radius:10px;border:1px solid rgba(204,136,255,.3);z-index:99999;font-size:14px';
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  function _readLiked() {
    try { return new Set(JSON.parse(localStorage.getItem(LIKES_KEY) || '[]')); }
    catch (_) { return new Set(); }
  }
  function _writeLiked(set) {
    try { localStorage.setItem(LIKES_KEY, JSON.stringify(Array.from(set))); }
    catch (_) {}
  }

  async function _ensureWishlistId() {
    if (_wishlistId) return _wishlistId;
    if (!_isAuth()) return null;
    try {
      const resp = await fetch('/playlists/wishlist', {
        credentials: 'same-origin', headers: _authHeaders()
      });
      if (!resp.ok) return null;
      const wl = await resp.json();
      _wishlistId = wl.id;
      return _wishlistId;
    } catch (_) { return null; }
  }

  async function loadLikedTrackIds() {
    if (!_isAuth()) return new Set();
    const wid = await _ensureWishlistId();
    if (!wid) return new Set();
    try {
      const resp = await fetch('/playlists/' + encodeURIComponent(wid), {
        credentials: 'same-origin', headers: _authHeaders()
      });
      if (!resp.ok) return new Set();
      const data = await resp.json();
      const set = new Set((data.tracks || []).map(t => String(t.id)));
      _writeLiked(set);
      return set;
    } catch (_) { return _readLiked(); }
  }

  function _applyLikedClass(set) {
    document.querySelectorAll('[data-like-btn]').forEach(btn => {
      const tid = btn.getAttribute('data-like-btn');
      if (tid && set.has(String(tid))) btn.classList.add('liked');
      else btn.classList.remove('liked');
    });
  }

  async function toggleLike(trackId) {
    if (!_isAuth()) {
      _showToast('Connecte-toi pour aimer.');
      return;
    }
    const wid = await _ensureWishlistId();
    if (!wid) {
      _showToast('Wishlist indisponible.');
      return;
    }
    const cur = _readLiked();
    const sTid = String(trackId);
    const wasLiked = cur.has(sTid);

    if (wasLiked) cur.delete(sTid);
    else cur.add(sTid);
    _writeLiked(cur);
    _applyLikedClass(cur);

    try {
      if (wasLiked) {
        const r = await fetch('/playlists/' + encodeURIComponent(wid) + '/tracks/' + encodeURIComponent(trackId), {
          method: 'DELETE', credentials: 'same-origin', headers: _authHeaders()
        });
        if (!r.ok && r.status !== 204 && r.status !== 404) throw new Error('HTTP ' + r.status);
      } else {
        const r = await fetch('/playlists/' + encodeURIComponent(wid) + '/tracks', {
          method: 'POST', credentials: 'same-origin',
          headers: Object.assign(_authHeaders(), { 'Content-Type': 'application/json' }),
          body: JSON.stringify({ track_id: trackId })
        });
        if (!r.ok && r.status !== 409) throw new Error('HTTP ' + r.status);
      }
    } catch (e) {
      if (wasLiked) cur.add(sTid);
      else cur.delete(sTid);
      _writeLiked(cur);
      _applyLikedClass(cur);
      _showToast('Like impossible : ' + (e && e.message || 'erreur'));
    }
  }

  function _wireLikeClicks() {
    if (window.__pl_like_wired) return;
    window.__pl_like_wired = true;
    document.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-like-btn]');
      if (!btn) return;
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation();
      const tid = btn.getAttribute('data-like-btn');
      if (tid) toggleLike(tid);
    }, true);
  }

  // ── CSS COMPACT UNIFIÉ — override les anciens styles .add-to-pl-btn
  // pour avoir un design minimaliste cohérent sur Top Sons + cards + profil.
  function _injectCompactStyles() {
    if (document.getElementById('pl-compact-styles')) return;
    const css = `
button.add-to-pl-btn, button.like-btn, .mp-son-card button.add-to-pl-btn, .mp-son-card button.like-btn, .mp-son-card-actions button.add-to-pl-btn, .mp-son-card-actions button.like-btn, .mp-ranking-row button.add-to-pl-btn, .mp-ranking-row button.like-btn, .ap-track-card button.add-to-pl-btn, .ap-track-card button.like-btn { width: 28px !important; min-width: 28px !important; max-width: 28px !important; height: 28px !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; padding: 0 !important; background: transparent !important; border: 1px solid rgba(255,255,255,.1) !important; color: #a09cb8 !important; border-radius: 7px !important; font-size: 13px !important; line-height: 1 !important; cursor: pointer !important; flex: 0 0 28px !important; box-sizing: border-box !important; vertical-align: middle !important; }
/* ── Boutons d'action sur cellules track (PR fix UI) ──────────────────────
   Design unifié minimaliste : icône carrée 26px, bordure très discrète,
   couleur de base gris doux, hover coloré subtil. Même look sur les 3
   emplacements : Top Sons row, mp-son-card marketplace, ap-track-card profil. */
.add-to-pl-btn, .like-btn {
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  width: 26px !important;
  height: 26px !important;
  padding: 0 !important;
  background: transparent !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  color: #a09cb8 !important;
  border-radius: 7px !important;
  font-size: 13px !important;
  line-height: 1 !important;
  cursor: pointer !important;
  transition: color .12s ease, border-color .12s ease, background .12s ease;
  vertical-align: middle;
  flex: 0 0 auto !important;
}
.add-to-pl-btn:hover {
  color: #cc88ff !important;
  border-color: rgba(204,136,255,.4) !important;
  background: rgba(204,136,255,.08) !important;
}
.like-btn::before { content: "\\2661"; font-size: 14px; }
.like-btn:hover {
  color: #ff7799 !important;
  border-color: rgba(255,119,153,.35) !important;
  background: rgba(255,119,153,.06) !important;
}
.like-btn.liked::before { content: "\\2665"; }
.like-btn.liked {
  color: #ff5577 !important;
  border-color: rgba(255,85,119,.45) !important;
  background: rgba(255,85,119,.1) !important;
}

/* Wrapper d'actions sur les cards marketplace : layout horizontal compact */
.mp-son-card-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 12px 10px;
}

/* Top Sons row : aligner les boutons (déjà flex sur la row) */
.mp-ranking-row .add-to-pl-btn,
.mp-ranking-row .like-btn { margin-left: 4px; }

/* Cellule profil artiste : la zone meta est déjà flex */
.ap-track-card-meta .add-to-pl-btn,
.ap-track-card-meta .like-btn { margin-left: 4px; }
`;
    const s = document.createElement('style');
    s.id = 'pl-compact-styles';
    s.textContent = css;
    document.head.appendChild(s);
  }

  async function _boot() {
    _injectCompactStyles();
    _wireLikeClicks();
    _applyLikedClass(_readLiked());
    if (_isAuth()) {
      try {
        const set = await loadLikedTrackIds();
        _applyLikedClass(set);
      } catch (_) {}
    }
    setTimeout(() => _applyLikedClass(_readLiked()), 1500);
    setTimeout(() => _applyLikedClass(_readLiked()), 4000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot);
  } else {
    _boot();
  }

  if (window.SmylePlaylists) {
    window.SmylePlaylists.toggleLike = toggleLike;
    window.SmylePlaylists.loadLikedTrackIds = loadLikedTrackIds;
  }
})();


// ── 14. CSS cover thumbnail modale view ────────────────────────────────
(function(){
  if (document.getElementById('pl-cover-thumb-styles')) return;
  function _inj() {
    if (document.getElementById('pl-cover-thumb-styles')) return;
    var css = '.pl-view-row-cover { width: 36px; height: 36px; border-radius: 6px; object-fit: cover; flex: 0 0 36px; margin-right: 8px; }';
    var st = document.createElement('style');
    st.id = 'pl-cover-thumb-styles';
    st.textContent = css;
    document.head.appendChild(st);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _inj);
  else _inj();
})();
