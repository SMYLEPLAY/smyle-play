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
      try { detail = (await resp.json()).detail || ''; } catch (_) {}
      const err = new Error('HTTP ' + resp.status + (detail ? ' — ' + detail : ''));
      err.status = resp.status;
      throw err;
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  async function loadMyPlaylists() {
    return _req('/playlists/me');
  }

  async function createPlaylist(title, visibility) {
    return _req('/playlists', {
      method: 'POST',
      body: { title: title, visibility: visibility || 'private' }
    });
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
    overlay.innerHTML = (
      '<div class="pl-modal" role="dialog" aria-labelledby="pl-modal-title">' +
        '<button type="button" class="pl-modal-close" aria-label="Fermer">✕</button>' +
        '<h3 id="pl-modal-title" class="pl-modal-title">Nouvelle playlist</h3>' +
        '<label class="pl-modal-label">Nom' +
          '<input type="text" id="pl-modal-name" maxlength="200" placeholder="Ma playlist…" autofocus />' +
        '</label>' +
        '<fieldset class="pl-modal-vis">' +
          '<legend>Visibilité</legend>' +
          '<label class="pl-vis-opt">' +
            '<input type="radio" name="pl-vis" value="private" checked /> ' +
            '<span><strong>Privée</strong> · visible uniquement par toi</span>' +
          '</label>' +
          '<label class="pl-vis-opt">' +
            '<input type="radio" name="pl-vis" value="public" /> ' +
            '<span><strong>Publique</strong> · visible sur ton profil /u/&lt;slug&gt;</span>' +
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

    const close = () => overlay.remove();
    overlay.querySelector('.pl-modal-close').onclick = close;
    overlay.querySelector('#pl-modal-cancel').onclick = close;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#pl-modal-create').onclick = async () => {
      const name = overlay.querySelector('#pl-modal-name').value.trim();
      const vis  = overlay.querySelector('input[name="pl-vis"]:checked').value;
      const errBox = overlay.querySelector('#pl-modal-err');
      errBox.style.display = 'none';
      if (!name) {
        errBox.textContent = 'Donne un nom à ta playlist.';
        errBox.style.display = 'block';
        return;
      }
      try {
        const created = await createPlaylist(name, vis);
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
      // Artiste public section
      '.ap-playlists-section { padding: 0 12px; margin: 20px 0 28px; }' +
      '.ap-playlists-hdr { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }' +
      '.ap-playlists-title { font-size: 18px; color: #fff; margin: 0; letter-spacing: -.01em; }' +
      '.ap-playlists-count { font-size: 12px; color: #a09cb8; }' +
      '.ap-playlists-list { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }' +
      '.ap-playlist-card { background: linear-gradient(180deg, rgba(255,255,255,.025), rgba(255,255,255,.005)); border: 1px solid rgba(204,136,255,.16); border-radius: 12px; padding: 14px 16px; cursor: default; }' +
      '.ap-playlist-card-title { color: #fff; font-size: 14px; font-weight: 600; margin: 0 0 4px; }' +
      '.ap-playlist-card-meta { font-size: 11px; color: #a09cb8; }'
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
          return (
            '<li class="pl-row" data-id="' + p.id + '" data-vis="' + p.visibility + '">' +
              '<div>' +
                '<div class="pl-row-name">' + _esc(p.title) + '</div>' +
                '<div class="pl-row-meta">' + badge + '</div>' +
              '</div>' +
              '<div class="pl-row-actions">' +
                '<button type="button" class="pl-icon-btn pl-act-vis" title="Changer visibilité">' +
                  (p.visibility === 'public' ? 'Rendre privée' : 'Rendre publique') +
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

    // Délégation pour boutons toggle / delete
    root.querySelector('#pl-dash-list').addEventListener('click', async (ev) => {
      const row = ev.target.closest('.pl-row');
      if (!row) return;
      const id = row.dataset.id;
      const vis = row.dataset.vis;
      if (ev.target.closest('.pl-act-vis')) {
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

    await reload();
  }

  // ── 4. RENDERER PROFIL PUBLIC ─────────────────────────────────────────────

  async function renderArtistPlaylists(slug, containerId) {
    const root = document.getElementById(containerId);
    if (!root) return;
    _injectModalStyles();
    try {
      const playlists = await loadArtistPublicPlaylists(slug);
      if (!playlists || playlists.length === 0) {
        // Section invisible si rien de public — pas la peine de polluer le profil
        root.style.display = 'none';
        return;
      }
      root.style.display = '';
      root.innerHTML = (
        '<section class="ap-playlists-section" aria-label="Playlists publiques">' +
          '<div class="ap-playlists-hdr">' +
            '<h2 class="ap-playlists-title">Playlists</h2>' +
            '<span class="ap-playlists-count">' + playlists.length + ' playlist' + (playlists.length > 1 ? 's' : '') + '</span>' +
          '</div>' +
          '<ul class="ap-playlists-list">' +
            playlists.map(p => (
              '<li class="ap-playlist-card" data-pl-id="' + p.id + '">' +
                '<div class="ap-playlist-card-title">' + _esc(p.title) + '</div>' +
                '<div class="ap-playlist-card-meta">' + _fmtDate(p.created_at) + '</div>' +
              '</li>'
            )).join('') +
          '</ul>' +
        '</section>'
      );
    } catch (e) {
      // Erreur silencieuse côté public — on ne casse pas le profil pour ça
      root.style.display = 'none';
      console.warn('[playlists] artist load failed:', e);
    }
  }

  // ── 5. UTILS ──────────────────────────────────────────────────────────────

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

  // ── 6. EXPORTS ────────────────────────────────────────────────────────────

  window.SmylePlaylists = {
    loadMyPlaylists,
    createPlaylist,
    deletePlaylist,
    togglePlaylistVisibility,
    loadArtistPublicPlaylists,
    openCreatePlaylistModal,
    renderDashboardPlaylists,
    renderArtistPlaylists
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
        (tracks.length === 0
          ? '<p class="pl-empty">Aucune track. Ajoute des sons depuis la marketplace via le bouton +.</p>'
          : '<ul class="pl-view-list">' + tracks.map(t => {
              const safe = String(t.name || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
              const url = t.stream_url || t.streamUrl || '';
              const safeUrl = url.replace(/"/g, '&quot;');
              return '<li class="pl-view-row" data-track-id="' + t.id + '">' +
                '<div class="pl-view-row-info">' +
                  '<div class="pl-view-row-title">' + safe + '</div>' +
                '</div>' +
                (safeUrl ? '<audio controls preload="none" class="pl-view-audio" src="' + safeUrl + '"></audio>' : '<span class="pl-empty">Audio indisponible</span>') +
              '</li>';
            }).join('') + '</ul>'
        )
      );
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
    document.addEventListener('click', (ev) => {
      const addBtn = ev.target.closest('[data-add-to-playlist]');
      if (addBtn) {
        ev.preventDefault();
        ev.stopPropagation();
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
      // Open playlist view from profil public card
      const apCard = ev.target.closest('.ap-playlist-card[data-pl-id]');
      if (apCard) {
        const id = apCard.dataset.plId;
        if (id) openPlaylistViewModal(id);
      }
    });
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
      const tid = btn.getAttribute('data-like-btn');
      if (tid) toggleLike(tid);
    });
  }

  // ── CSS COMPACT UNIFIÉ — override les anciens styles .add-to-pl-btn
  // pour avoir un design minimaliste cohérent sur Top Sons + cards + profil.
  function _injectCompactStyles() {
    if (document.getElementById('pl-compact-styles')) return;
    const css = `
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

