/* ═════════════════════════════════════════════════════════════════════════
   oeuvre-compose.js — Composer une ŒUVRE (binarité self-service)
   ─────────────────────────────────────────────────────────────────────────
   window.OeuvreCompose.open({ onSuccess })

   Modal autonome (injecte son CSS). Laisse un artiste LIER une de ses
   playlists (face SON) et un de ses albums (face VISUEL) en une œuvre :
   POST /artist/me/oeuvre → pose un oeuvre_slug partagé → la page
   /oeuvre/<slug> s'allume. C'est l'action « la binarité se complète » côté
   créateur lambda (équivalent manuel du seed officiel).

   Dépendances : window.apiFetch (api.js). Toast best-effort (window.smyleToast).
   ═════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _toast(msg, type) {
    if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' });
  }

  var CSS_ID = 'oc-css';
  function _injectCss() {
    if (document.getElementById(CSS_ID)) return;
    var st = document.createElement('style');
    st.id = CSS_ID;
    st.textContent =
      '.oc-overlay{position:fixed;inset:0;background:rgba(6,5,10,.66);display:flex;align-items:center;justify-content:center;z-index:10000;animation:ocFade .16s ease}' +
      '@keyframes ocFade{from{opacity:0}to{opacity:1}}' +
      '.oc-box{width:100%;max-width:440px;margin:16px;background:#16121f;border:1px solid rgba(124,92,255,.3);border-radius:18px;padding:22px;box-shadow:0 16px 60px rgba(0,0,0,.55);position:relative}' +
      '.oc-close{position:absolute;top:12px;right:14px;background:none;border:none;color:#cfc9e0;font-size:22px;cursor:pointer;line-height:1}' +
      '.oc-kicker{font-size:11px;font-weight:700;letter-spacing:.12em;color:#c7b8ff;margin:0 0 2px}' +
      '.oc-title{margin:0 0 4px;color:#fff;font-size:19px}' +
      '.oc-sub{margin:0 0 16px;font-size:12.5px;color:rgba(255,255,255,.55)}' +
      '.oc-field{margin-bottom:13px}' +
      '.oc-label{display:block;font-size:12px;color:rgba(255,255,255,.7);margin-bottom:5px}' +
      '.oc-label .oc-face{font-size:9px;font-weight:700;letter-spacing:.1em;padding:1px 6px;border-radius:999px;background:rgba(255,255,255,.1);margin-right:6px}' +
      '.oc-input,.oc-select{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:11px;border:1px solid rgba(255,255,255,.14);background:#1c1726;color:#fff;font-size:14px}' +
      '.oc-actions{display:flex;gap:10px;margin-top:18px}' +
      '.oc-cancel{flex:0 0 auto;padding:11px 16px;border-radius:11px;border:1px solid rgba(255,255,255,.14);background:none;color:#cfc9e0;font-weight:600;cursor:pointer}' +
      '.oc-confirm{flex:1;padding:11px 16px;border-radius:11px;border:none;background:linear-gradient(120deg,#7c5cff,#0055ff);color:#fff;font-weight:700;cursor:pointer}' +
      '.oc-confirm:disabled{opacity:.55;cursor:default}' +
      '.oc-err{color:#ff8a8a;font-size:12.5px;margin-top:10px;display:none}' +
      '.oc-done{text-align:center;padding:8px 0}' +
      '.oc-done a{color:#9dc0ff;font-weight:700;text-decoration:none}';
    document.head.appendChild(st);
  }

  function _options(items, emptyLabel) {
    if (!items || !items.length) {
      return '<option value="">' + _esc(emptyLabel) + '</option>';
    }
    return '<option value="">— Choisir —</option>' + items.map(function (it) {
      return '<option value="' + _esc(it.id) + '">' + _esc(it.title || 'Sans titre') + '</option>';
    }).join('');
  }

  function close() {
    var ov = document.getElementById('oc-overlay');
    if (ov) ov.remove();
    document.removeEventListener('keydown', _onEsc);
  }
  function _onEsc(e) { if (e.key === 'Escape') close(); }

  function open(opts) {
    opts = opts || {};
    if (document.getElementById('oc-overlay')) return;
    if (!window.apiFetch) { _toast('Connexion indisponible — recharge la page.', 'error'); return; }
    _injectCss();

    var ov = document.createElement('div');
    ov.id = 'oc-overlay';
    ov.className = 'oc-overlay';
    ov.innerHTML =
      '<div class="oc-box" role="dialog" aria-modal="true" aria-label="Composer une œuvre">' +
        '<button class="oc-close" aria-label="Fermer">&times;</button>' +
        '<p class="oc-kicker">ŒUVRE BINAIRE</p>' +
        '<h3 class="oc-title">Composer une œuvre</h3>' +
        '<p class="oc-sub">Lie une playlist (face son) et un album (face visuel) en une œuvre unique. Elle se complète quand les deux faces ont leur ADN.</p>' +
        '<div class="oc-field">' +
          '<label class="oc-label"><span class="oc-face">SON</span>Playlist</label>' +
          '<select class="oc-select" id="oc-playlist"><option value="">Chargement…</option></select>' +
        '</div>' +
        '<div class="oc-field">' +
          '<label class="oc-label"><span class="oc-face">VISUEL</span>Album</label>' +
          '<select class="oc-select" id="oc-album"><option value="">Chargement…</option></select>' +
        '</div>' +
        '<div class="oc-field">' +
          '<label class="oc-label">Titre de l\'œuvre <span style="opacity:.5">(optionnel)</span></label>' +
          '<input class="oc-input" id="oc-title" type="text" maxlength="120" placeholder="Ex. Jungle Osmose" />' +
        '</div>' +
        '<div class="oc-err" id="oc-err"></div>' +
        '<div class="oc-actions">' +
          '<button class="oc-cancel" type="button">Annuler</button>' +
          '<button class="oc-confirm" type="button">Lier l\'œuvre</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(ov);

    ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
    ov.querySelector('.oc-close').addEventListener('click', close);
    ov.querySelector('.oc-cancel').addEventListener('click', close);
    document.addEventListener('keydown', _onEsc);

    var errEl = ov.querySelector('#oc-err');
    function _err(msg) { errEl.textContent = msg; errEl.style.display = msg ? 'block' : 'none'; }

    // Charge playlists + albums du créateur en parallèle.
    Promise.all([
      window.apiFetch('/playlists/me').catch(function () { return []; }),
      window.apiFetch('/albums/me').catch(function () { return []; }),
    ]).then(function (res) {
      var pls = Array.isArray(res[0]) ? res[0] : (res[0] && res[0].items) || [];
      var als = Array.isArray(res[1]) ? res[1] : (res[1] && res[1].items) || [];
      var selP = ov.querySelector('#oc-playlist');
      var selA = ov.querySelector('#oc-album');
      if (selP) selP.innerHTML = _options(pls, 'Aucune playlist — crées-en une d\'abord');
      if (selA) selA.innerHTML = _options(als, 'Aucun album — crées-en un d\'abord');
    });

    ov.querySelector('.oc-confirm').addEventListener('click', function () {
      var btn = ov.querySelector('.oc-confirm');
      var pid = (ov.querySelector('#oc-playlist') || {}).value;
      var aid = (ov.querySelector('#oc-album') || {}).value;
      var title = (ov.querySelector('#oc-title') || {}).value || '';
      _err('');
      if (!pid || !aid) { _err('Choisis une playlist ET un album.'); return; }
      btn.disabled = true;
      btn.textContent = 'Liaison…';
      window.apiFetch('/artist/me/oeuvre', {
        method: 'POST',
        json: { playlist_id: pid, album_id: aid, title: title || null },
      }).then(function (resp) {
        var slug = resp && resp.slug;
        var url = (resp && resp.url) || ('/oeuvre/' + slug);
        _toast('Œuvre liée 🔗', 'success');
        var box = ov.querySelector('.oc-box');
        if (box) {
          box.innerHTML =
            '<button class="oc-close" aria-label="Fermer">&times;</button>' +
            '<p class="oc-kicker">ŒUVRE LIÉE ✓</p>' +
            '<h3 class="oc-title">C\'est en ligne</h3>' +
            '<div class="oc-done"><p class="oc-sub">Ton œuvre binaire est accessible ici :</p>' +
            '<a href="' + _esc(url) + '">' + _esc(url) + '</a></div>' +
            '<div class="oc-actions"><button class="oc-confirm" type="button" onclick="window.location.href=\'' + _esc(url) + '\'">Voir l\'œuvre</button></div>';
          box.querySelector('.oc-close').addEventListener('click', close);
        }
        if (typeof opts.onSuccess === 'function') { try { opts.onSuccess(resp); } catch (_) {} }
      }).catch(function (err) {
        btn.disabled = false;
        btn.textContent = 'Lier l\'œuvre';
        var s = err && err.status;
        if (s === 404) _err('Playlist ou album introuvable (vérifie qu\'ils t\'appartiennent).');
        else if (s === 409) _err('Ce titre d\'œuvre est déjà pris — choisis-en un autre.');
        else if (s === 422) _err('Donne un titre à l\'œuvre.');
        else if (s === 401) _err('Connecte-toi pour composer une œuvre.');
        else _err('Échec de la liaison. Réessaie.');
      });
    });
  }

  window.OeuvreCompose = { open: open, close: close };
})();
