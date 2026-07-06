/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/albums.js
   Albums d'images (curation visuelle) — calque le pattern playlists.js.

   Couvre 3 choses :
     1) My Mix monde IMAGE : commutateur Musique ⇄ Image (localStorage
        clé `mymix_mode`), rendu « ♥ Images likées » (GET /me/likes/prompts
        ?product_type=image) + « 🖼 Mes albums » (GET /albums/me).
     2) Vue & gestion d'un album (GET /albums/{id}, PATCH, DELETE,
        DELETE /albums/{id}/images/{prompt_id}) — modale.
     3) « Ajouter à un album » : listener délégué global sur
        [data-add-to-album="<prompt_id>"] → openAddToAlbumModal (calque
        data-add-to-playlist / openAddToPlaylistModal).

   Endpoints backend (déjà codés) :
     POST   /albums                      {title, visibility}
     GET    /albums/me                   → [{id,title,visibility,coverPreviewKey,imageCount,createdAt}]
     GET    /albums/{id}                 → {…, images:[{id,previewKey,title,priceCredits,productType}]}
     PATCH  /albums/{id}                 {title?, visibility?}
     DELETE /albums/{id}
     POST   /albums/{id}/images          {prompt_id}
     DELETE /albums/{id}/images/{prompt_id}

   Réutilise : window.SmylePlaylists.hydrateImgLikes (état ❤️),
   data-img-like-btn (toggle like global), window.PurchaseDrawer (fiche image).
   Charger APRÈS ui/playlists.js.
   ───────────────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  // ── Helpers communs ─────────────────────────────────────────────────────
  function _isAuth() {
    if (typeof getAuthToken === 'function') return !!getAuthToken();
    if (typeof getCurrentUser === 'function') {
      const u = getCurrentUser();
      return !!(u && u.id);
    }
    return false;
  }

  function _headers(json) {
    const h = { 'Accept': 'application/json' };
    if (json) h['Content-Type'] = 'application/json';
    if (typeof getAuthToken === 'function') {
      const t = getAuthToken();
      if (t) h['Authorization'] = 'Bearer ' + t;
    }
    return h;
  }

  function _toast(msg) {
    if (typeof showToast === 'function') return showToast(msg);
    if (window.showToast) return window.showToast(msg);
  }

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c]
    ));
  }

  // Aperçu image via le proxy backend (sert UNIQUEMENT images/previews/).
  function _imgPreviewUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  // ── ADN Album — codes de style (alignés EXACTEMENT sur le backend) ────────
  // Source : STYLES création image (dashboard.html #imgcStyle / backend).
  const ADN_STYLES = [
    { v: 'realiste',    l: 'Réaliste' },
    { v: 'cartoon',     l: 'Cartoon' },
    { v: 'anime',       l: 'Anime' },
    { v: '3d',          l: '3D / Render' },
    { v: 'peinture',    l: 'Peinture' },
    { v: 'aquarelle',   l: 'Aquarelle' },
    { v: 'croquis',     l: 'Croquis' },
    { v: 'pixel_art',   l: 'Pixel art' },
    { v: 'cyberpunk',   l: 'Cyberpunk' },
    { v: 'fantasy',     l: 'Fantasy' },
    { v: 'minimaliste', l: 'Minimaliste' },
    { v: 'retro',       l: 'Rétro' },
    { v: 'abstrait',    l: 'Abstrait' },
    { v: 'surrealiste', l: 'Surréaliste' },
    { v: 'comics',      l: 'Comics' },
    { v: 'photo',       l: 'Photo' },
  ];

  function _styleLabel(code) {
    const m = ADN_STYLES.find(s => s.v === code);
    return m ? m.l : (code || '');
  }

  function _styleOptions(selected) {
    return '<option value="">— Aucun style —</option>' + ADN_STYLES.map(s =>
      '<option value="' + s.v + '"' + (s.v === selected ? ' selected' : '') + '>' + _esc(s.l) + '</option>'
    ).join('');
  }

  // ── API albums ───────────────────────────────────────────────────────────
  async function loadMyAlbums() {
    if (!_isAuth()) return [];
    try {
      const r = await fetch('/albums/me', { credentials: 'same-origin', headers: _headers() });
      if (!r.ok) return [];
      const data = await r.json();
      return Array.isArray(data) ? data : (data.items || data.albums || []);
    } catch (_) { return []; }
  }

  async function loadAlbum(id) {
    // Authentifié → /albums/{id} (gating génome calculé pour le viewer :
    // owner / acheteur voient le seedPrompt, sinon NULL). Non authentifié →
    // route publique /watt/albums/{id} (album public uniquement, génome gaté).
    const path = _isAuth()
      ? '/albums/' + encodeURIComponent(id)
      : '/watt/albums/' + encodeURIComponent(id);
    const r = await fetch(path, { credentials: 'same-origin', headers: _headers() });
    if (!r.ok) { const e = new Error('load'); e.status = r.status; throw e; }
    return r.json();
  }

  async function createAlbum(title, visibility) {
    const r = await fetch('/albums', {
      method: 'POST', credentials: 'same-origin', headers: _headers(true),
      body: JSON.stringify({ title: title, visibility: visibility || 'private' })
    });
    if (!r.ok) { const e = new Error('create'); e.status = r.status; throw e; }
    return r.json();
  }

  async function patchAlbum(id, patch) {
    const r = await fetch('/albums/' + encodeURIComponent(id), {
      method: 'PATCH', credentials: 'same-origin', headers: _headers(true),
      body: JSON.stringify(patch)
    });
    if (!r.ok) { const e = new Error('patch'); e.status = r.status; throw e; }
    return r.json();
  }

  async function deleteAlbum(id) {
    const r = await fetch('/albums/' + encodeURIComponent(id), {
      method: 'DELETE', credentials: 'same-origin', headers: _headers()
    });
    return r.ok || r.status === 204;
  }

  async function addImageToAlbum(albumId, promptId) {
    const r = await fetch('/albums/' + encodeURIComponent(albumId) + '/images', {
      method: 'POST', credentials: 'same-origin', headers: _headers(true),
      body: JSON.stringify({ prompt_id: promptId })
    });
    if (!r.ok && r.status !== 201) { const e = new Error('add'); e.status = r.status; throw e; }
    return true;
  }

  async function removeImageFromAlbum(albumId, promptId) {
    const r = await fetch('/albums/' + encodeURIComponent(albumId) + '/images/' + encodeURIComponent(promptId), {
      method: 'DELETE', credentials: 'same-origin', headers: _headers()
    });
    return r.ok || r.status === 204;
  }

  // ── Crée un album à la volée (mini-prompt titre + visibilité) ─────────────
  // Retourne l'album créé ou null si annulé. Respecte la règle projet :
  // tout UI de création/édition collection DOIT exposer le choix public/privé.
  async function promptCreateAlbum() {
    const title = window.prompt('Titre du nouvel album :');
    if (title == null) return null;
    const t = title.trim();
    if (!t) { _toast('Titre requis.'); return null; }
    const pub = window.confirm('Album PUBLIC ? (OK = public · Annuler = privé)');
    try {
      const album = await createAlbum(t, pub ? 'public' : 'private');
      _toast('Album « ' + t + ' » créé ✓');
      return album;
    } catch (e) {
      _toast('Création impossible (' + (e && e.status || 'erreur') + ').');
      return null;
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // VOLET B — Modale « Ajouter à un album » (calque openAddToPlaylistModal)
  // ══════════════════════════════════════════════════════════════════════════
  async function openAddToAlbumModal(promptId) {
    if (!promptId) return;
    if (!_isAuth()) { _toast('Connecte-toi pour ajouter à un album.'); return; }
    if (document.getElementById('al-add-modal')) return;
    if (window.SmylePlaylists && window.SmylePlaylists.injectModalStyles) {
      window.SmylePlaylists.injectModalStyles();
    }

    const overlay = document.createElement('div');
    overlay.id = 'al-add-modal';
    overlay.className = 'pl-modal-overlay';
    overlay.innerHTML = (
      '<div class="pl-modal" role="dialog">' +
        '<button type="button" class="pl-modal-close" aria-label="Fermer">✕</button>' +
        '<h3 class="pl-modal-title">Ajouter à un album</h3>' +
        '<div id="al-add-list" class="pl-add-list">Chargement…</div>' +
        '<div class="pl-modal-actions">' +
          '<button type="button" class="pl-btn pl-btn-ghost" id="al-add-cancel">Annuler</button>' +
          '<button type="button" class="pl-btn pl-btn-primary" id="al-add-new">+ Nouvel album</button>' +
        '</div>' +
      '</div>'
    );
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('.pl-modal-close').onclick = close;
    overlay.querySelector('#al-add-cancel').onclick = close;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#al-add-new').onclick = async () => {
      const album = await promptCreateAlbum();
      if (album && album.id) {
        try {
          await addImageToAlbum(album.id, promptId);
          _toast('Ajoutée à « ' + (album.title || 'album') + ' » ✓');
          close();
        } catch (e) {
          if (e && e.status === 409) { _toast('Déjà dans cet album.'); close(); }
          else _toast('Ajout impossible.');
        }
      }
    };

    const listEl = overlay.querySelector('#al-add-list');
    const albums = await loadMyAlbums();
    if (!albums.length) {
      listEl.innerHTML = '<p class="pl-empty">Aucun album. Clique « + Nouvel album » ci-dessous.</p>';
      return;
    }
    listEl.innerHTML = '<ul class="pl-picker-list">' + albums.map(a => {
      const badge = a.visibility === 'public' ? 'Public' : 'Privé';
      const safeTitle = _esc(a.title || 'Sans nom');
      return '<li><button type="button" class="pl-picker-row" data-al-id="' + _esc(a.id) + '" data-al-title="' + safeTitle + '">' +
        '<span>' + safeTitle + ' <span style="opacity:.6;font-size:.85em">· ' + (a.imageCount || 0) + ' img</span></span>' +
        '<span class="pl-picker-vis">' + badge + '</span>' +
      '</button></li>';
    }).join('') + '</ul>';

    listEl.addEventListener('click', async (ev) => {
      const btn = ev.target.closest('.pl-picker-row');
      if (!btn) return;
      const id = btn.dataset.alId;
      const title = btn.dataset.alTitle || '';
      btn.disabled = true; btn.style.opacity = '.6';
      try {
        await addImageToAlbum(id, promptId);
        _toast('Ajoutée à « ' + title + ' » ✓');
        close();
      } catch (e) {
        btn.disabled = false; btn.style.opacity = '';
        if (e && e.status === 409) { _toast('Déjà dans cet album.'); close(); }
        else if (e && e.status === 403) { _toast('Tu ne peux pas modifier cet album.'); }
        else { _toast('Ajout impossible.'); }
      }
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // VOLET B — Modale « Vue album » (grille images + édition titre/visibilité
  //           + retrait d'image). Owner uniquement pour les actions.
  // ══════════════════════════════════════════════════════════════════════════
  async function openAlbumViewModal(albumId) {
    if (!albumId) return;
    if (document.getElementById('al-view-modal')) return;
    if (window.SmylePlaylists && window.SmylePlaylists.injectModalStyles) {
      window.SmylePlaylists.injectModalStyles();
    }

    const overlay = document.createElement('div');
    overlay.id = 'al-view-modal';
    overlay.className = 'pl-modal-overlay';
    overlay.innerHTML = (
      '<div class="pl-modal pl-modal-wide" role="dialog">' +
        '<button type="button" class="pl-modal-close" aria-label="Fermer">✕</button>' +
        '<div id="al-view-content">Chargement…</div>' +
      '</div>'
    );
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.querySelector('.pl-modal-close').onclick = close;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    const content = overlay.querySelector('#al-view-content');

    async function render() {
      let album;
      try {
        album = await loadAlbum(albumId);
      } catch (e) {
        content.innerHTML = (e && e.status === 404)
          ? '<p class="pl-empty">Album introuvable ou privé.</p>'
          : '<p class="pl-empty">Chargement impossible.</p>';
        return;
      }
      const images = Array.isArray(album.images) ? album.images : [];
      const isPublic = album.visibility === 'public';
      const visLabel = isPublic ? '🌐 Public' : '🔒 Privé';

      // Owner ? (compare owner_id de l'album avec l'utilisateur courant). Les
      // outils d'édition + la section « vendre l'ADN » sont owner-only ; un
      // non-owner sur un album public voit le teaser ADN + le bouton d'achat.
      let _me = null;
      try { _me = (typeof getCurrentUser === 'function') ? getCurrentUser() : null; } catch (_) {}
      const myId = _me && _me.id ? String(_me.id) : null;
      const ownerId = album.ownerId || album.owner_id || null;
      const isOwner = !!(myId && ownerId && String(ownerId) === myId);

      const grid = images.length
        ? '<div class="al-view-grid">' + images.map(im => {
            const url = _imgPreviewUrl(im.previewKey);
            const cover = url
              ? '<img src="' + _esc(url) + '" alt="' + _esc(im.title || 'Image') + '" loading="lazy" />'
              : '<div class="al-view-fallback">🖼</div>';
            const price = (im.priceCredits != null)
              ? '<span class="al-view-price">' + _esc(im.priceCredits) + ' Smyles</span>' : '';
            const removeBtn = isOwner
              ? '<button type="button" class="al-view-remove" data-remove-image="' + _esc(im.id) + '" title="Retirer de l\'album">✕</button>'
              : '';
            return '<article class="al-view-cell" data-image-id="' + _esc(im.id) + '" title="' + _esc(im.title || 'Image') + '">' +
              '<div class="al-view-thumb">' + cover + removeBtn +
              '</div>' +
              '<div class="al-view-cap">' + _esc(im.title || 'Image IA') + price + '</div>' +
            '</article>';
          }).join('') + '</div>'
        : '<p class="pl-empty">Album vide. Ajoute des images via « Ajouter à un album » sur une fiche image.</p>';

      // ── Bloc ADN Album ────────────────────────────────────────────────────
      // Owner   → éditeur de vente (toggle / prix / style / palette / génome /
      //           teaser). L'ADN ne se vend QUE si l'album est public.
      // Visiteur → teaser (style + description + prix) + bouton d'achat si en
      //            vente. Le génome (seedPrompt + palette) n'est JAMAIS affiché
      //            avant achat (le backend le renvoie déjà NULL).
      const adnBlock = isOwner
        ? _adnOwnerEditorHtml(album, isPublic)
        : _adnViewerHtml(album);

      content.innerHTML =
        '<div class="al-view-hdr">' +
          '<h3 class="pl-modal-title" id="al-view-title">' + _esc(album.title || 'Album') + '</h3>' +
          '<div class="al-view-tools">' +
            '<span class="al-view-vis-badge">' + visLabel + '</span>' +
            (isOwner
              ? '<button type="button" class="pl-btn pl-btn-ghost" id="al-edit-title">✎ Renommer</button>' +
                '<button type="button" class="pl-btn pl-btn-ghost" id="al-toggle-vis">' +
                  (isPublic ? '🔒 Passer en privé' : '🌐 Passer en public') + '</button>'
              : '') +
          '</div>' +
        '</div>' +
        adnBlock +
        grid;

      // Câblage ADN (owner = éditeur PATCH · visiteur = achat)
      if (isOwner) _wireAdnOwnerEditor(content, album, isPublic, render);
      else _wireAdnViewer(content, album);

      // Renommer (titre)
      const editTitleBtn = content.querySelector('#al-edit-title');
      if (editTitleBtn) editTitleBtn.onclick = async () => {
        const nt = window.prompt('Nouveau titre de l\'album :', album.title || '');
        if (nt == null) return;
        const t = nt.trim();
        if (!t) { _toast('Titre requis.'); return; }
        try { await patchAlbum(albumId, { title: t }); _toast('Titre mis à jour ✓'); await render(); _refreshAlbumList(); }
        catch (e) { _toast(e && e.status === 403 ? 'Action non autorisée.' : 'Échec.'); }
      };

      // Toggle public/privé EXPLICITE (règle projet)
      const visBtn = content.querySelector('#al-toggle-vis');
      if (visBtn) visBtn.onclick = async () => {
        const next = isPublic ? 'private' : 'public';
        try { await patchAlbum(albumId, { visibility: next }); _toast(next === 'public' ? 'Album public ✓' : 'Album privé ✓'); await render(); _refreshAlbumList(); }
        catch (e) { _toast(e && e.status === 403 ? 'Action non autorisée.' : 'Échec.'); }
      };

      // Retrait d'image (délégué)
      content.querySelectorAll('[data-remove-image]').forEach(btn => {
        btn.onclick = async (ev) => {
          ev.stopPropagation();
          const pid = btn.getAttribute('data-remove-image');
          if (!confirm('Retirer cette image de l\'album ?')) return;
          const ok = await removeImageFromAlbum(albumId, pid);
          if (ok) { _toast('Image retirée.'); await render(); _refreshAlbumList(); }
          else _toast('Retrait impossible.');
        };
      });

      // Clic vignette (hors bouton retirer) → fiche d'achat image
      content.querySelectorAll('.al-view-cell').forEach(cell => {
        cell.onclick = (ev) => {
          if (ev.target.closest('[data-remove-image]')) return;
          const id = cell.dataset.imageId;
          if (!id) return;
          if (window.PurchaseDrawer && typeof window.PurchaseDrawer.open === 'function') {
            window.PurchaseDrawer.open({ type: 'image', id: id });
          }
        };
      });
    }

    _injectAlbumStyles();
    render();
  }

  // ══════════════════════════════════════════════════════════════════════════
  // VOLET B-bis — ADN ALBUM (génome de style vendable) — calque ADN Playlist
  // ══════════════════════════════════════════════════════════════════════════

  // Bannière d'honnêteté — obligatoire partout où on vend un ADN.
  const ADN_HONEST = 'Un ADN donne des résultats dans le même esprit, jamais identiques. Tu achètes la recette de style, pas une copie.';

  // ── OWNER : éditeur de vente de l'ADN ─────────────────────────────────────
  function _adnOwnerEditorHtml(album, isPublic) {
    const forSale = !!album.adnForSale;
    const price   = album.adnPrice || '';
    const style   = album.adnStyle || '';
    const palette = album.adnPalette || '';
    const seed    = album.seedPrompt || '';
    const teaser  = album.dnaDescription || '';

    // L'ADN ne peut être vendu que si l'album est PUBLIC (règle backend).
    const lockedNotice = !isPublic
      ? '<p class="al-adn-lock">🔒 Passe l\'album en public pour vendre son ADN. ' +
        'Le génome reste masqué pour les visiteurs tant qu\'ils ne l\'ont pas acheté.</p>'
      : '';

    return '' +
      '<section class="al-adn-block al-adn-owner">' +
        '<div class="al-adn-hdr"><span class="al-adn-ico">🎨</span>' +
          '<h4 class="al-adn-title">ADN de l\'album</h4></div>' +
        '<p class="al-adn-honest">' + _esc(ADN_HONEST) + '</p>' +
        lockedNotice +
        '<label class="al-adn-toggle-label">' +
          '<input type="checkbox" id="al-adn-sale" ' + (forSale ? 'checked' : '') +
            (isPublic ? '' : ' disabled') + ' /> ' +
          '<span>🎨 Vendre l\'ADN de cet album</span>' +
        '</label>' +
        '<div class="al-adn-fields" id="al-adn-fields" style="display:' + (forSale && isPublic ? '' : 'none') + '">' +
          '<label class="al-adn-lbl" for="al-adn-price">Prix en Smyles (1 – 100 000)</label>' +
          '<input type="number" id="al-adn-price" class="dash-input" min="1" max="100000" placeholder="ex : 50" value="' + _esc(price) + '" />' +

          // OFFRES-ADN étape 5 : plancher CACHÉ (write-only → toujours vide).
          '<label class="al-adn-lbl" for="al-adn-reserve">Plancher caché des offres <span class="al-adn-opt">(optionnel)</span></label>' +
          '<input type="number" id="al-adn-reserve" class="dash-input" min="0" max="100000" placeholder="Minimum accepté — jamais montré aux acheteurs" />' +
          '<p class="al-adn-hint">Les offres en dessous sont refusées automatiquement. Vide = inchangé · 0 = pas de plancher.</p>' +

          '<label class="al-adn-lbl" for="al-adn-style">Style dominant</label>' +
          '<select id="al-adn-style" class="dash-input">' + _styleOptions(style) + '</select>' +

          '<label class="al-adn-lbl" for="al-adn-palette">Palette / mots-clés <span class="al-adn-opt">(teaser visible)</span></label>' +
          '<input type="text" id="al-adn-palette" class="dash-input" maxlength="255" placeholder="ex : néon mauve, chrome, brouillard nocturne" value="' + _esc(palette) + '" />' +

          '<label class="al-adn-lbl" for="al-adn-desc">Description publique <span class="al-adn-opt">(teaser court — visible avant achat)</span></label>' +
          '<textarea id="al-adn-desc" class="dash-input" rows="2" maxlength="2000" placeholder="Décris l\'esprit de cet ADN sans révéler la recette…">' + _esc(teaser) + '</textarea>' +

          '<label class="al-adn-lbl" for="al-adn-seed">Génome — la recette de style vendue <span class="al-adn-opt">(verrouillé publiquement)</span></label>' +
          '<textarea id="al-adn-seed" class="dash-input" rows="4" maxlength="10000" placeholder="Le prompt / la recette de style que l\'acheteur reçoit…">' + _esc(seed) + '</textarea>' +
          '<p class="al-adn-hint">🔒 Le génome (recette + palette détaillée) reste masqué tant que la vente est active — révélé seulement à l\'acheteur.</p>' +
        '</div>' +
        '<button type="button" class="pl-btn pl-btn-primary al-adn-save" id="al-adn-save">Enregistrer l\'ADN</button>' +
        '<div class="al-adn-err" id="al-adn-err" style="display:none"></div>' +
      '</section>';
  }

  function _wireAdnOwnerEditor(content, album, isPublic, rerender) {
    const chk     = content.querySelector('#al-adn-sale');
    const fields  = content.querySelector('#al-adn-fields');
    const saveBtn = content.querySelector('#al-adn-save');
    const errEl   = content.querySelector('#al-adn-err');
    if (chk && fields) {
      chk.addEventListener('change', () => {
        fields.style.display = (chk.checked && isPublic) ? '' : 'none';
      });
    }
    if (!saveBtn) return;
    saveBtn.addEventListener('click', async () => {
      const sale    = !!(chk && chk.checked && isPublic);
      const price   = sale ? (parseInt(content.querySelector('#al-adn-price').value, 10) || null) : null;
      const style   = (content.querySelector('#al-adn-style') ? content.querySelector('#al-adn-style').value : '') || '';
      const palette = (content.querySelector('#al-adn-palette') ? content.querySelector('#al-adn-palette').value : '').trim();
      const desc    = (content.querySelector('#al-adn-desc') ? content.querySelector('#al-adn-desc').value : '').trim();
      const seed    = (content.querySelector('#al-adn-seed') ? content.querySelector('#al-adn-seed').value : '').trim();

      if (sale && !price) {
        if (errEl) { errEl.textContent = 'Fixe un prix en Smyles pour activer la vente de l\'ADN.'; errEl.style.display = 'block'; }
        return;
      }
      if (sale && !seed) {
        if (errEl) { errEl.textContent = 'Écris le génome — on ne vend pas une recette vide.'; errEl.style.display = 'block'; }
        return;
      }

      // PATCH /albums/{id} — calque STRICT du PATCH ADN Playlist.
      const patch = { adn_for_sale: sale };
      patch.adn_price       = sale ? price : null;
      patch.adn_style       = style || null;
      patch.adn_palette     = palette || null;
      patch.dna_description = desc || null;
      if (seed) patch.seed_prompt = seed;
      // Plancher caché (offres) : n'envoie QUE si saisi.
      const reserveRaw = (content.querySelector('#al-adn-reserve')?.value || '').trim();
      if (reserveRaw !== '') {
        const reserveVal = parseInt(reserveRaw, 10);
        if (!isNaN(reserveVal) && reserveVal >= 0) patch.adn_reserve_credits = reserveVal;
      }

      saveBtn.disabled = true;
      saveBtn.textContent = 'Sauvegarde…';
      if (errEl) errEl.style.display = 'none';
      try {
        await patchAlbum(album.id, patch);
        _toast(sale ? 'ADN en vente ✓' : 'ADN mis à jour ✓');
        await rerender();
        _refreshAlbumList();
      } catch (e) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Enregistrer l\'ADN';
        const msg = (e && e.status === 404) ? 'Action non autorisée.' : 'Échec de l\'enregistrement.';
        if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
      }
    });
  }

  // ── VISITEUR : teaser ADN + bouton d'achat ────────────────────────────────
  function _adnViewerHtml(album) {
    const forSale = !!album.adnForSale;
    // Génome déjà possédé / album pas en vente → le backend renvoie seedPrompt.
    const ownsGenome = !!album.seedPrompt;

    if (ownsGenome) {
      // Acheteur (ou ADN pas en vente avec génome exposé) : on affiche le génome.
      const style = album.adnStyle ? '<span class="al-adn-chip">' + _esc(_styleLabel(album.adnStyle)) + '</span>' : '';
      const pal   = album.adnPalette ? '<div class="al-adn-line"><b>Palette :</b> ' + _esc(album.adnPalette) + '</div>' : '';
      return '' +
        '<section class="al-adn-block al-adn-owned">' +
          '<div class="al-adn-hdr"><span class="al-adn-ico">🎨</span>' +
            '<h4 class="al-adn-title">ADN de l\'album ' + style + '</h4>' +
            '<span class="al-adn-owned-badge">✅ Possédé</span></div>' +
          (album.dnaDescription ? '<p class="al-adn-desc">' + _esc(album.dnaDescription) + '</p>' : '') +
          pal +
          '<div class="al-adn-genome"><div class="al-adn-genome-lbl">🧬 Génome</div>' +
            '<div class="al-adn-genome-body">' + _esc(album.seedPrompt) + '</div></div>' +
        '</section>';
    }

    if (!forSale) return '';  // pas en vente, pas possédé → rien

    // En vente, non possédé : teaser SEUL. JAMAIS de génome ici.
    // OFFRES-ADN (2026-07-03) : plus d'achat direct (backend 410) — vente
    // sur proposition uniquement → bouton « Faire une offre » (étape 3).
    const style = album.adnStyle ? '<span class="al-adn-chip">' + _esc(_styleLabel(album.adnStyle)) + '</span>' : '';
    return '' +
      '<section class="al-adn-block al-adn-sale">' +
        '<div class="al-adn-hdr"><span class="al-adn-ico">🎨</span>' +
          '<h4 class="al-adn-title">ADN de l\'album ' + style + '</h4></div>' +
        '<p class="al-adn-honest">' + _esc(ADN_HONEST) + '</p>' +
        (album.dnaDescription ? '<p class="al-adn-desc">' + _esc(album.dnaDescription) + '</p>' : '') +
        '<div class="al-adn-offer-info">🤝 Cet ADN se vend sur proposition — ' +
          'offre libre, l\'artiste accepte ou refuse.</div>' +
        '<div class="al-adn-buy-row">' +
          '<button type="button" class="pl-btn pl-btn-primary al-adn-buy-btn" ' +
            'id="al-adn-offer" data-album-id="' + _esc(album.id) + '">' +
            '🤝 Faire une offre</button>' +
        '</div>' +
      '</section>';
  }

  function _wireAdnViewer(content, album) {
    // OFFRES-ADN : bouton « Faire une offre » (remplace l'achat direct).
    const offerBtn = content.querySelector('#al-adn-offer');
    if (offerBtn) {
      offerBtn.addEventListener('click', () => {
        if (window.AdnOfferModal) {
          window.AdnOfferModal.open({
            targetType: 'album_adn',
            targetId:   album.id,
            title:      album.title || 'ADN d\'album',
          });
        }
      });
    }
    const btn = content.querySelector('#al-adn-buy');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      const errEl = content.querySelector('#al-adn-buy-err');
      if (!_isAuth()) {
        if (errEl) { errEl.textContent = 'Connecte-toi pour acheter cet ADN.'; errEl.style.display = 'block'; }
        return;
      }
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = 'Traitement…';
      if (errEl) errEl.style.display = 'none';
      try {
        await unlockAlbumAdn(album.id);
        _toast('ADN album débloqué 🎨 — génome révélé');
        if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
          window.SmyleBalance.refresh();
        }
        // Re-fetch : le génome devient visible après achat. Le plus simple et
        // le plus sûr — recharger la modale entière (re-GET /albums/{id}).
        const overlay = document.getElementById('al-view-modal');
        if (overlay) { overlay.remove(); openAlbumViewModal(album.id); }
      } catch (e) {
        btn.disabled = false;
        btn.textContent = prev;
        const s = e && e.status;
        const msg = s === 402 ? 'Crédits insuffisants.'
                  : s === 409 ? 'Tu possèdes déjà cet ADN.'
                  : s === 401 ? 'Connecte-toi pour acheter.'
                  : 'Erreur lors de l\'achat.';
        if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
      }
    });
  }

  // Achat ADN album — POST /unlocks/album-adn/{id} (calque playlist-adn).
  async function unlockAlbumAdn(albumId) {
    const r = await fetch('/unlocks/album-adn/' + encodeURIComponent(albumId), {
      method: 'POST', credentials: 'same-origin', headers: _headers(true)
    });
    if (!r.ok) { const e = new Error('unlock'); e.status = r.status; throw e; }
    return r.json().catch(() => ({}));
  }

  // ══════════════════════════════════════════════════════════════════════════
  // VOLET A — MY MIX monde IMAGE (commutateur + likées + albums)
  // ══════════════════════════════════════════════════════════════════════════
  const MODE_KEY = 'mymix_mode';

  function _getMode() {
    try {
      const m = localStorage.getItem(MODE_KEY);
      return (m === 'image') ? 'image' : 'musique';
    } catch (_) { return 'musique'; }
  }
  function _setMode(mode) {
    try { localStorage.setItem(MODE_KEY, mode === 'image' ? 'image' : 'musique'); } catch (_) {}
  }

  function applyMixMode(mode) {
    const panel = document.getElementById('mixPanel');
    if (!panel) return;
    const m = (mode === 'image') ? 'image' : 'musique';
    panel.classList.toggle('mymix-mode-image', m === 'image');
    panel.classList.toggle('mymix-mode-musique', m !== 'image');
    panel.querySelectorAll('[data-mymix-mode]').forEach(btn => {
      btn.setAttribute('aria-selected', btn.getAttribute('data-mymix-mode') === m ? 'true' : 'false');
    });
    if (m === 'image') renderMixImageWorld();
  }

  function setMixMode(mode) {
    _setMode(mode);
    applyMixMode(mode);
  }

  // Rendu des deux sections image (likées + albums)
  async function renderMixImageWorld() {
    renderMixLikedImages();
    _refreshAlbumList();
  }

  async function renderMixLikedImages() {
    const el = document.getElementById('mymix-liked-list');
    const countEl = document.getElementById('mymix-liked-count');
    if (!el) return;
    if (!_isAuth()) {
      el.innerHTML = '<div class="mymix-img-empty">Connecte-toi pour voir tes images likées.</div>';
      if (countEl) countEl.textContent = '0';
      return;
    }
    el.innerHTML = '<div class="mymix-img-empty">Chargement…</div>';
    let data;
    try {
      const r = await fetch('/me/likes/prompts?product_type=image', {
        credentials: 'same-origin', headers: _headers()
      });
      if (!r.ok) throw new Error('http');
      data = await r.json();
    } catch (_) {
      el.innerHTML = '<div class="mymix-img-empty">Impossible de charger tes images likées.</div>';
      return;
    }
    const imgs = (data && Array.isArray(data.images)) ? data.images : [];
    if (countEl) countEl.textContent = String(imgs.length);
    if (!imgs.length) {
      el.innerHTML = '<div class="mymix-img-empty">Aucune image likée — explore le monde Visuel.</div>';
      return;
    }
    el.innerHTML = imgs.map(im => {
      const url = _imgPreviewUrl(im.previewKey || im.preview_r2_key || '');
      const cover = url
        ? '<img src="' + _esc(url) + '" alt="' + _esc(im.title || 'Image') + '" loading="lazy" />'
        : '<div class="mymix-liked-fallback">🖼</div>';
      const likeBtn = '<button type="button" class="like-btn" data-img-like-btn="' + _esc(im.id) + '" title="Retirer des likes" aria-label="Retirer des likes" onclick="event.stopPropagation()"></button>';
      const price = (im.priceCredits != null) ? (_esc(im.priceCredits) + ' Smyles') : '';
      return '<article class="mymix-liked-card" data-image-id="' + _esc(im.id) + '" title="Voir la fiche">' +
        cover + likeBtn +
        '<div class="mymix-liked-cap">' + _esc(im.title || 'Image IA') + (price ? (' · ' + price) : '') + '</div>' +
      '</article>';
    }).join('');

    // Hydrate l'état ❤️ via le système partagé.
    if (window.SmylePlaylists && typeof window.SmylePlaylists.hydrateImgLikes === 'function') {
      window.SmylePlaylists.hydrateImgLikes();
    }

    // Clic carte → fiche image (drawer). Le ❤️ est géré par le listener global.
    el.querySelectorAll('.mymix-liked-card').forEach(card => {
      card.addEventListener('click', (ev) => {
        if (ev.target.closest('[data-img-like-btn]')) return;
        const id = card.dataset.imageId;
        if (!id) return;
        if (window.PurchaseDrawer && typeof window.PurchaseDrawer.open === 'function') {
          window.PurchaseDrawer.open({ type: 'image', id: id });
        } else {
          window.location.href = '/images';
        }
      });
    });

    // Au unlike → retire la card (le listener global toggle .liked).
    _wireLikedUnlike(el, countEl);
  }

  function _wireLikedUnlike(container, countEl) {
    if (container.__al_unlike_wired) return;
    container.__al_unlike_wired = true;
    container.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-img-like-btn]');
      if (!btn) return;
      const card = btn.closest('.mymix-liked-card');
      if (!card) return;
      setTimeout(() => {
        if (!btn.classList.contains('liked')) {
          card.remove();
          if (countEl) {
            const n = container.querySelectorAll('.mymix-liked-card').length;
            countEl.textContent = String(n);
            if (!n) container.innerHTML = '<div class="mymix-img-empty">Aucune image likée — explore le monde Visuel.</div>';
          }
        }
      }, 60);
    });
  }

  async function _refreshAlbumList() {
    const el = document.getElementById('mymix-album-list');
    if (!el) return;
    if (!_isAuth()) {
      el.innerHTML = '<div class="mymix-img-empty">Connecte-toi pour gérer tes albums.</div>';
      return;
    }
    el.innerHTML = '<div class="mymix-img-empty">Chargement…</div>';
    const albums = await loadMyAlbums();
    if (!albums.length) {
      el.innerHTML = '<div class="mymix-img-empty">Aucun album. Crée-en un avec « + Nouvel album ».</div>';
      return;
    }
    albums.sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
    el.innerHTML = albums.map(a => {
      const url = _imgPreviewUrl(a.coverPreviewKey);
      const cover = url
        ? '<img class="mymix-album-cover" src="' + _esc(url) + '" alt="" loading="lazy" />'
        : '<div class="mymix-album-cover">🖼</div>';
      const badge = a.visibility === 'public' ? '🌐 Public' : '🔒 Privé';
      const n = a.imageCount || 0;
      return '<div class="mymix-album-item" data-album-id="' + _esc(a.id) + '" title="Ouvrir l\'album">' +
        cover +
        '<div class="mymix-album-info">' +
          '<div class="mymix-album-name">' + _esc(a.title || 'Sans nom') + '</div>' +
          '<div class="mymix-album-meta">' + badge + ' · ' + n + ' image' + (n > 1 ? 's' : '') + '</div>' +
        '</div>' +
        '<button type="button" class="mymix-album-del" data-album-del="' + _esc(a.id) + '" title="Supprimer l\'album">🗑</button>' +
      '</div>';
    }).join('');

    el.querySelectorAll('.mymix-album-item').forEach(item => {
      item.addEventListener('click', (ev) => {
        if (ev.target.closest('[data-album-del]')) return;
        openAlbumViewModal(item.dataset.albumId);
      });
    });
    el.querySelectorAll('[data-album-del]').forEach(btn => {
      btn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const id = btn.getAttribute('data-album-del');
        if (!confirm('Supprimer cet album ? Les images restent dans ta bibliothèque, seul le regroupement est supprimé.')) return;
        const ok = await deleteAlbum(id);
        if (ok) { _toast('Album supprimé.'); _refreshAlbumList(); }
        else _toast('Suppression impossible.');
      });
    });
  }

  // ── Styles modale album (réutilise les classes pl-* + un peu de grille) ───
  function _injectAlbumStyles() {
    if (document.getElementById('al-view-styles')) return;
    const css = `
      .al-view-hdr { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; }
      .al-view-tools { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
      .al-view-vis-badge { font-size:12px; color:#cbb3ff; padding:3px 10px; border-radius:999px; background:rgba(124,77,255,.15); }
      .al-view-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(120px,1fr)); gap:10px; }
      .al-view-cell { cursor:pointer; }
      .al-view-thumb { position:relative; aspect-ratio:1/1; border-radius:9px; overflow:hidden; background:rgba(124,77,255,.08); border:1px solid rgba(124,77,255,.15); }
      .al-view-thumb img { width:100%; height:100%; object-fit:cover; display:block; }
      .al-view-fallback { display:flex; align-items:center; justify-content:center; height:100%; font-size:2rem; }
      .al-view-remove { position:absolute; top:5px; right:5px; width:24px; height:24px; border-radius:50%; border:none; cursor:pointer; background:rgba(0,0,0,.6); color:#fff; font-size:12px; line-height:1; }
      .al-view-remove:hover { background:#ff4444; }
      .al-view-cap { margin-top:5px; font-size:11px; color:rgba(255,255,255,.85); display:flex; flex-direction:column; gap:2px; }
      .al-view-price { color:#cbb3ff; font-weight:700; font-size:10px; }

      /* ── Bloc ADN Album ── */
      .al-adn-block { margin:16px 0 18px; padding:16px; border-radius:14px; border:1px solid rgba(204,136,255,.22); background:rgba(204,136,255,.06); }
      .al-adn-hdr { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
      .al-adn-ico { font-size:18px; }
      .al-adn-title { margin:0; font-size:15px; font-weight:700; color:#f3e9ff; }
      .al-adn-chip { font-size:11px; font-weight:700; color:#cc88ff; background:rgba(204,136,255,.14); border:1px solid rgba(204,136,255,.3); border-radius:999px; padding:2px 9px; margin-left:6px; }
      .al-adn-honest { font-size:11.5px; color:#b9b3d0; line-height:1.5; margin:0 0 10px; border-left:2px solid rgba(204,136,255,.4); padding-left:10px; }
      .al-adn-desc { font-size:12.5px; color:#cdc7e2; line-height:1.55; margin:0 0 10px; }
      .al-adn-lock { font-size:12px; color:#ffce8a; background:rgba(255,184,0,.08); border:1px solid rgba(255,184,0,.25); border-radius:9px; padding:9px 11px; margin:0 0 12px; line-height:1.5; }
      .al-adn-toggle-label { display:flex; align-items:center; gap:9px; cursor:pointer; font-size:13.5px; font-weight:600; color:#e8e6f5; }
      .al-adn-toggle-label input[type=checkbox] { width:16px; height:16px; accent-color:#cc88ff; cursor:pointer; }
      .al-adn-toggle-label input[disabled] { cursor:not-allowed; opacity:.5; }
      .al-adn-fields { margin-top:12px; display:flex; flex-direction:column; gap:4px; }
      .al-adn-lbl { font-size:11.5px; font-weight:600; color:#bdb6d6; margin-top:8px; }
      .al-adn-opt { font-weight:400; color:#7d7896; }
      .al-adn-fields .dash-input { width:100%; }
      .al-adn-hint { font-size:11px; color:#8b86a3; margin:6px 0 0; line-height:1.5; }
      .al-adn-save { margin-top:14px; }
      .al-adn-err { margin-top:10px; font-size:12px; color:#ff6b6b; }
      .al-adn-buy-row { margin-top:6px; }
      .al-adn-buy-btn { width:100%; }
      .al-adn-offer-info { margin-top:8px; font-size:12.5px; color:#a09cb8; line-height:1.5; text-align:center; padding:10px 8px; border:1px dashed rgba(204,136,255,.3); border-radius:10px; }
      .al-adn-owned-badge { font-size:11px; font-weight:700; color:#6fffb0; margin-left:auto; }
      .al-adn-line { font-size:12px; color:#cdc7e2; margin:0 0 8px; }
      .al-adn-genome { margin-top:10px; border:1px solid rgba(204,136,255,.25); border-radius:10px; overflow:hidden; }
      .al-adn-genome-lbl { font-size:11px; font-weight:700; color:#cc88ff; background:rgba(204,136,255,.1); padding:7px 11px; }
      .al-adn-genome-body { padding:11px; font-size:12.5px; color:#e3def2; white-space:pre-wrap; line-height:1.55; }
    `;
    const s = document.createElement('style');
    s.id = 'al-view-styles';
    s.textContent = css;
    document.head.appendChild(s);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // VOLET B — Délégation globale [data-add-to-album] (calque data-add-to-playlist)
  // ══════════════════════════════════════════════════════════════════════════
  function _wireGlobalClicks() {
    if (window.__al_clicks_wired) return;
    window.__al_clicks_wired = true;
    // capture:true → intercepte avant les handlers de carte (ouvrent une fiche)
    document.addEventListener('click', (ev) => {
      const addBtn = ev.target.closest('[data-add-to-album]');
      if (addBtn) {
        ev.preventDefault();
        ev.stopPropagation();
        ev.stopImmediatePropagation();
        const pid = addBtn.getAttribute('data-add-to-album');
        if (pid) openAddToAlbumModal(pid);
        return;
      }
      // Commutateur Musique ⇄ Image du panneau My Mix
      const switchBtn = ev.target.closest('[data-mymix-mode]');
      if (switchBtn && switchBtn.closest('#mixPanel')) {
        setMixMode(switchBtn.getAttribute('data-mymix-mode'));
        return;
      }
    }, true);

    // Bouton « + Nouvel album » du panneau image
    document.addEventListener('click', async (ev) => {
      const newBtn = ev.target.closest('#mymix-album-new');
      if (!newBtn) return;
      const album = await promptCreateAlbum();
      if (album) _refreshAlbumList();
    });
  }

  function _boot() {
    _wireGlobalClicks();
    // Appliquer le mode persisté au panneau dès le chargement.
    applyMixMode(_getMode());
    // Deep-link depuis le WattBoard (tuile « ADN visuel » / « Albums ») : si la
    // tuile a posé `mymix_open` avant de rediriger ici, on ouvre My Mix une fois.
    try {
      if (localStorage.getItem('mymix_open') === '1') {
        localStorage.removeItem('mymix_open');
        if (typeof toggleMixPanel === 'function') {
          // léger délai → laisse le reste du boot home s'initialiser
          setTimeout(function () { try { toggleMixPanel(); } catch (_) {} }, 250);
        }
      }
    } catch (_) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot);
  } else {
    _boot();
  }

  // Expose pour mix.js (rafraîchir le monde image à l'ouverture du panneau)
  window.SmyleAlbums = {
    openAddToAlbumModal,
    openAlbumViewModal,
    renderMixImageWorld,
    applyMixMode,
    getMixMode: _getMode,
    loadMyAlbums,
    unlockAlbumAdn,
    setMixMode,
  };
})();
