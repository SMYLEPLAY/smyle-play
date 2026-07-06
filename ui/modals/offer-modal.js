/* ═══════════════════════════════════════════════════════════════════════════
   OFFRES-ADN étape 3 (2026-07-03) — MODAL « FAIRE UNE OFFRE » · window.AdnOfferModal
   ─────────────────────────────────────────────────────────────────────────
   UN seul composant pour proposer un montant en Smyles sur n'importe quel
   ADN (les ADN ne s'achètent plus en direct — doctrine vente sur proposition).

   Usage :
     AdnOfferModal.open({
       targetType: 'playlist_adn' | 'album_adn' | 'visual_adn' | 'profile_adn',
       targetId:   '<uuid de l ADN cible>',
       title:      'Nom affiché',            // optionnel
       artistName: 'Nom artiste',            // optionnel
       onSuccess:  (offer) => {},            // optionnel
     });

   Dépendances souples : window.apiFetch (Bearer), window.smyleToast /
   showToast, window.openAuthModal. Auto-injecte son CSS (ao-*).
   Anti-lowball : « offre libre » — le plancher caché de l'artiste n'est
   JAMAIS affiché ; s'il existe et que l'offre est en dessous, le backend
   répond 422 avec un message générique.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var TYPE_LABELS = {
    'playlist_adn': '🎚 ADN de playlist',
    'album_adn':    '🎨 ADN d’album',
    'visual_adn':   '🎨 ADN visuel d’artiste',
    'profile_adn':  '🧬 ADN d’artiste',
  };

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _toast(msg, type) {
    if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' });
    if (window.showToast) return window.showToast(msg);
  }

  var _cssDone = false;
  function _injectCss() {
    if (_cssDone) return;
    _cssDone = true;
    var st = document.createElement('style');
    st.textContent = [
      '#ao-overlay{position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:16px}',
      '.ao-modal{background:#15151c;border:1px solid rgba(255,255,255,.12);border-radius:14px;max-width:420px;width:100%;padding:20px;color:#eee;font-size:14px}',
      '.ao-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}',
      '.ao-close{background:none;border:none;color:#aaa;font-size:18px;cursor:pointer;line-height:1}',
      '.ao-kicker{font-size:12px;color:#a09cb8;margin:0 0 2px}',
      '.ao-title{font-size:16px;font-weight:700;margin:0 0 12px}',
      '.ao-info{font-size:12.5px;color:#a09cb8;line-height:1.55;border:1px dashed rgba(204,136,255,.3);border-radius:10px;padding:9px 11px;margin-bottom:14px}',
      '.ao-lbl{display:block;font-size:11.5px;font-weight:600;color:#bdb6d6;margin:10px 0 4px}',
      '.ao-input,.ao-msg{width:100%;box-sizing:border-box;background:#0e0e14;border:1px solid rgba(255,255,255,.14);border-radius:9px;color:#eee;padding:10px 12px;font-size:14px;font-family:inherit}',
      '.ao-input:focus,.ao-msg:focus{outline:none;border-color:rgba(204,136,255,.55)}',
      '.ao-msg{min-height:70px;resize:vertical}',
      '.ao-suffix{font-size:12px;color:#a09cb8;margin-top:3px}',
      '.ao-err{display:none;margin-top:10px;font-size:12.5px;color:#ff6b6b;line-height:1.4}',
      '.ao-submit{width:100%;margin-top:14px;padding:12px;border:none;border-radius:10px;background:linear-gradient(135deg,#7C3AED,#cc88ff);color:#fff;font-weight:700;font-size:14px;cursor:pointer}',
      '.ao-submit[disabled]{opacity:.55;cursor:not-allowed}',
    ].join('\n');
    document.head.appendChild(st);
  }

  function close() {
    var el = document.getElementById('ao-overlay');
    if (el) el.remove();
  }

  function open(opts) {
    opts = opts || {};
    var targetType = TYPE_LABELS[opts.targetType] ? opts.targetType : null;
    var targetId = opts.targetId;
    if (!targetType || !targetId) return;
    if (document.getElementById('ao-overlay')) return;

    // Non connecté → modal d'auth si dispo (le POST renverrait 401 de toute façon).
    var token = (typeof window.getAuthToken === 'function') ? window.getAuthToken() : null;
    if (!token && typeof window.openAuthModal === 'function') {
      window.openAuthModal();
      return;
    }

    _injectCss();

    var overlay = document.createElement('div');
    overlay.id = 'ao-overlay';
    overlay.innerHTML =
      '<div class="ao-modal" role="dialog" aria-modal="true">' +
        '<div class="ao-hdr">' +
          '<p class="ao-kicker">' + _esc(TYPE_LABELS[targetType]) +
            (opts.artistName ? ' · ' + _esc(opts.artistName) : '') + '</p>' +
          '<button class="ao-close" id="ao-close" aria-label="Fermer">✕</button>' +
        '</div>' +
        '<h3 class="ao-title">🤝 Faire une offre' +
          (opts.title ? ' — ' + _esc(opts.title) : '') + '</h3>' +
        '<div class="ao-info">Offre libre : propose le montant que tu veux en Smyles. ' +
          'L’artiste reçoit ta proposition et l’accepte ou la refuse. ' +
          'Tes Smyles ne sont débités QUE si l’artiste accepte.</div>' +
        '<label class="ao-lbl" for="ao-amount">Ton offre</label>' +
        '<input class="ao-input" id="ao-amount" type="number" min="1" step="1" ' +
          'inputmode="numeric" placeholder="Montant en Smyles" />' +
        '<label class="ao-lbl" for="ao-message">Message (optionnel)</label>' +
        '<textarea class="ao-msg" id="ao-message" maxlength="500" ' +
          'placeholder="Un mot pour l’artiste…"></textarea>' +
        '<div class="ao-err" id="ao-err"></div>' +
        '<button class="ao-submit" id="ao-submit">Envoyer mon offre</button>' +
      '</div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.getElementById('ao-close').addEventListener('click', close);

    var submitBtn = document.getElementById('ao-submit');
    submitBtn.addEventListener('click', async function () {
      var errEl = document.getElementById('ao-err');
      errEl.style.display = 'none';
      var amount = parseInt(document.getElementById('ao-amount').value, 10);
      if (!amount || amount < 1) {
        errEl.textContent = 'Indique un montant en Smyles (minimum 1).';
        errEl.style.display = 'block';
        return;
      }
      var message = (document.getElementById('ao-message').value || '').trim() || null;

      submitBtn.disabled = true;
      submitBtn.textContent = 'Envoi…';
      try {
        var offer = await window.apiFetch('/adn-offers', {
          method: 'POST',
          json: {
            target_type: targetType,
            target_id:   String(targetId),
            amount_credits: amount,
            message: message,
          },
        });
        close();
        _toast('🤝 Offre envoyée — tu seras notifié de la réponse de l’artiste.', 'success');
        if (typeof opts.onSuccess === 'function') { try { opts.onSuccess(offer); } catch (_) {} }
      } catch (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Envoyer mon offre';
        var st = err && err.status;
        var detail = (err && err.body && err.body.detail);
        var msg;
        if (st === 401) {
          msg = 'Connecte-toi pour faire une offre.';
          if (typeof window.openAuthModal === 'function') { close(); window.openAuthModal(); return; }
        } else if (st === 402) {
          msg = 'Tu n’as pas assez de Smyles pour couvrir cette offre.';
        } else if (st === 422) {
          msg = (typeof detail === 'string') ? detail
              : 'Offre refusée automatiquement — propose un montant plus élevé.';
        } else if (st === 409) {
          msg = (typeof detail === 'string') ? detail
              : 'Tu as déjà une offre en attente sur cet ADN.';
        } else if (st === 404 || st === 410) {
          msg = 'Cet ADN n’est plus proposé à la vente.';
        } else {
          msg = (typeof detail === 'string') ? detail : 'Erreur lors de l’envoi de l’offre.';
        }
        errEl.textContent = msg;
        errEl.style.display = 'block';
      }
    });

    setTimeout(function () {
      var inp = document.getElementById('ao-amount');
      if (inp) inp.focus();
    }, 50);
  }

  window.AdnOfferModal = { open: open, close: close };
})();
