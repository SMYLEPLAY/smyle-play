/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/cgu-gate.js
   Lot D — ré-acceptation des CGU.

   Quand les conditions d'utilisation changent (CGU_VERSION côté serveur), un
   compte connecté qui ne les a pas encore acceptées voit une fenêtre
   BLOQUANTE : lien vers les CGU, bouton « J'accepte », ou déconnexion.
   Tant qu'il n'a pas accepté, le serveur refuse les actions qui écrivent
   (achat, publication, vente…) avec le code `cgu_a_accepter` ; api.js
   rouvre alors cette fenêtre.

   Chargé par api.js (si un jeton est présent, ou sur réponse 403
   `cgu_a_accepter`). API : window.SmyleCguGate.check() / .show(version)
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.SmyleCguGate) return;

  // Pages où la fenêtre ne s'ouvre pas : il faut pouvoir lire les CGU, et
  // finir un changement de mot de passe ou une vérification d'email.
  function pageExemptee() {
    return /^\/(legal|reset|verifier-email)(\.html)?\/?$/.test(location.pathname);
  }

  function dateFr(v) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v || ''));
    if (!m) return '';
    var mois = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
                'septembre', 'octobre', 'novembre', 'décembre'][Number(m[2]) - 1];
    return Number(m[3]) + (m[3] === '01' ? 'er' : '') + ' ' + mois + ' ' + m[1];
  }

  var CSS = [
    '#cgu-gate{position:fixed;inset:0;z-index:2147483600;background:rgba(5,3,10,.86);display:flex;align-items:center;justify-content:center;padding:16px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}',
    '#cgu-gate .cg-box{background:#15111f;border:1px solid rgba(204,136,255,.35);border-radius:16px;max-width:460px;width:100%;padding:22px 20px;color:#ece8f5;box-shadow:0 20px 60px rgba(0,0,0,.6);box-sizing:border-box}',
    '#cgu-gate h2{margin:0 0 10px;font-size:18px;line-height:1.3}',
    '#cgu-gate p{margin:0 0 12px;font-size:14px;line-height:1.6;color:#cfc8de}',
    '#cgu-gate a{color:#c9a6ff}',
    '#cgu-gate .cg-check{display:flex;gap:10px;align-items:flex-start;margin:14px 0;font-size:14px;line-height:1.5;cursor:pointer}',
    '#cgu-gate .cg-check input{margin-top:3px;width:18px;height:18px;accent-color:#cc88ff;flex-shrink:0}',
    '#cgu-gate .cg-ok{width:100%;padding:12px;border:none;border-radius:11px;background:#ffd700;color:#120a1c;font-weight:800;font-size:15px;cursor:pointer}',
    '#cgu-gate .cg-ok[disabled]{opacity:.45;cursor:not-allowed}',
    '#cgu-gate .cg-out{display:block;margin:12px auto 0;background:none;border:none;color:#9d95b3;font-size:13px;text-decoration:underline;cursor:pointer}',
    '#cgu-gate .cg-err{display:none;color:#ff7b7b;font-size:13px;margin:8px 0 0}'
  ].join('\n');

  var ouvert = false;

  function show(version) {
    if (ouvert || pageExemptee() || document.getElementById('cgu-gate')) return;
    ouvert = true;
    if (!document.getElementById('cgu-gate-css')) {
      var st = document.createElement('style');
      st.id = 'cgu-gate-css';
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    var d = dateFr(version);
    var el = document.createElement('div');
    el.id = 'cgu-gate';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('aria-labelledby', 'cgu-gate-title');
    el.innerHTML =
      '<div class="cg-box">' +
        '<h2 id="cgu-gate-title">Nos conditions d’utilisation ont changé</h2>' +
        '<p>Pour continuer à acheter, publier ou vendre sur WATT, accepte la nouvelle version' +
          (d ? ' (en vigueur le ' + d + ')' : '') + ' de nos conditions générales d’utilisation.</p>' +
        '<p><a href="/legal#cgu" target="_blank" rel="noopener">Lire les conditions d’utilisation</a> ' +
          '(s’ouvre dans un nouvel onglet).</p>' +
        '<label class="cg-check"><input type="checkbox" id="cgu-gate-check" /> ' +
          '<span>J’ai lu et j’accepte les conditions générales d’utilisation.</span></label>' +
        '<button type="button" class="cg-ok" id="cgu-gate-ok" disabled>Accepter et continuer</button>' +
        '<div class="cg-err" id="cgu-gate-err"></div>' +
        '<button type="button" class="cg-out" id="cgu-gate-out">Me déconnecter</button>' +
      '</div>';
    document.body.appendChild(el);
    var chk = document.getElementById('cgu-gate-check');
    var ok = document.getElementById('cgu-gate-ok');
    var err = document.getElementById('cgu-gate-err');
    chk.addEventListener('change', function () { ok.disabled = !chk.checked; });
    ok.addEventListener('click', function () {
      ok.disabled = true;
      err.style.display = 'none';
      window.apiFetch('/users/me/accept-terms', { method: 'POST' })
        .then(function () {
          el.remove();
          ouvert = false;
          try { window.dispatchEvent(new CustomEvent('smyle:cgu-accepted')); } catch (_) {}
          if (window.smyleToast) window.smyleToast('Merci, c’est enregistré.', { type: 'success' });
        })
        .catch(function () {
          ok.disabled = !chk.checked;
          err.textContent = 'Enregistrement impossible. Réessaie dans un instant.';
          err.style.display = 'block';
        });
    });
    document.getElementById('cgu-gate-out').addEventListener('click', function () {
      try { if (typeof window.clearAuthToken === 'function') window.clearAuthToken(); } catch (_) {}
      try { if (window.smyleClearPersonalData) window.smyleClearPersonalData(); } catch (_) {}
      window.location.href = '/';
    });
    setTimeout(function () { try { chk.focus(); } catch (_) {} }, 50);
  }

  function check() {
    if (pageExemptee() || typeof window.apiFetch !== 'function') return;
    if (!(typeof window.getAuthToken === 'function' && window.getAuthToken())) return;
    window.apiFetch('/users/me')
      .then(function (me) { if (me && me.cgu_a_jour === false) show(me.cgu_version); })
      .catch(function () { /* silencieux : la page reste utilisable en lecture */ });
  }

  window.SmyleCguGate = { check: check, show: show };
  window.addEventListener('smyle:cgu-required', function (e) {
    show(e && e.detail && e.detail.version);
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', check);
  else check();
})();
