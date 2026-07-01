/* ═════════════════════════════════════════════════════════════════════════
   oeuvre.js — Page ŒUVRE binaire (C4c)
   ─────────────────────────────────────────────────────────────────────────
   Sert /oeuvre/<slug>. Extrait le slug, appelle l'API JSON
   GET /watt/oeuvre/<slug> (FastAPI), puis monte :
     • en-tête : carte ID scindée (renderOeuvreCard, C4b)
     • colonne SON    : ADN Playlist + recette par track  (drawer 'playlist'/'son')
     • colonne VISUEL : ADN Album + prompt IA par image    (drawer 'album-adn'/'image')
     • centre PACK    : « Œuvre complète −% » (POST buy-complete, C5)
   Tous les achats passent par le drawer unifié (window.PurchaseDrawer).
   ═════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _imgUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  function _toast(msg, type) {
    if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' });
    var el = document.getElementById('oeuvre-toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('is-show');
    setTimeout(function () { el.classList.remove('is-show'); }, 2600);
  }

  function _slug() {
    var m = window.location.pathname.match(/^\/oeuvre\/([^/?#]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  var SLUG = _slug();

  // ── Achat via drawer unifié ; onSuccess → recharge la page (états owned). ──
  function _buy(type, id, price, title) {
    if (!window.PurchaseDrawer || typeof window.PurchaseDrawer.open !== 'function') {
      _toast('Module d\'achat indisponible — recharge la page.', 'error');
      return;
    }
    window.PurchaseDrawer.open({
      type: type, id: id, price: (price != null ? price : null), title: title,
      onSuccess: function () { load(); },
    });
  }

  // ── Pack « œuvre complète » (C5). Tolérant si l'endpoint n'existe pas encore. ──
  function _buyComplete() {
    if (!window.apiFetch) { _toast('Connexion indisponible.', 'error'); return; }
    window.apiFetch('/watt/oeuvre/' + encodeURIComponent(SLUG) + '/buy-complete', { method: 'POST' })
      .then(function () {
        _toast('Œuvre complète débloquée 🎉', 'success');
        try { if (window.SmyleBalance && window.SmyleBalance.refresh) window.SmyleBalance.refresh(); } catch (_) {}
        load();
      })
      .catch(function (err) {
        var s = err && err.status;
        if (s === 401) { _toast('Connecte-toi pour acheter l\'œuvre complète.', 'error'); }
        else if (s === 402) { _toast('Solde de Smyles insuffisant.', 'error'); }
        else if (s === 409) { _toast('Tu possèdes déjà cette œuvre.', 'info'); }
        else { _toast('Le pack « œuvre complète » arrive bientôt.', 'info'); }
      });
  }
  // Exposé pour les onclick inline.
  window.__oeuvreBuyComplete = _buyComplete;

  // ── Rendu : en-tête carte scindée ──────────────────────────────────────
  function _renderHead(data) {
    var son = data.son, visuel = data.visuel;
    var cover = (visuel && visuel.images && visuel.images[0]) ? visuel.images[0].previewKey : null;
    var card = (typeof window.renderOeuvreCard === 'function')
      ? window.renderOeuvreCard({
          slug: data.oeuvreSlug,
          title: (son && son.title) || (visuel && visuel.title) || 'Œuvre',
          son: son ? { title: son.title, platform: 'suno', color: son.color } : null,
          visuel: visuel ? { title: visuel.title, platform: 'chatgpt', previewKey: cover } : null,
        })
      : '';
    return '<div class="oeuvre-head-card">' + card + '</div>';
  }

  // ── Bloc ADN de collection (réutilisé son & visuel) ────────────────────
  function _adnBlock(opts) {
    // opts: { icon, label, forSale, price, desc, drawerType, id, title }
    if (!opts.forSale || !opts.price) return '';
    return '' +
      '<div class="oeuvre-adn">' +
        '<div class="oeuvre-adn-hdr">' + opts.icon + ' <strong>' + _esc(opts.label) + '</strong>' +
          '<span class="oeuvre-adn-tag">−20% collection</span></div>' +
        (opts.desc ? '<p class="oeuvre-adn-desc">' + _esc(opts.desc) + '</p>' : '') +
        '<button type="button" class="oeuvre-btn oeuvre-btn--adn" ' +
          'data-buy="' + _esc(opts.drawerType) + '" data-id="' + _esc(opts.id) + '" ' +
          'data-price="' + _esc(opts.price) + '" data-title="' + _esc(opts.title) + '">' +
          'Débloquer l\'ADN · ' + _esc(opts.price) + ' ⚡</button>' +
      '</div>';
  }

  // ── Colonne SON ────────────────────────────────────────────────────────
  function _renderSon(son) {
    var el = document.getElementById('oeuvre-col-son');
    if (!son) { el.innerHTML = '<div class="oeuvre-col-empty">🎵 Face son à venir</div>'; return; }
    var rows = (son.tracks || []).map(function (t) {
      var action;
      if (t.owned) {
        action = '<span class="oeuvre-owned">Possédé ✓</span>';
      } else if (t.promptId) {
        action = '<button type="button" class="oeuvre-btn oeuvre-btn--unit" ' +
          'data-buy="son" data-id="' + _esc(t.promptId) + '" data-price="' + _esc(t.price) + '" ' +
          'data-title="' + _esc(t.title) + '">Recette · ' + _esc(t.price) + ' ⚡</button>';
      } else {
        action = '<span class="oeuvre-noprompt">—</span>';
      }
      return '<li class="oeuvre-row"><span class="oeuvre-row-ttl">🎵 ' + _esc(t.title) + '</span>' + action + '</li>';
    }).join('');
    el.innerHTML =
      '<div class="oeuvre-col-hdr"><span class="oeuvre-col-face">SON</span>' +
        '<h2>' + _esc(son.title) + '</h2></div>' +
      _adnBlock({ icon: '🎚', label: 'ADN Playlist', forSale: son.adnForSale, price: son.adnPrice,
                  desc: son.dnaDescription, drawerType: 'playlist', id: son.playlistId,
                  title: 'ADN · ' + son.title }) +
      '<ul class="oeuvre-list">' + (rows || '<li class="oeuvre-col-empty">Aucun son</li>') + '</ul>';
  }

  // ── Colonne VISUEL ─────────────────────────────────────────────────────
  function _renderVisuel(visuel) {
    var el = document.getElementById('oeuvre-col-visuel');
    if (!visuel) { el.innerHTML = '<div class="oeuvre-col-empty">🖼️ Face visuelle à venir</div>'; return; }
    var cards = (visuel.images || []).map(function (im) {
      var url = _imgUrl(im.previewKey);
      var thumb = url ? '<img class="oeuvre-img-thumb" src="' + _esc(url) + '" alt="" loading="lazy"/>'
                      : '<div class="oeuvre-img-thumb is-ph">🖼️</div>';
      var action;
      if (im.owned) {
        action = '<span class="oeuvre-owned">Possédé ✓</span>';
      } else {
        action = '<button type="button" class="oeuvre-btn oeuvre-btn--unit" ' +
          'data-buy="image" data-id="' + _esc(im.imageId) + '" data-price="' + _esc(im.price) + '" ' +
          'data-title="' + _esc(im.title) + '">Prompt IA · ' + _esc(im.price) + ' ⚡</button>';
      }
      return '<li class="oeuvre-img-card">' + thumb +
        '<div class="oeuvre-img-meta"><span class="oeuvre-img-ttl">' + _esc(im.title || 'Image') + '</span>' +
        action + '</div></li>';
    }).join('');
    el.innerHTML =
      '<div class="oeuvre-col-hdr"><span class="oeuvre-col-face">VISUEL</span>' +
        '<h2>' + _esc(visuel.title) + '</h2></div>' +
      _adnBlock({ icon: '🎨', label: 'ADN Album', forSale: visuel.adnForSale, price: visuel.adnPrice,
                  desc: visuel.dnaDescription, drawerType: 'album-adn', id: visuel.albumId,
                  title: 'ADN · ' + visuel.title }) +
      '<ul class="oeuvre-img-grid">' + (cards || '<li class="oeuvre-col-empty">Aucune image</li>') + '</ul>';
  }

  // ── Centre : PACK œuvre complète ───────────────────────────────────────
  function _renderPack(data) {
    var el = document.getElementById('oeuvre-col-pack');
    if (!data.isComplete) {
      el.innerHTML = '<div class="oeuvre-pack oeuvre-pack--half">' +
        '<div class="oeuvre-pack-seal">◇</div>' +
        '<p class="oeuvre-pack-note">L\'œuvre se complète quand les <strong>deux faces</strong> sont publiées.</p>' +
        '</div>';
      return;
    }
    el.innerHTML = '<div class="oeuvre-pack oeuvre-pack--full">' +
      '<div class="oeuvre-pack-seal">◆</div>' +
      '<h3 class="oeuvre-pack-ttl">Œuvre complète</h3>' +
      '<p class="oeuvre-pack-note">Son + Visuel en un seul geste, au tarif groupé.</p>' +
      '<button type="button" class="oeuvre-btn oeuvre-btn--pack" onclick="window.__oeuvreBuyComplete()">' +
        '◆ Débloquer l\'œuvre complète</button>' +
      '</div>';
  }

  // ── Délégation : tous les boutons [data-buy] ouvrent le drawer ─────────
  function _wireBuyButtons() {
    var content = document.getElementById('oeuvre-content');
    if (!content) return;
    content.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('[data-buy]');
      if (!btn) return;
      e.preventDefault();
      var price = parseInt(btn.getAttribute('data-price'), 10);
      _buy(btn.getAttribute('data-buy'), btn.getAttribute('data-id'),
           isFinite(price) ? price : null, btn.getAttribute('data-title') || '');
    });
  }

  // ── Chargement / rendu ─────────────────────────────────────────────────
  function _show(id) {
    ['oeuvre-loading', 'oeuvre-empty', 'oeuvre-content'].forEach(function (x) {
      var n = document.getElementById(x);
      if (n) n.style.display = (x === id) ? '' : 'none';
    });
  }

  function load() {
    if (!SLUG) { _show('oeuvre-empty'); return; }
    if (!window.apiFetch) { _show('oeuvre-empty'); return; }
    window.apiFetch('/watt/oeuvre/' + encodeURIComponent(SLUG))
      .then(function (data) {
        if (!data || (!data.son && !data.visuel)) { _show('oeuvre-empty'); return; }
        document.getElementById('oeuvre-head').innerHTML = _renderHead(data);
        _renderSon(data.son);
        _renderVisuel(data.visuel);
        _renderPack(data);
        _show('oeuvre-content');
      })
      .catch(function () { _show('oeuvre-empty'); });
  }

  document.addEventListener('DOMContentLoaded', function () {
    _wireBuyButtons();
    load();
  });
})();
