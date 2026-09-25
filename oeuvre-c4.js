/* ═════════════════════════════════════════════════════════════════════════
   oeuvre-c4.js — Page ŒUVRE (1 son + 1 image) · /o/<id>   (Lot 2, 23/09)
   ─────────────────────────────────────────────────────────────────────────
   L'Œuvre est LA fonctionnalité centrale : un son et une image réunis.
   Cette page est le lien que le créateur partage (aperçu social injecté par
   le serveur). Elle monte :
     • l'image (aperçu, jamais l'original) ;
     • le lecteur audio du son ;
     • les deux moitiés, chacune achetable SÉPARÉMENT (drawer unifié) — la
       moitié son n'est achetable que si le morceau a une recette ;
     • un lien vers le profil du créateur ;
     • « Acheter l'Œuvre » (#o-bundle, Lot 3) : son + image − 10 %, en un
       seul achat (POST /watt/oeuvres/<id>/acheter). Si une moitié est déjà
       possédée, le bouton complète l'Œuvre au prix plein de l'autre.

   API : GET /watt/oeuvres/<id> (public, aperçu anti-fuite).
   ═════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  // Échappeur complet (& < > " ' `) — copie de ui/albums.js.
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }

  function _toast(msg, type) {
    try { if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' }); } catch (_) {}
  }

  function _id() {
    var m = window.location.pathname.match(/^\/o\/([0-9a-fA-F-]{36})\/?$/);
    return m ? m[1] : null;
  }
  var OID = _id();

  function _previewUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  function _show(id) {
    ['o-loading', 'o-empty', 'o-content'].forEach(function (x) {
      var n = document.getElementById(x);
      if (n) n.style.display = (x === id) ? '' : 'none';
    });
  }

  var _data = null;

  function _buy(kind) {
    if (!_data) return;
    if (!window.PurchaseDrawer || typeof window.PurchaseDrawer.open !== 'function') {
      _toast('Module d\'achat indisponible — recharge la page.', 'error');
      return;
    }
    var half = kind === 'image'
      ? { type: 'image', id: _data.image.id, price: _data.image.priceCredits, title: _data.image.title }
      : { type: 'son', id: _data.sound.recipe.id, price: _data.sound.recipe.priceCredits, title: _data.sound.title };
    window.PurchaseDrawer.open({
      type: half.type, id: half.id, price: half.price, title: half.title,
      onSuccess: function () { _toast('Débloqué — retrouve-le dans ta bibliothèque.', 'success'); },
    });
  }

  function _buyBundle(btn) {
    var token = (typeof window.getAuthToken === 'function') ? window.getAuthToken() : null;
    if (!token) {
      if (typeof window.openAuthModal === 'function') window.openAuthModal('login');
      else _toast('Connecte-toi pour acheter cette œuvre.', 'info');
      return;
    }
    if (!_data || !_data.bundle) return;
    var prix = _data.bundle.priceCredits;
    if (!window.confirm('Acheter cette œuvre pour ' + prix + ' Smyles ?')) return;
    btn.disabled = true;
    window.apiFetch('/watt/oeuvres/' + encodeURIComponent(OID) + '/acheter', { method: 'POST' })
      .then(function () {
        _toast('Œuvre débloquée — le son et l\'image sont dans ta bibliothèque.', 'success');
        try { if (window.SmyleBalance && window.SmyleBalance.refresh) window.SmyleBalance.refresh(); } catch (_) {}
        load();
      })
      .catch(function (err) {
        btn.disabled = false;
        var s = err && err.status;
        if (s === 402) _toast('Pas assez de Smyles pour cette œuvre.', 'error');
        else if (s === 409) _toast((err.body && typeof err.body.detail === 'string') ? err.body.detail : 'Tu possèdes déjà cette œuvre.', 'info');
        else _toast('Achat impossible pour le moment. Réessaie.', 'error');
      });
  }

  function _render(d) {
    _data = d;
    var creator = d.creator || {};
    var title = d.title || 'Œuvre';
    document.title = title + ' · WATT';
    document.getElementById('o-title').textContent = title;

    var by = document.getElementById('o-by');
    if (creator.slug) {
      by.innerHTML = 'par <a href="/u/' + encodeURIComponent(creator.slug) + '">' +
        _esc(creator.name || creator.slug) + '</a>';
    } else {
      by.textContent = creator.name ? ('par ' + creator.name) : '';
    }

    var img = d.image || {};
    var url = _previewUrl(img.previewKey);
    document.getElementById('o-visual').innerHTML = url
      ? '<img src="' + _esc(url) + '" alt="' + _esc(img.title || title) + '" />'
      : '<span class="o-visual-ph" aria-hidden="true">🖼</span>';

    var snd = d.sound || {};
    var player = document.getElementById('o-player');
    player.innerHTML = snd.streamUrl
      ? '<p class="o-player-label">Écouter le son</p>' +
        '<audio controls preload="none" src="' + _esc(snd.streamUrl) + '"></audio>'
      : '<p class="o-player-empty">L\'écoute de ce son n\'est pas disponible pour le moment.</p>';

    // Moitié SON
    var sonThumb = snd.coverUrl
      ? '<img src="' + _esc(snd.coverUrl) + '" alt="" />'
      : '<span aria-hidden="true">🎵</span>';
    var sonAction = snd.recipe
      ? '<button type="button" class="o-btn" data-o-buy="son">Débloquer · ' +
        _esc(snd.recipe.priceCredits) + ' Smyles</button>'
      : '';
    document.getElementById('o-half-son').innerHTML =
      '<div class="o-half-thumb">' + sonThumb + '</div>' +
      '<div class="o-half-body"><p class="o-half-kind o-half-kind--son">Le son</p>' +
      '<p class="o-half-title">' + _esc(snd.title || title) + '</p>' +
      '<p class="o-half-note">' + (snd.recipe ? 'Recette + fichier' : 'En écoute libre') + '</p></div>' +
      sonAction;

    // Moitié IMAGE
    document.getElementById('o-half-image').innerHTML =
      '<div class="o-half-thumb">' + (url ? '<img src="' + _esc(url) + '" alt="" />' : '<span aria-hidden="true">🖼</span>') + '</div>' +
      '<div class="o-half-body"><p class="o-half-kind o-half-kind--image">L\'image</p>' +
      '<p class="o-half-title">' + _esc(img.title || title) + '</p>' +
      '<p class="o-half-note">Recette + image originale</p></div>' +
      (img.priceCredits != null
        ? '<button type="button" class="o-btn" data-o-buy="image">Débloquer · ' + _esc(img.priceCredits) + ' Smyles</button>'
        : '');

    // Achat de l'Œuvre entière (Lot 3) : son + image − 10 %.
    var bundle = document.getElementById('o-bundle');
    var b = d.bundle;
    if (b && b.mode === 'possedee') {
      bundle.hidden = false;
      bundle.innerHTML = '<p class="o-bundle-note">Tu possèdes cette œuvre — retrouve-la dans ta bibliothèque.</p>';
    } else if (b && b.priceCredits != null) {
      var label = b.mode === 'moitie_manquante'
        ? 'Compléter l\'œuvre · ' + _esc(b.priceCredits) + ' Smyles'
        : 'Acheter l\'œuvre · ' + _esc(b.priceCredits) + ' Smyles';
      var detail = (b.mode === 'oeuvre' && b.fullPriceCredits != null)
        ? '<p class="o-bundle-note">Le son et l\'image ensemble : <s>' + _esc(b.fullPriceCredits) +
          '</s> ' + _esc(b.priceCredits) + ' Smyles (−' + _esc(b.discountPct) + ' %).</p>'
        : '<p class="o-bundle-note">Tu as déjà une moitié : l\'autre est au prix normal.</p>';
      bundle.hidden = false;
      bundle.innerHTML = '<button type="button" class="o-btn o-btn--bundle" data-o-buy="bundle">' + label + '</button>' + detail;
    } else {
      bundle.hidden = true;
      bundle.innerHTML = '';
    }
    _show('o-content');
  }

  function _wire() {
    document.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-o-buy]');
      if (b) {
        var k = b.getAttribute('data-o-buy');
        if (k === 'son' || k === 'image') _buy(k);
        if (k === 'bundle') _buyBundle(b);
        return;
      }
      if (ev.target.closest('#o-report')) {
        if (window.ReportModal && _data) window.ReportModal.open({ targetType: 'image', targetId: _data.image.id });
        return;
      }
      if (ev.target.closest('#o-share')) {
        var link = window.location.origin + '/o/' + (OID || '');
        var done = function () { _toast('Lien copié — colle-le où tu veux.', 'success'); };
        try {
          if (navigator.share) {
            navigator.share({ title: document.title, url: link }).catch(function () {});
            return;
          }
          navigator.clipboard.writeText(link).then(done, function () { window.prompt('Copie ce lien :', link); });
        } catch (_) { window.prompt('Copie ce lien :', link); }
        try { if (window.SmyleTrack) window.SmyleTrack.event('share_click', { oeuvre: OID }); } catch (_) {}
      }
    });
  }

  function load() {
    if (!OID || !window.apiFetch) { _show('o-empty'); return; }
    // Jeton joint s'il existe : le prix de l'Œuvre est calculé pour l'acheteur.
    window.apiFetch('/watt/oeuvres/' + encodeURIComponent(OID))
      .then(function (d) {
        if (!d || !d.image) { _show('o-empty'); return; }
        _render(d);
      })
      .catch(function (err) {
        _show('o-empty');
        var s = err && err.status;
        if (s && s !== 404) _toast('Chargement impossible pour le moment — réessaie.', 'error');
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    _wire();
    load();
  });
})();
