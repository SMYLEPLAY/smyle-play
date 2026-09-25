/* ═════════════════════════════════════════════════════════════════════════
   oeuvre-invite.js — « Fais-en une Œuvre »  (Lot 2, 23/09)
   ─────────────────────────────────────────────────────────────────────────
   L'Œuvre = 1 son + 1 image. Juste après une publication, on propose tout de
   suite de compléter :
     • après un SON   → « Ajoute une image » : une de mes images, ou une nouvelle ;
     • après une IMAGE → « Ajoute un son »   : un de mes sons, ou un nouveau.

   « Une nouvelle » : on mémorise l'intention (sessionStorage) et on ouvre
   l'écran de création. À la publication suivante, `consumePending()` rend
   l'élément à lier, et la liaison se fait sans autre question.

   API :
     window.SmyleOeuvreInvite.afterSound({ trackId, title })
     window.SmyleOeuvreInvite.afterImage({ imageId, title })
     window.SmyleOeuvreInvite.consumePending(kind)   // 'track' | 'image'
     window.SmyleOeuvreInvite.linkTrackImage(trackId, imageId) → Promise<{oeuvreId,url}>

   Routes : GET/POST /artist/me/tracks/{id}/link(able),
            GET /artist/me/prompts/{imageId}/linkable (sons + morceaux sans recette),
            POST /artist/me/prompts/{imageId}/link (recette ↔ image, historique).
   Dépendances : window.apiFetch ; toast best-effort ; WattBoardV3 (dashboard).
   ═════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var PENDING_KEY = 'smyle_oeuvre_pending';
  var CSS_ID = 'oi-css';

  // Échappeur complet (& < > " ' `) — copie de ui/albums.js.
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }

  function _toast(msg, type) {
    try {
      if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' });
      if (typeof window.dashToast === 'function') return window.dashToast(msg);
      if (typeof window.showToast === 'function') return window.showToast(msg);
    } catch (_) {}
  }

  function _uuid(s) { return /^[0-9a-fA-F-]{36}$/.test(String(s || '')); }

  function _injectCss() {
    if (document.getElementById(CSS_ID)) return;
    var st = document.createElement('style');
    st.id = CSS_ID;
    st.textContent =
      '.oi-overlay{position:fixed;inset:0;background:rgba(6,5,10,.7);display:flex;align-items:center;justify-content:center;z-index:10050;padding:16px;box-sizing:border-box}' +
      '.oi-box{width:100%;max-width:460px;max-height:90vh;overflow:auto;background:#16121f;border:1px solid rgba(124,92,255,.3);border-radius:18px;padding:22px;position:relative;box-sizing:border-box}' +
      '.oi-close{position:absolute;top:10px;right:12px;background:none;border:none;color:#cfc9e0;font-size:22px;cursor:pointer;line-height:1}' +
      '.oi-kicker{font-size:11px;font-weight:700;letter-spacing:.12em;color:#c7b8ff;margin:0 0 4px}' +
      '.oi-title{margin:0 0 6px;color:#fff;font-size:19px}' +
      '.oi-sub{margin:0 0 16px;font-size:13px;color:rgba(255,255,255,.65);line-height:1.5}' +
      '.oi-choices{display:flex;flex-direction:column;gap:10px}' +
      '.oi-choice{display:block;width:100%;text-align:left;padding:13px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.04);color:#fff;cursor:pointer;font-size:14px;font-weight:600}' +
      '.oi-choice em{display:block;font-style:normal;font-weight:400;font-size:12px;color:rgba(255,255,255,.6);margin-top:2px}' +
      '.oi-later{margin-top:12px;background:none;border:none;color:rgba(255,255,255,.6);cursor:pointer;font-size:13px;text-decoration:underline;padding:4px 0}' +
      '.oi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:10px;margin-top:4px}' +
      '.oi-cand{display:flex;flex-direction:column;gap:6px;padding:8px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.03);color:#fff;cursor:pointer;text-align:left;font-size:12px}' +
      '.oi-cand:disabled{opacity:.5;cursor:default}' +
      '.oi-thumb{width:100%;aspect-ratio:1/1;border-radius:8px;overflow:hidden;background:#0e0b16;display:flex;align-items:center;justify-content:center;font-size:24px}' +
      '.oi-thumb img{width:100%;height:100%;object-fit:cover;display:block}' +
      '.oi-cand-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.oi-empty{font-size:13px;color:rgba(255,255,255,.6)}' +
      '.oi-done a{color:#9dc0ff;font-weight:700;text-decoration:none;word-break:break-all}' +
      '.oi-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}' +
      '.oi-primary{padding:11px 16px;border-radius:11px;border:none;background:linear-gradient(120deg,#7c5cff,#0055ff);color:#fff;font-weight:700;cursor:pointer}' +
      '.oi-secondary{padding:11px 16px;border-radius:11px;border:1px solid rgba(255,255,255,.2);background:none;color:#fff;font-weight:600;cursor:pointer}' +
      '.oi-choice:focus-visible,.oi-cand:focus-visible,.oi-primary:focus-visible,.oi-secondary:focus-visible{outline:2px solid #ffd700;outline-offset:2px}';
    document.head.appendChild(st);
  }

  function _close() {
    var ov = document.getElementById('oi-overlay');
    if (ov) ov.remove();
  }

  function _open(inner) {
    _injectCss();
    _close();
    var ov = document.createElement('div');
    ov.id = 'oi-overlay';
    ov.className = 'oi-overlay';
    ov.innerHTML = '<div class="oi-box" role="dialog" aria-modal="true" aria-labelledby="oi-title">' +
      '<button type="button" class="oi-close" aria-label="Fermer">×</button>' +
      '<div id="oi-body">' + inner + '</div></div>';
    ov.addEventListener('click', function (e) {
      if (e.target === ov || e.target.closest('.oi-close') || e.target.closest('.oi-later')) _close();
    });
    document.body.appendChild(ov);
    return ov;
  }

  function _body(html) {
    var b = document.getElementById('oi-body');
    if (b) b.innerHTML = html;
    return b;
  }

  // ── Intention « une nouvelle » mémorisée pour la prochaine publication ──
  function _setPending(kind, id) {
    try { sessionStorage.setItem(PENDING_KEY, JSON.stringify({ kind: kind, id: id, at: Date.now() })); } catch (_) {}
  }

  function consumePending(kind) {
    try {
      var raw = sessionStorage.getItem(PENDING_KEY);
      if (!raw) return null;
      var p = JSON.parse(raw);
      // Une intention vieille de plus d'une heure est oubliée.
      if (!p || p.kind !== kind || !_uuid(p.id) || (Date.now() - (p.at || 0)) > 3600 * 1000) return null;
      sessionStorage.removeItem(PENDING_KEY);
      return p.id;
    } catch (_) { return null; }
  }

  function linkTrackImage(trackId, imageId) {
    return window.apiFetch('/artist/me/tracks/' + encodeURIComponent(trackId) + '/link', {
      method: 'POST', json: { image_id: imageId, bundle_exclusive: false },
    });
  }

  function _done(resp) {
    var url = (resp && resp.url) || (resp && resp.oeuvreId ? '/o/' + resp.oeuvreId : null);
    var full = url ? (window.location.origin + url) : '';
    _body(
      '<p class="oi-kicker">ŒUVRE CRÉÉE ✓</p>' +
      '<h3 class="oi-title" id="oi-title">Ton œuvre est en ligne</h3>' +
      '<p class="oi-sub">Un son et une image réunis. Partage ce lien : il s\'affiche avec l\'image et le titre sur les réseaux.</p>' +
      (url ? '<p class="oi-done"><a href="' + _esc(url) + '">' + _esc(full) + '</a></p>' : '') +
      '<div class="oi-actions">' +
        (url ? '<button type="button" class="oi-primary" data-oi-copy="' + _esc(full) + '">Copier le lien</button>' +
               '<a class="oi-secondary" href="' + _esc(url) + '" style="text-decoration:none">Voir l\'œuvre</a>' : '') +
        '<button type="button" class="oi-later">Fermer</button>' +
      '</div>'
    );
    var b = document.querySelector('[data-oi-copy]');
    if (b) {
      b.addEventListener('click', function () {
        var link = b.getAttribute('data-oi-copy');
        try {
          navigator.clipboard.writeText(link).then(function () { _toast('Lien copié.', 'success'); },
            function () { window.prompt('Copie ce lien :', link); });
        } catch (_) { window.prompt('Copie ce lien :', link); }
      });
    }
    try { if (window.WattBoardV3 && window.WattBoardV3.refresh) window.WattBoardV3.refresh(); } catch (_) {}
  }

  function _err(e) {
    var s = e && e.status;
    _toast(s === 409 ? 'Déjà dans une autre œuvre — choisis-en un autre.'
                     : 'Liaison impossible pour le moment. Réessaie.', 'error');
  }

  function _thumb(c) {
    if (c.previewKey) {
      return '<img src="/watt/images/' + String(c.previewKey).split('/').map(encodeURIComponent).join('/') + '" alt="" />';
    }
    if (c.coverUrl) return '<img src="' + _esc(c.coverUrl) + '" alt="" />';
    return '<span aria-hidden="true">' + (c.kind === 'image' ? '🖼' : '🎵') + '</span>';
  }

  function _pickList(title, candidates, onPick) {
    if (!candidates.length) {
      _body('<p class="oi-kicker">ŒUVRE</p><h3 class="oi-title" id="oi-title">' + _esc(title) + '</h3>' +
        '<p class="oi-empty">Rien de disponible pour l\'instant (tout est déjà dans une œuvre, ou tu n\'as encore rien publié).</p>' +
        '<button type="button" class="oi-later">Fermer</button>');
      return;
    }
    var b = _body('<p class="oi-kicker">ŒUVRE</p><h3 class="oi-title" id="oi-title">' + _esc(title) + '</h3>' +
      '<div class="oi-grid">' + candidates.map(function (c, i) {
        return '<button type="button" class="oi-cand" data-oi-i="' + i + '">' +
          '<span class="oi-thumb">' + _thumb(c) + '</span>' +
          '<span class="oi-cand-title">' + _esc(c.title || 'Sans titre') + '</span></button>';
      }).join('') + '</div><button type="button" class="oi-later">Plus tard</button>');
    b.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-oi-i]');
      if (!btn) return;
      b.querySelectorAll('.oi-cand').forEach(function (x) { x.disabled = true; });
      onPick(candidates[parseInt(btn.getAttribute('data-oi-i'), 10)])
        .then(_done)
        .catch(function (err) {
          _err(err);
          b.querySelectorAll('.oi-cand').forEach(function (x) { x.disabled = false; });
        });
    });
  }

  // ── Après un SON : « Ajoute une image » ────────────────────────────────
  function afterSound(opts) {
    opts = opts || {};
    var trackId = opts.trackId;
    if (!_uuid(trackId) || !window.apiFetch) return;
    var title = opts.title || 'ton son';
    _open(
      '<p class="oi-kicker">FAIS-EN UNE ŒUVRE</p>' +
      '<h3 class="oi-title" id="oi-title">Ajoute une image à « ' + _esc(title) + ' »</h3>' +
      '<p class="oi-sub">Une œuvre, c\'est un son et une image ensemble, avec sa propre page à partager.</p>' +
      '<div class="oi-choices">' +
        '<button type="button" class="oi-choice" data-oi="existing">Choisir une de mes images<em>Parmi celles qui ne sont pas déjà dans une œuvre</em></button>' +
        '<button type="button" class="oi-choice" data-oi="new">Créer une nouvelle image<em>Elle sera ajoutée à ce son dès sa publication</em></button>' +
      '</div>' +
      '<button type="button" class="oi-later">Plus tard</button>'
    );
    var b = document.getElementById('oi-body');
    b.addEventListener('click', function (e) {
      var c = e.target.closest('[data-oi]');
      if (!c) return;
      if (c.getAttribute('data-oi') === 'new') {
        _setPending('track', trackId);
        _close();
        _toast('Crée ton image : elle sera ajoutée à « ' + title + ' » à la publication.');
        try {
          if (window.WattBoardV3) window.WattBoardV3.open('images');
          else window.location.href = '/dashboard#images';
        } catch (_) {}
        return;
      }
      window.apiFetch('/artist/me/tracks/' + encodeURIComponent(trackId) + '/linkable')
        .then(function (list) {
          _pickList('Choisis une image', Array.isArray(list) ? list : [], function (img) {
            return linkTrackImage(trackId, img.id);
          });
        })
        .catch(function () { _toast('Impossible de charger tes images.', 'error'); });
    }, { once: false });
  }

  // ── Après une IMAGE : « Ajoute un son » ────────────────────────────────
  function afterImage(opts) {
    opts = opts || {};
    var imageId = opts.imageId;
    if (!_uuid(imageId) || !window.apiFetch) return;
    var title = opts.title || 'ton image';
    _open(
      '<p class="oi-kicker">FAIS-EN UNE ŒUVRE</p>' +
      '<h3 class="oi-title" id="oi-title">Ajoute un son à « ' + _esc(title) + ' »</h3>' +
      '<p class="oi-sub">Un son qui met ton image en valeur. Ensemble, ils forment une œuvre avec sa page à partager.</p>' +
      '<div class="oi-choices">' +
        '<button type="button" class="oi-choice" data-oi="existing">Choisir un de mes sons<em>Parmi ceux qui ne sont pas déjà dans une œuvre</em></button>' +
        '<button type="button" class="oi-choice" data-oi="new">Publier un nouveau son<em>Il sera ajouté à cette image dès sa publication</em></button>' +
      '</div>' +
      '<button type="button" class="oi-later">Plus tard</button>'
    );
    var b = document.getElementById('oi-body');
    b.addEventListener('click', function (e) {
      var c = e.target.closest('[data-oi]');
      if (!c) return;
      if (c.getAttribute('data-oi') === 'new') {
        _setPending('image', imageId);
        _close();
        _toast('Publie ton son : il sera ajouté à « ' + title + ' » à la publication.');
        try {
          if (window.WattBoardV3) window.WattBoardV3.open('sons');
          else window.location.href = '/dashboard';
        } catch (_) {}
        return;
      }
      window.apiFetch('/artist/me/prompts/' + encodeURIComponent(imageId) + '/linkable')
        .then(function (list) {
          _pickList('Choisis un son', Array.isArray(list) ? list : [], function (snd) {
            if (snd.kind === 'track') return linkTrackImage(snd.id, imageId);
            // Recette sonore (liaison historique recette ↔ image).
            return window.apiFetch('/artist/me/prompts/' + encodeURIComponent(imageId) + '/link', {
              method: 'POST', json: { other_prompt_id: snd.id, bundle_exclusive: false }, raw: true,
            }).then(function () { return { oeuvreId: imageId, url: '/o/' + imageId }; });
          });
        })
        .catch(function () { _toast('Impossible de charger tes sons.', 'error'); });
    });
  }

  window.SmyleOeuvreInvite = {
    afterSound: afterSound,
    afterImage: afterImage,
    consumePending: consumePending,
    linkTrackImage: linkTrackImage,
    showDone: function (resp) { _open(''); _done(resp); },
  };
})();
