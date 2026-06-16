/* ═══════════════════════════════════════════════════════════════════════════
   C2 (2026-06-12) — DRAWER D'ACHAT UNIFIÉ · window.PurchaseDrawer
   ─────────────────────────────────────────────────────────────────────────
   UN seul composant d'achat pour toute la plateforme : récap produit,
   3 repères (écoute libre · achat = fichier + recette · provenance IA),
   marché primaire/secondaire (sons), confirmation, erreurs humanisées.

   Usage :
     PurchaseDrawer.open({
       type:  'son' | 'adn-artist' | 'voix' | 'playlist',
       id:    '<uuid produit>',
       title: 'Nom affiché',
       price: 120,                    // Smyles (affichage)
       artistName: 'Nom artiste',     // optionnel
       platform:   'suno',            // optionnel (provenance)
       onSuccess:  (resp) => {},      // optionnel
     });

   Dépendances souples : window.apiFetch (Bearer), window.showToast /
   smyleToast, window.openAuthModal. Tout est optionnel → dégradation propre.
   Auto-injecte son CSS (pd-*) : fonctionne sur toutes les pages.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var ENDPOINTS = {
    'son':        '/unlocks/prompts/',
    // C4 ③ — une image est une ligne `prompts` (product_type='image') : achat
    // via le MÊME endpoint d'unlock prompt (mint #X/N inclus). On distingue
    // juste le type pour adapter les repères/toasts.
    'image':      '/unlocks/prompts/',
    'adn-artist': '/unlocks/adns/',
    'voix':       '/unlocks/voices/',
    'playlist':   '/unlocks/playlist-adn/',
  };
  var TYPE_LABELS = {
    'son':        '🧬 Recette + fichier',
    'image':      '🖼️ Recette + image originale',
    'adn-artist': '🧬 ADN d’artiste',
    'voix':       '🎙 Voix',
    'playlist':   '🎚 ADN de playlist',
  };
  var SUCCESS_TOASTS = {
    'son':        'Exemplaire débloqué 🔓 — fichier + recette dans ta bibliothèque',
    'image':      'Image débloquée 🔓 — recette + original dans ta bibliothèque',
    'adn-artist': 'ADN débloqué 🧬 — retrouve-le dans ta bibliothèque',
    'voix':       'Voix débloquée 🎙 — retrouve-la dans ta bibliothèque',
    'playlist':   'ADN Playlist débloqué 🎚 — retrouve-le dans ta bibliothèque',
  };
  var PLATFORM_LABELS = { suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion', stable_audio: 'Stable Audio', midjourney: 'Midjourney', dalle: 'DALL·E', flux: 'Flux', stable_diffusion: 'Stable Diffusion', autre: 'Autre' };

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _toast(msg, type) {
    if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' });
    if (window.showToast) return window.showToast(msg);
  }

  /* C4 Œuvre complète — bloc « produit lié » (achat séparé). Sur un drawer
     IMAGE : montre le SON lié (opts.linkedSound). Sur un drawer SON : montre
     l'IMAGE liée (opts.linkedImage). Ne révèle QUE titre/aperçu/prix : aucune
     recette. Le bouton réouvre le drawer du partenaire (achat indépendant). */
  function _linkedBlockHtml(type, opts) {
    var ls = opts.linkedSound, li = opts.linkedImage;
    if (type === 'image' && ls && ls.id) {
      var cover = ls.coverUrl
        ? '<img class="pd-linked-thumb" src="' + _esc(ls.coverUrl) + '" alt="" />'
        : '<span class="pd-linked-thumb pd-linked-thumb--ph">🎵</span>';
      return '<div class="pd-linked" data-link-kind="son" data-link-id="' + _esc(ls.id) + '">' +
        cover +
        '<div class="pd-linked-meta"><span class="pd-linked-kicker">🎵 Son lié · œuvre complète</span>' +
        '<span class="pd-linked-title">' + _esc(ls.title || 'Son lié') + '</span>' +
        (ls.priceCredits != null ? '<span class="pd-linked-price">' + _esc(ls.priceCredits) + ' Smyles</span>' : '') +
        '</div><button type="button" class="pd-linked-go">Écouter / voir</button></div>';
    }
    if (type === 'son' && li && li.id) {
      var prev = li.previewKey
        ? '<img class="pd-linked-thumb" src="/watt/images/' + _esc(li.previewKey) + '" alt="" />'
        : '<span class="pd-linked-thumb pd-linked-thumb--ph">🖼</span>';
      return '<div class="pd-linked" data-link-kind="image" data-link-id="' + _esc(li.id) + '">' +
        prev +
        '<div class="pd-linked-meta"><span class="pd-linked-kicker">🖼 Visuel lié · œuvre complète</span>' +
        '<span class="pd-linked-title">Image liée</span>' +
        (li.priceCredits != null ? '<span class="pd-linked-price">' + _esc(li.priceCredits) + ' Smyles</span>' : '') +
        '</div><button type="button" class="pd-linked-go">Voir l\'image</button></div>';
    }
    return '';
  }

  function _injectCss() {
    if (document.getElementById('pd-styles')) return;
    var s = document.createElement('style');
    s.id = 'pd-styles';
    s.textContent =
      '.pd-overlay{position:fixed;inset:0;background:rgba(8,6,18,.72);backdrop-filter:blur(3px);z-index:1300;display:flex;align-items:flex-end;justify-content:center;animation:pdFade .18s ease}' +
      '@media(min-width:640px){.pd-overlay{align-items:center}}' +
      '@keyframes pdFade{from{opacity:0}to{opacity:1}}' +
      '.pd-box{width:100%;max-width:430px;background:#16121f;border:1px solid rgba(124,92,255,.28);border-radius:18px 18px 0 0;padding:22px 22px 18px;position:relative;animation:pdUp .22s ease;box-shadow:0 -8px 48px rgba(0,0,0,.5)}' +
      '@media(min-width:640px){.pd-box{border-radius:18px}}' +
      '@keyframes pdUp{from{transform:translateY(24px);opacity:0}to{transform:translateY(0);opacity:1}}' +
      '.pd-close{position:absolute;top:10px;right:14px;background:none;border:none;color:#a09cb8;font-size:22px;cursor:pointer;line-height:1}' +
      '.pd-kicker{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#8b7bd8;margin:0 0 4px}' +
      '.pd-title{margin:0 0 2px;font-size:1.12rem;color:#f3f0ff;font-weight:700}' +
      '.pd-artist{margin:0 0 12px;font-size:.82rem;color:#a09cb8}' +
      '.pd-reperes{list-style:none;margin:0 0 12px;padding:10px 12px;border:1px solid rgba(255,255,255,.07);border-radius:12px;background:rgba(255,255,255,.025);display:flex;flex-direction:column;gap:6px}' +
      '.pd-reperes li{font-size:.8rem;color:#cfc9e0;display:flex;gap:7px;align-items:baseline}' +
      '.pd-market{font-size:.78rem;color:#a79fc0;line-height:1.6;margin:0 0 12px;min-height:0}' +
      '.pd-price-row{display:flex;align-items:baseline;gap:6px;margin:0 0 14px}' +
      '.pd-price{font-size:1.7rem;font-weight:800;color:#cbb3ff}' +
      '.pd-price-unit{font-size:.85rem;color:#8b7bd8;font-weight:600}' +
      '.pd-actions{display:flex;gap:10px}' +
      '.pd-cancel{flex:0 0 auto;padding:11px 16px;border-radius:11px;border:1px solid rgba(255,255,255,.14);background:none;color:#cfc9e0;font-weight:600;cursor:pointer}' +
      '.pd-confirm{flex:1;padding:11px 16px;border-radius:11px;border:none;background:linear-gradient(135deg,#7c5cff,#9d4dff);color:#fff;font-weight:700;cursor:pointer;font-size:.95rem}' +
      '.pd-confirm:disabled{opacity:.55;cursor:default}' +
      '.pd-note{margin:10px 0 0;font-size:.72rem;color:#7d7794;text-align:center}' +
      /* C4 Œuvre complète — bloc produit lié (bleu électrique WATT). */
      '.pd-linked{display:flex;align-items:center;gap:10px;margin:0 0 12px;padding:8px 10px;border:1px solid rgba(0,85,255,.4);border-radius:12px;background:rgba(0,85,255,.08);cursor:pointer}' +
      '.pd-linked:hover{background:rgba(0,85,255,.14)}' +
      '.pd-linked-thumb{width:42px;height:42px;border-radius:8px;object-fit:cover;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.06);font-size:18px}' +
      '.pd-linked-meta{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}' +
      '.pd-linked-kicker{font-size:.66rem;font-weight:700;letter-spacing:.04em;color:#6da4ff;text-transform:uppercase}' +
      '.pd-linked-title{font-size:.84rem;color:#f3f0ff;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.pd-linked-price{font-size:.72rem;color:#a09cb8}' +
      '.pd-linked-go{flex:0 0 auto;padding:6px 10px;border-radius:9px;border:1px solid rgba(0,85,255,.5);background:none;color:#9dc0ff;font-size:.74rem;font-weight:600;cursor:pointer}';
    document.head.appendChild(s);
  }

  function close() {
    var ov = document.getElementById('pd-overlay');
    if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
    document.removeEventListener('keydown', _onEsc);
  }

  function _onEsc(e) { if (e.key === 'Escape') close(); }

  function open(opts) {
    opts = opts || {};
    var type  = ENDPOINTS[opts.type] ? opts.type : 'son';
    var id    = opts.id;
    if (!id) return;
    if (document.getElementById('pd-overlay')) return;
    _injectCss();

    var price  = (opts.price != null && isFinite(opts.price)) ? opts.price : null;
    var title  = opts.title || 'Cet exemplaire';
    var platformKey = (opts.platform || '').trim().toLowerCase();
    var platformLbl = PLATFORM_LABELS[platformKey] || (platformKey || null);

    var reperes;
    if (type === 'image') {
      // C4 ③ — repères image : aperçu public, achat = recette + original,
      // provenance, + règle d'honnêteté (résultats similaires, jamais identiques).
      reperes =
        '<li>👁️ <span>L’aperçu reste <strong>public pour tout le monde</strong> — tu achètes la possession, pas la vue.</span></li>' +
        '<li>🔓 <span>Achat = <strong>recette (prompt + réglages) + image originale</strong>, téléchargeable depuis ta bibliothèque.</span></li>' +
        '<li>⚡ <span>Provenance déclarée' + (platformLbl ? ' : <strong>' + _esc(platformLbl) + '</strong>' : ' (IA nommée sur la fiche)') + '.</span></li>' +
        '<li>♻️ <span>Honnêteté : une recette donne des <strong>résultats similaires, jamais identiques</strong>.</span></li>';
    } else {
      reperes =
        '<li>🎧 <span>L’écoute reste <strong>libre pour tout le monde</strong> — tu achètes la possession, pas l’accès.</span></li>' +
        (type === 'voix'
          ? '<li>🔓 <span>Achat = <strong>le fichier voix complet</strong> (la preview 30 s devient intégrale).</span></li>'
          : '<li>🔓 <span>Achat = <strong>fichier + recette</strong> — l’exemplaire complet, téléchargeable depuis ta bibliothèque.</span></li>') +
        '<li>⚡ <span>Provenance déclarée' + (platformLbl ? ' : <strong>' + _esc(platformLbl) + '</strong>' : ' (IA nommée sur la fiche)') + '.</span></li>';
    }

    var ov = document.createElement('div');
    ov.id = 'pd-overlay';
    ov.className = 'pd-overlay';
    ov.innerHTML =
      '<div class="pd-box" role="dialog" aria-modal="true" aria-label="Confirmer l’achat">' +
        '<button class="pd-close" aria-label="Fermer">&times;</button>' +
        '<p class="pd-kicker">' + _esc(TYPE_LABELS[type]) + '</p>' +
        '<h3 class="pd-title">' + _esc(title) + '</h3>' +
        (opts.artistName ? '<p class="pd-artist">par ' + _esc(opts.artistName) + '</p>' : '<p class="pd-artist"></p>') +
        '<ul class="pd-reperes">' + reperes + '</ul>' +
        '<div class="pd-market" id="pd-market"></div>' +
        _linkedBlockHtml(type, opts) +
        '<div class="pd-price-row"><span class="pd-price">' + (price != null ? price : '—') + '</span><span class="pd-price-unit">Smyles</span></div>' +
        '<div class="pd-actions">' +
          '<button class="pd-cancel" type="button">Annuler</button>' +
          '<button class="pd-confirm" type="button">Débloquer' + (price != null ? ' · ' + price : '') + ' ⚡</button>' +
        '</div>' +
        '<p class="pd-note">Exemplaire ajouté à ta bibliothèque immédiatement après achat.</p>' +
      '</div>';
    document.body.appendChild(ov);

    ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
    ov.querySelector('.pd-close').addEventListener('click', close);
    ov.querySelector('.pd-cancel').addEventListener('click', close);
    document.addEventListener('keydown', _onEsc);

    // C4 — clic sur le produit lié : ferme ce drawer et ouvre celui du
    // partenaire (achat séparé). Le partenaire est un autre prompt.
    var linkedEl = ov.querySelector('.pd-linked');
    if (linkedEl) {
      linkedEl.addEventListener('click', function () {
        var kind = linkedEl.getAttribute('data-link-kind');
        var lid  = linkedEl.getAttribute('data-link-id');
        if (!lid) return;
        close();
        var partner = (kind === 'son')
          ? (opts.linkedSound || {}) : (opts.linkedImage || {});
        open({
          type:  (kind === 'son') ? 'son' : 'image',
          id:    lid,
          title: partner.title || (kind === 'son' ? 'Son lié' : 'Image liée'),
          price: partner.priceCredits,
        });
      });
    }

    // Marché primaire/secondaire — modèle fiche canonique. Sons ET images
    // (toutes deux des lignes `prompts`, donc /resale/prompt/{id}/market gère
    // l'édition limitée #X/N et les reventes de la même façon).
    if ((type === 'son' || type === 'image') && window.apiFetch) {
      (function () {
        window.apiFetch('/resale/prompt/' + encodeURIComponent(id) + '/market').then(function (m) {
          var el = document.getElementById('pd-market');
          if (!el || !m) return;
          var parts = [];
          if (m.is_limited) {
            if (m.supply_left > 0) parts.push('🎟️ Édition limitée · <strong>' + m.supply_left + '/' + m.max_supply + '</strong> au prix officiel');
            else parts.push('🔴 Édition limitée <strong>épuisée</strong> en primaire');
          } else {
            parts.push('♾️ Édition ouverte');
          }
          if (m.secondary && m.secondary.length) {
            parts.push('♻️ <strong>' + m.secondary.length + '</strong> en revente · à partir de <strong>' + m.secondary_from + ' Smyles</strong>');
          }
          el.innerHTML = parts.join('<br>');
          if (m.is_limited && !(m.supply_left > 0)) {
            var btn = ov.querySelector('.pd-confirm');
            if (btn) {
              btn.disabled = true;
              btn.textContent = (m.secondary && m.secondary.length) ? 'Épuisé · dispo en revente' : 'Épuisé';
            }
          }
        }).catch(function () { /* silencieux */ });
      })();
    }

    ov.querySelector('.pd-confirm').addEventListener('click', function () {
      var btn = ov.querySelector('.pd-confirm');
      btn.disabled = true;
      btn.textContent = 'Déblocage…';
      if (!window.apiFetch) { _toast('Connexion indisponible. Recharge la page.', 'error'); btn.disabled = false; return; }
      window.apiFetch(ENDPOINTS[type] + encodeURIComponent(id), { method: 'POST' }).then(function (resp) {
        close();
        var msg = (resp && resp.perk_applied)
          ? 'Débloqué avec perk ADN −30 % 🔓'
          : SUCCESS_TOASTS[type];
        _toast(msg, 'success');
        // Badge "owned" sur toutes les cards du produit (pattern marketplace).
        try {
          document.querySelectorAll('.mp-recipe-badge[data-prompt-id="' + (window.CSS && CSS.escape ? CSS.escape(String(id)) : String(id)) + '"]').forEach(function (el) {
            el.classList.add('is-owned');
            el.title = 'Débloqué ✓';
          });
        } catch (_) {}
        // Solde topbar — refresh best-effort.
        try { if (window.SmyleBalance && window.SmyleBalance.refresh) window.SmyleBalance.refresh(); } catch (_) {}
        if (typeof opts.onSuccess === 'function') { try { opts.onSuccess(resp); } catch (_) {} }
      }).catch(function (err) {
        btn.disabled = false;
        btn.textContent = 'Débloquer' + (price != null ? ' · ' + price : '') + ' ⚡';
        var status = err && err.status;
        if (status === 401) {
          close();
          _toast('Connecte-toi pour acheter — ta bibliothèque garde tes exemplaires.', 'error');
          try { if (window.openAuthModal) window.openAuthModal(); } catch (_) {}
        } else if (status === 402) {
          var d = err.body && err.body.detail;
          _toast((d && typeof d === 'object')
            ? 'Solde insuffisant — il te faut ' + d.required + ' Smyles, tu en as ' + d.available + '.'
            : 'Solde de Smyles insuffisant.', 'error');
        } else if (status === 409) {
          _toast('Tu possèdes déjà cet exemplaire — il est dans ta bibliothèque.', 'info');
        } else {
          var dd = err && err.body && err.body.detail;
          _toast(typeof dd === 'string' ? dd : 'Achat impossible pour le moment. Réessaie.', 'error');
        }
      });
    });
  }

  window.PurchaseDrawer = { open: open, close: close };
})();
