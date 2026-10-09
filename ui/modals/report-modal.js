/* ═══════════════════════════════════════════════════════════════════════════
   D3 CONFIANCE (07/07) — MODAL « SIGNALER UN CONTENU » · window.ReportModal
   ─────────────────────────────────────────────────────────────────────────
   Conformité DSA art. 16 : mécanisme de signalement accessible à TOUS
   (connecté ou non), motifs clairs, accusé de réception (toast + email
   best-effort côté backend).

   Usage :
     ReportModal.open({
       targetType: 'track' | 'prompt' | 'image' | 'profil' | 'playlist' | 'album',
       targetId:   '<id de la cible>',
       title:      'Nom affiché',   // optionnel
     });

   Dépendances souples : window.apiFetch (Bearer auto si connecté),
   window.smyleToast / showToast. Auto-injecte son CSS (rm-*).
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  // Lot 2 : ADN, ADN visuels et voix signalables (anti-squat Pionnier).
  var TARGET_TYPES = { track: 1, prompt: 1, image: 1, profil: 1, playlist: 1, album: 1, adn: 1, visual_adn: 1, voix: 1 };
  var REASONS = [
    ['contenu_illegal', 'Contenu illégal'],
    ['contrefacon',     'Contrefaçon / droits d’auteur'],
    ['haine_violence',  'Haine ou violence'],
    ['nudite',          'Nudité / contenu sexuel'],
    ['spam_arnaque',    'Spam ou arnaque'],
    ['autre',           'Autre'],
  ];

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
      '#rm-overlay{position:fixed;inset:0;z-index:100001;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:16px}',
      '.rm-modal{background:#15151c;border:1px solid rgba(255,255,255,.12);border-radius:14px;max-width:420px;width:100%;max-height:85vh;overflow:auto;padding:20px;color:#eee;font-size:14px}',
      '.rm-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}',
      '.rm-title{font-size:15px;font-weight:700;margin:0}',
      '.rm-close{background:none;border:none;color:#aaa;font-size:18px;cursor:pointer;line-height:1}',
      '.rm-sub{font-size:12px;color:#a09cb8;margin:0 0 12px;line-height:1.5}',
      '.rm-reason{display:flex;align-items:center;gap:8px;padding:8px 10px;border:0.5px solid rgba(255,255,255,.12);border-radius:9px;margin-bottom:6px;cursor:pointer;font-size:13px}',
      '.rm-reason:hover{border-color:rgba(255,255,255,.3)}',
      '.rm-reason input{accent-color:#cc88ff}',
      '.rm-lbl{display:block;font-size:11.5px;font-weight:600;color:#bdb6d6;margin:10px 0 4px}',
      '.rm-input,.rm-msg{width:100%;box-sizing:border-box;background:#0e0e14;border:1px solid rgba(255,255,255,.14);border-radius:9px;color:#eee;padding:9px 11px;font-size:13px;font-family:inherit}',
      '.rm-msg{min-height:64px;resize:vertical}',
      '.rm-err{display:none;margin-top:8px;font-size:12.5px;color:#ff6b6b}',
      '.rm-submit{width:100%;margin-top:12px;padding:11px;border:none;border-radius:10px;background:#e24b4a;color:#fff;font-weight:700;font-size:13.5px;cursor:pointer}',
      '.rm-submit[disabled]{opacity:.55;cursor:not-allowed}',
      '.rm-join{margin:0 0 12px;padding:10px 12px;border-radius:10px;background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.3);font-size:12.5px;line-height:1.45;color:#ffe9a8}',
      '.rm-join button{margin-left:4px;background:none;border:none;padding:0;color:#ffd700;font-weight:700;text-decoration:underline;cursor:pointer;font-size:12.5px}',
    ].join('\n');
    document.head.appendChild(st);
  }

  function close() {
    var el = document.getElementById('rm-overlay');
    if (el) el.remove();
  }

  function open(opts) {
    opts = opts || {};
    if (!TARGET_TYPES[opts.targetType] || !opts.targetId) return;
    if (document.getElementById('rm-overlay')) return;
    _injectCss();

    var token = (typeof window.getAuthToken === 'function') ? window.getAuthToken() : null;

    var overlay = document.createElement('div');
    overlay.id = 'rm-overlay';
    overlay.innerHTML =
      '<div class="rm-modal" role="dialog" aria-modal="true">' +
        '<div class="rm-hdr">' +
          '<h3 class="rm-title">⚑ Signaler' + (opts.title ? ' — ' + _esc(opts.title) : '') + '</h3>' +
          '<button class="rm-close" id="rm-close" aria-label="Fermer">✕</button>' +
        '</div>' +
        '<p class="rm-sub">Signale un contenu qui te semble illégal ou contraire ' +
          'aux règles. Ton signalement est examiné par la modération ' +
          '(accusé de réception envoyé si ton email est connu).</p>' +
        // Parcours V1 : le visiteur est invité à créer son compte (signalement
        // en un clic). Le formulaire sans compte reste ouvert à tous (DSA).
        (!token
          ? '<p class="rm-join">Avec un compte gratuit, tu signales en un clic et tu suis la réponse.' +
            '<button type="button" id="rm-join">Créer mon compte</button></p>'
          : '') +
        REASONS.map(function (r, i) {
          return '<label class="rm-reason"><input type="radio" name="rm-reason" value="' +
            r[0] + '"' + (i === 0 ? ' checked' : '') + ' /> ' + _esc(r[1]) + '</label>';
        }).join('') +
        '<label class="rm-lbl" for="rm-detail">Précisions (optionnel)</label>' +
        '<textarea class="rm-msg" id="rm-detail" maxlength="2000" ' +
          'placeholder="Décris le problème…"></textarea>' +
        (!token
          ? '<label class="rm-lbl" for="rm-email">Ton email (pour l’accusé de réception ; sans compte, ajoute ton email ou une précision)</label>' +
            '<input class="rm-input" id="rm-email" type="email" placeholder="toi@exemple.com" />'
          : '') +
        '<div class="rm-err" id="rm-err"></div>' +
        '<button class="rm-submit" id="rm-submit">Envoyer le signalement</button>' +
      '</div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) { close(); return; }
      if (e.target && e.target.id === 'rm-join') {
        close();
        if (window.SmyleGate) window.SmyleGate.openSignup({ tab: 'signup' });
      }
    });
    document.getElementById('rm-close').addEventListener('click', close);

    var btn = document.getElementById('rm-submit');
    btn.addEventListener('click', async function () {
      var errEl = document.getElementById('rm-err');
      errEl.style.display = 'none';
      var reasonEl = document.querySelector('input[name="rm-reason"]:checked');
      var body = {
        target_type: opts.targetType,
        target_id:   String(opts.targetId),
        reason:      reasonEl ? reasonEl.value : 'autre',
        detail:      (document.getElementById('rm-detail').value || '').trim() || null,
      };
      var emailEl = document.getElementById('rm-email');
      if (emailEl && emailEl.value.trim()) body.reporter_email = emailEl.value.trim();

      btn.disabled = true;
      btn.textContent = 'Envoi…';
      try {
        var r = await window.apiFetch('/reports', { method: 'POST', json: body, auth: !!token });
        close();
        _toast('⚑ Signalement enregistré (réf. ' + String(r && r.id || '').slice(0, 8) + '…) — merci, il sera examiné.', 'success');
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Envoyer le signalement';
        var st2 = err && err.status;
        // Parcours V1 : sans compte, un signalement vide (ni précision ni
        // email) est refusé (422) — le message le dit et invite à s'inscrire,
        // au lieu d'un faux « réessaie dans un instant ».
        if (st2 === 429) {
          errEl.textContent = 'Trop de signalements récents — réessaie plus tard.';
        } else if (!token && (st2 === 422 || st2 === 401)) {
          errEl.innerHTML = 'Sans compte, ajoute une précision ou ton email pour qu’on puisse traiter ton signalement. ' +
            'Ou <button type="button" id="rm-join" style="background:none;border:none;padding:0;color:#ffd700;font-weight:700;text-decoration:underline;cursor:pointer;font-size:12.5px">crée ton compte gratuit</button> pour signaler en un clic.';
        } else if (st2 === 422) {
          var d = err.body && err.body.detail;
          errEl.textContent = (typeof d === 'string' && d) ? d : 'Signalement incomplet : ajoute une précision.';
        } else {
          errEl.textContent = 'Envoi impossible. Réessaie dans un instant.';
        }
        errEl.style.display = 'block';
      }
    });
  }

  // Délégué global : tout bouton .mp-report-btn (fiches produit, profils)
  // ouvre le modal — le composant est chargé sur toutes les pages.
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('.mp-report-btn');
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    open({
      targetType: btn.getAttribute('data-report-type'),
      targetId:   btn.getAttribute('data-report-id'),
      title:      btn.getAttribute('data-report-title') || null,
    });
  }, true);

  window.ReportModal = { open: open, close: close };
})();
