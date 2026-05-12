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
    return _req('/api/playlists/me');
  }

  async function createPlaylist(title, visibility) {
    return _req('/api/playlists', {
      method: 'POST',
      body: { title: title, visibility: visibility || 'private' }
    });
  }

  async function deletePlaylist(id) {
    return _req('/api/playlists/' + encodeURIComponent(id), { method: 'DELETE' });
  }

  async function togglePlaylistVisibility(id, currentVis) {
    const next = currentVis === 'public' ? 'private' : 'public';
    return _req('/api/playlists/' + encodeURIComponent(id), {
      method: 'PATCH',
      body: { visibility: next }
    });
  }

  async function loadArtistPublicPlaylists(slug) {
    return _req('/api/users/' + encodeURIComponent(slug) + '/playlists');
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
              '<li class="ap-playlist-card">' +
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
