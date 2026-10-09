/* ═════════════════════════════════════════════════════════════════════════
   mes-oeuvres.js — écran « Mes Œuvres » (Parcours V1, 9/10/2026)
   ─────────────────────────────────────────────────────────────────────────
   Liste de mes Œuvres (vignette, titre, écoute, recette, prix, statut,
   ventes), sélection multiple et actions groupées (Masquer, Republier,
   Changer le prix 10–150, Supprimer), bouton « Modifier » par Œuvre (titre,
   description, image, prix).

   Rien n'enlève l'accès de ceux qui ont déjà payé : c'est garanti côté
   serveur (règle de protection des acheteurs) et rappelé dans les textes.
   ═════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var PRIX_MIN = 10;
  var PRIX_MAX = 150;
  var CONFIRM_SUPPR = 'Ton œuvre disparaît de la plateforme. Ceux qui l\'ont déjà achetée la gardent.';

  var _items = [];
  var _sel = new Set();
  var _audio = null;
  var _playing = null;

  function $(id) { return document.getElementById(id); }
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }
  var _tt;
  function _toast(msg) {
    var t = $('mo-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('is-on');
    clearTimeout(_tt);
    _tt = setTimeout(function () { t.classList.remove('is-on'); }, 3200);
  }
  function _errMsg(e, fallback) {
    var d = e && e.body && e.body.detail;
    if (typeof d === 'string' && d) return d;
    if (d && typeof d === 'object' && d.message) return d.message;
    if (Array.isArray(d) && d[0] && d[0].msg) return d[0].msg;
    return fallback;
  }
  function _thumb(it) {
    if (it.image && it.image.previewKey) {
      return '/watt/images/' + String(it.image.previewKey).split('/').map(encodeURIComponent).join('/');
    }
    return it.coverUrl || '';
  }
  var STATUTS = { publiee: 'Publiée', masquee: 'Masquée', retiree: 'Retirée par la modération' };

  // ── Rendu ────────────────────────────────────────────────────────────────
  function render() {
    var list = $('mo-list');
    if (!_items.length) {
      list.innerHTML = '<div class="mo-state">Tu n\'as pas encore publié d\'Œuvre.<br>' +
        '<a href="/dashboard#sec-upload">Publie ton premier son</a> : il apparaîtra ici.</div>';
      _syncBar();
      return;
    }
    list.innerHTML = _items.map(function (it) {
      var src = _thumb(it);
      var sel = _sel.has(it.trackId);
      var recette = it.recipe
        ? '<span>Recette <b>' + _esc(it.recipe.priceCredits) + ' Smyles</b></span>'
        : '<span>Pas de recette en vente</span>';
      var image = it.image ? '<span>Image <b>' + _esc(it.image.priceCredits) + ' Smyles</b></span>' : '';
      var ventes = '<span><b>' + _esc(it.sales) + '</b> vente' + (it.sales > 1 ? 's' : '') + '</span>';
      return '<article class="mo-row' + (sel ? ' is-selected' : '') + (it.status !== 'publiee' ? ' is-hidden' : '') +
          '" data-id="' + _esc(it.trackId) + '">' +
        '<input type="checkbox" class="mo-check" data-check="' + _esc(it.trackId) + '"' + (sel ? ' checked' : '') +
          ' aria-label="Sélectionner « ' + _esc(it.title) + ' »" />' +
        '<div class="mo-thumb">' + (src ? '<img src="' + _esc(src) + '" alt="" loading="lazy" />' : '<span aria-hidden="true">🎵</span>') +
          (it.streamUrl ? '<button type="button" class="mo-play" data-play="' + _esc(it.trackId) + '" aria-label="Écouter « ' +
            _esc(it.title) + ' »">' + (_playing === it.trackId ? '❚❚' : '▶') + '</button>' : '') +
        '</div>' +
        '<div class="mo-info">' +
          '<p class="mo-name">' + _esc(it.title) + '</p>' +
          '<div class="mo-meta">' +
            '<span class="mo-pill mo-pill--' + _esc(it.status) + '">' + _esc(STATUTS[it.status] || it.status) + '</span>' +
            recette + image + ventes +
          '</div>' +
        '</div>' +
        '<div class="mo-actions">' +
          (it.oeuvreUrl && it.status === 'publiee' ? '<a class="mo-btn" href="' + _esc(it.oeuvreUrl) + '">Voir</a>' : '') +
          '<button type="button" class="mo-btn" data-edit="' + _esc(it.trackId) + '">Modifier</button>' +
        '</div>' +
      '</article>';
    }).join('');
    _syncBar();
  }

  function _syncBar() {
    var n = _sel.size;
    $('mo-count').textContent = n + ' sélectionnée' + (n > 1 ? 's' : '');
    document.querySelectorAll('[data-bulk]').forEach(function (b) { b.disabled = n === 0; });
    var all = $('mo-all');
    all.checked = n > 0 && n === _items.length;
    all.indeterminate = n > 0 && n < _items.length;
  }

  // ── Chargement ───────────────────────────────────────────────────────────
  function load() {
    return window.apiFetch('/artist/me/oeuvres').then(function (d) {
      _items = (d && d.items) || [];
      var ids = new Set(_items.map(function (i) { return i.trackId; }));
      _sel.forEach(function (id) { if (!ids.has(id)) _sel.delete(id); });
      render();
    }).catch(function (e) {
      $('mo-list').innerHTML = '<div class="mo-state">' + _esc(_errMsg(e, 'Impossible de charger tes Œuvres pour le moment. Recharge la page.')) + '</div>';
    });
  }

  // ── Écoute ───────────────────────────────────────────────────────────────
  function _play(id) {
    var it = _items.find(function (x) { return x.trackId === id; });
    if (!it || !it.streamUrl) return;
    if (!_audio) {
      _audio = new Audio();
      _audio.addEventListener('ended', function () { _playing = null; render(); });
    }
    if (_playing === id) { _audio.pause(); _playing = null; render(); return; }
    _audio.src = it.streamUrl;
    _audio.play().then(function () { _playing = id; render(); }).catch(function () {
      _toast('Lecture impossible pour le moment.');
    });
  }

  // ── Fenêtres ─────────────────────────────────────────────────────────────
  function _open(html, onReady) {
    $('mo-modal-box').innerHTML = html;
    $('mo-modal').hidden = false;
    if (onReady) onReady($('mo-modal-box'));
    var first = $('mo-modal-box').querySelector('input, textarea, button');
    if (first) { try { first.focus(); } catch (_) {} }
  }
  function _close() { $('mo-modal').hidden = true; $('mo-modal-box').innerHTML = ''; }
  function _showErr(box, msg) {
    var e = box.querySelector('.mo-err');
    if (e) { e.textContent = msg; e.style.display = 'block'; }
  }

  function _priceAdvice() {
    return '<div class="mo-advice">Prix libre, entre ' + PRIX_MIN + ' et ' + PRIX_MAX + ' Smyles. Prix conseillés :' +
      '<ul><li><b>15</b> pour une recette (≈ 1 €)</li>' +
      '<li><b>30</b> pour une Œuvre son + image (≈ 2 €)</li>' +
      '<li><b>45 et plus</b> pour une édition rare (≈ 3 €)</li></ul>' +
      'Les prix montent avec la rareté et le travail de création.' +
      '<div class="mo-chips"><button type="button" class="mo-chip" data-chip="15">15</button>' +
      '<button type="button" class="mo-chip" data-chip="30">30</button>' +
      '<button type="button" class="mo-chip" data-chip="45">45</button></div></div>';
  }
  function _wireChips(box, inputId) {
    box.querySelectorAll('[data-chip]').forEach(function (c) {
      c.addEventListener('click', function () { box.querySelector('#' + inputId).value = c.getAttribute('data-chip'); });
    });
  }
  function _readPrice(box, id) {
    var raw = (box.querySelector('#' + id).value || '').trim();
    var p = parseInt(raw, 10);
    if (!/^\d+$/.test(raw) || p < PRIX_MIN || p > PRIX_MAX) return null;
    return p;
  }

  function _openPrice() {
    var n = _sel.size;
    _open(
      '<h2 id="mo-modal-title">Changer le prix</h2>' +
      '<p>' + n + ' Œuvre' + (n > 1 ? 's' : '') + ' sélectionnée' + (n > 1 ? 's' : '') + '. ' +
        'Ceux qui ont déjà acheté gardent leur exemplaire.</p>' +
      '<label class="mo-field" for="mo-price">Nouveau prix (en Smyles)' +
        '<input class="mo-input" id="mo-price" type="number" inputmode="numeric" min="' + PRIX_MIN + '" max="' + PRIX_MAX + '" step="1" value="15" /></label>' +
      _priceAdvice() +
      '<div class="mo-field">Appliquer à' +
        '<div class="mo-radio">' +
          '<label><input type="radio" name="mo-cible" value="les_deux" checked /> la recette et l\'image</label>' +
          '<label><input type="radio" name="mo-cible" value="recette" /> la recette</label>' +
          '<label><input type="radio" name="mo-cible" value="image" /> l\'image</label>' +
        '</div></div>' +
      '<div class="mo-err"></div>' +
      '<div class="mo-modal-actions"><button type="button" class="mo-btn" data-close>Annuler</button>' +
        '<button type="button" class="mo-btn mo-btn--main" data-ok>Enregistrer le prix</button></div>',
      function (box) {
        _wireChips(box, 'mo-price');
        box.querySelector('[data-ok]').addEventListener('click', function () {
          var p = _readPrice(box, 'mo-price');
          if (p === null) { _showErr(box, 'Le prix doit être un nombre entier entre ' + PRIX_MIN + ' et ' + PRIX_MAX + ' Smyles.'); return; }
          var cible = (box.querySelector('input[name="mo-cible"]:checked') || {}).value || 'les_deux';
          _bulk('prix', { prix: p, cible: cible }, box);
        });
      });
  }

  function _openDelete() {
    var n = _sel.size;
    _open(
      '<h2 id="mo-modal-title">Supprimer ' + (n > 1 ? 'ces ' + n + ' Œuvres' : 'cette Œuvre') + ' ?</h2>' +
      '<p>' + _esc(CONFIRM_SUPPR) + '</p>' +
      '<div class="mo-err"></div>' +
      '<div class="mo-modal-actions"><button type="button" class="mo-btn" data-close>Annuler</button>' +
        '<button type="button" class="mo-btn mo-btn--danger mo-btn--fill" data-ok>Supprimer</button></div>',
      function (box) {
        box.querySelector('[data-ok]').addEventListener('click', function () { _bulk('supprimer', {}, box); });
      });
  }

  var MESSAGES = {
    masquer: function (n) { return n + ' Œuvre' + (n > 1 ? 's masquées' : ' masquée') + '. Tes acheteurs y gardent accès.'; },
    republier: function (n) { return n + ' Œuvre' + (n > 1 ? 's republiées' : ' republiée') + '.'; },
    prix: function (n) { return 'Prix mis à jour sur ' + n + ' Œuvre' + (n > 1 ? 's' : '') + '.'; },
    supprimer: function (n) { return n + ' Œuvre' + (n > 1 ? 's supprimées' : ' supprimée') + '. Ceux qui l\'ont achetée la gardent.'; },
  };

  function _bulk(action, extra, box) {
    var ids = Array.from(_sel);
    if (!ids.length) return;
    var btn = box && box.querySelector('[data-ok]');
    if (btn) btn.disabled = true;
    document.querySelectorAll('[data-bulk]').forEach(function (b) { b.disabled = true; });
    var body = Object.assign({ track_ids: ids, action: action }, extra || {});
    window.apiFetch('/artist/me/oeuvres/actions', { method: 'POST', json: body })
      .then(function (r) {
        _close();
        var faits = (r && r.faits) ? r.faits.length : 0;
        var msg = MESSAGES[action](faits);
        if (r && r.ignores && r.ignores.length) {
          msg += ' ' + r.ignores.length + ' non modifiée' + (r.ignores.length > 1 ? 's' : '') +
            (action === 'prix' ? ' (rien en vente de ce côté).' : ' (retirée par la modération).');
        }
        _toast(msg);
        if (action === 'supprimer') _sel.clear();
        return load();
      })
      .catch(function (e) {
        if (btn) btn.disabled = false;
        var m = _errMsg(e, 'Action impossible pour le moment. Réessaie.');
        if (box) _showErr(box, m); else _toast(m);
        _syncBar();
      });
  }

  function _openEdit(id) {
    var it = _items.find(function (x) { return x.trackId === id; });
    if (!it) return;
    var src = _thumb(it);
    _open(
      '<h2 id="mo-modal-title">Modifier « ' + _esc(it.title) + ' »</h2>' +
      '<label class="mo-field" for="mo-e-title">Titre<input class="mo-input" id="mo-e-title" maxlength="200" value="' + _esc(it.title) + '" /></label>' +
      (it.recipe || it.image
        ? '<label class="mo-field" for="mo-e-desc">Description<textarea class="mo-input" id="mo-e-desc" maxlength="2000">' +
            _esc(it.recipe ? it.recipe.description : '') + '</textarea></label>'
        : '') +
      '<label class="mo-field" for="mo-e-cover">Image (pochette)' +
        (src ? '<img src="' + _esc(src) + '" alt="" style="display:block;width:72px;height:72px;object-fit:cover;border-radius:10px;margin:8px 0 0" />' : '') +
        '<input class="mo-input" id="mo-e-cover" type="file" accept="image/png,image/jpeg,image/webp" /></label>' +
      (it.recipe ? '<label class="mo-field" for="mo-e-rprice">Prix de la recette (Smyles)<input class="mo-input" id="mo-e-rprice" type="number" inputmode="numeric" min="' +
          PRIX_MIN + '" max="' + PRIX_MAX + '" value="' + _esc(it.recipe.priceCredits) + '" /></label>' : '') +
      (it.image ? '<label class="mo-field" for="mo-e-iprice">Prix de l\'image (Smyles)<input class="mo-input" id="mo-e-iprice" type="number" inputmode="numeric" min="' +
          PRIX_MIN + '" max="' + PRIX_MAX + '" value="' + _esc(it.image.priceCredits) + '" /></label>' : '') +
      (it.recipe || it.image ? _priceAdvice() : '') +
      '<div class="mo-err"></div>' +
      '<div class="mo-modal-actions"><button type="button" class="mo-btn" data-close>Annuler</button>' +
        '<button type="button" class="mo-btn mo-btn--main" data-ok>Enregistrer</button></div>',
      function (box) {
        if (box.querySelector('#mo-e-rprice')) _wireChips(box, 'mo-e-rprice');
        box.querySelector('[data-ok]').addEventListener('click', function () { _saveEdit(it, box); });
      });
  }

  function _saveEdit(it, box) {
    var body = {};
    var title = (box.querySelector('#mo-e-title').value || '').trim();
    if (title.length < 5) { _showErr(box, 'Le titre doit faire au moins 5 caractères.'); return; }
    if (title !== it.title) body.title = title;
    var desc = box.querySelector('#mo-e-desc');
    if (desc && desc.value.trim() !== ((it.recipe && it.recipe.description) || '')) body.description = desc.value.trim();
    if (box.querySelector('#mo-e-rprice')) {
      var rp = _readPrice(box, 'mo-e-rprice');
      if (rp === null) { _showErr(box, 'Prix de la recette : entre ' + PRIX_MIN + ' et ' + PRIX_MAX + ' Smyles.'); return; }
      if (rp !== it.recipe.priceCredits) body.recipe_price = rp;
    }
    if (box.querySelector('#mo-e-iprice')) {
      var ip = _readPrice(box, 'mo-e-iprice');
      if (ip === null) { _showErr(box, 'Prix de l\'image : entre ' + PRIX_MIN + ' et ' + PRIX_MAX + ' Smyles.'); return; }
      if (ip !== it.image.priceCredits) body.image_price = ip;
    }
    var btn = box.querySelector('[data-ok]');
    btn.disabled = true;
    var file = box.querySelector('#mo-e-cover').files[0];
    var step = Promise.resolve();
    if (file) {
      if (file.size > 5 * 1024 * 1024) { btn.disabled = false; _showErr(box, 'Image trop lourde : 5 Mo au maximum.'); return; }
      var fd = new FormData();
      fd.append('file', file);
      fd.append('kind', 'track-cover');
      step = window.apiFetch('/watt/upload-image', { method: 'POST', body: fd, timeoutMs: 30000 })
        .then(function (r) {
          if (!r || !r.url) throw new Error('upload');
          body.cover_url = r.url;
        });
    }
    step.then(function () {
      if (!Object.keys(body).length) { _close(); return null; }
      return window.apiFetch('/artist/me/oeuvres/' + encodeURIComponent(it.trackId), { method: 'PATCH', json: body })
        .then(function () { _close(); _toast('Œuvre mise à jour.'); return load(); });
    }).catch(function (e) {
      btn.disabled = false;
      _showErr(box, _errMsg(e, 'Enregistrement impossible pour le moment. Réessaie.'));
    });
  }

  // ── Événements ───────────────────────────────────────────────────────────
  function _wire() {
    $('mo-list').addEventListener('change', function (ev) {
      var id = ev.target.getAttribute && ev.target.getAttribute('data-check');
      if (!id) return;
      if (ev.target.checked) _sel.add(id); else _sel.delete(id);
      var row = ev.target.closest('.mo-row');
      if (row) row.classList.toggle('is-selected', ev.target.checked);
      _syncBar();
    });
    $('mo-list').addEventListener('click', function (ev) {
      var p = ev.target.closest('[data-play]');
      if (p) { _play(p.getAttribute('data-play')); return; }
      var e = ev.target.closest('[data-edit]');
      if (e) { _openEdit(e.getAttribute('data-edit')); }
    });
    $('mo-all').addEventListener('change', function (ev) {
      _sel = ev.target.checked ? new Set(_items.map(function (i) { return i.trackId; })) : new Set();
      render();
    });
    document.querySelectorAll('[data-bulk]').forEach(function (b) {
      b.addEventListener('click', function () {
        var a = b.getAttribute('data-bulk');
        if (a === 'prix') _openPrice();
        else if (a === 'supprimer') _openDelete();
        else _bulk(a, {}, null);
      });
    });
    $('mo-modal').addEventListener('click', function (ev) {
      if (ev.target === $('mo-modal') || ev.target.closest('[data-close]')) _close();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && !$('mo-modal').hidden) _close();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Page réservée aux comptes : un visiteur passe par l'inscription et
    // revient ici ensuite.
    if (typeof window.getAuthToken !== 'function' || !window.getAuthToken()) {
      if (window.SmyleGate) window.SmyleGate.openSignup({ tab: 'signup', returnTo: '/mes-oeuvres' });
      else window.location.href = '/?auth=signup&return=%2Fmes-oeuvres';
      return;
    }
    _wire();
    load();
  });
})();
