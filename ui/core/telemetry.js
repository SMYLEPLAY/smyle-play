/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/telemetry.js
   Télémétrie D0 — émetteur privacy-first.

   Mesure le funnel (visiteur → inscrit → 1er achat → revient) SANS PII.
   - session_id anonyme persistée en localStorage (jeton aléatoire).
   - Respecte Do-Not-Track : si l'utilisateur l'a activé, on n'émet rien.
   - Batch + flush (intervalle + beforeunload via sendBeacon), best-effort :
     un échec réseau ne casse jamais l'app.
   - N'envoie QUE des noms whitelistés (alignés sur le backend).

   API publique :
     SmyleTrack.event('purchase', { kind: 'son', price: 25 });
     SmyleTrack.pageView();           // auto au chargement
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;

  // Do-Not-Track → opt-out total.
  var dnt = (navigator.doNotTrack === '1' || window.doNotTrack === '1' ||
             navigator.msDoNotTrack === '1');

  // Consentement (RGPD/ePrivacy) — OPT-IN : on n'émet RIEN tant que
  // l'utilisateur n'a pas explicitement accepté la mesure d'audience via la
  // bannière (ui/core/consent.js pose la clé). Découplé : on lit le localStorage
  // partagé, donc la télémétrie respecte le choix même sur une page qui ne
  // charge pas consent.js. Défaut (aucun choix) = pas de mesure.
  function _consented() {
    try { return localStorage.getItem('smyle_consent') === 'granted'; }
    catch (_) { return false; }
  }

  var API_BASE = (window.SMYLE_API_BASE ? String(window.SMYLE_API_BASE).replace(/\/+$/, '') : '');
  var ALLOWED = ['visit', 'page_view', 'signup', 'profile_complete', 'product_view',
                 'drawer_open', 'purchase', 'purchase_failed', 'boutique_open',
                 'onboarding_start', 'onboarding_complete'];

  // ── Session anonyme (non-PII) ─────────────────────────────────────────────
  function _sid() {
    try {
      var k = 'smyle_sid', v = localStorage.getItem(k);
      if (!v) {
        v = (crypto && crypto.randomUUID) ? crypto.randomUUID()
            : (Date.now().toString(36) + Math.random().toString(36).slice(2, 12));
        localStorage.setItem(k, v);
      }
      return v;
    } catch (_) { return 'anon-' + Math.random().toString(36).slice(2, 12); }
  }
  var SID = _sid();

  function _token() {
    try { return (typeof getAuthToken === 'function') ? getAuthToken() : null; }
    catch (_) { return null; }
  }

  // ── Buffer + flush ────────────────────────────────────────────────────────
  var buf = [];
  function _enqueue(name, props) {
    if (dnt || !_consented()) return;
    if (ALLOWED.indexOf(name) === -1) return;
    buf.push({
      name: name,
      path: location.pathname,
      referrer: document.referrer ? document.referrer.slice(0, 256) : null,
      props: (props && typeof props === 'object') ? props : null,
    });
    if (buf.length >= 10) flush();
  }

  function flush(useBeacon) {
    if (dnt || !_consented() || !buf.length) return;
    var batch = { session_id: SID, events: buf.splice(0, 50) };
    var url = API_BASE + '/events';
    var body = JSON.stringify(batch);
    // beforeunload → sendBeacon (pas d'auth header possible, mais best-effort).
    if (useBeacon && navigator.sendBeacon) {
      try { navigator.sendBeacon(url, new Blob([body], { type: 'application/json' })); return; }
      catch (_) { /* fallthrough */ }
    }
    var headers = { 'Content-Type': 'application/json' };
    var tok = _token();
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    try {
      fetch(url, { method: 'POST', headers: headers, body: body, keepalive: true })
        .catch(function () {});
    } catch (_) { /* silencieux */ }
  }

  // ── Visite : 1×/jour/session (déduplique le bruit) ────────────────────────
  function _visitOncePerDay() {
    try {
      var k = 'smyle_visit_day', today = new Date().toISOString().slice(0, 10);
      if (localStorage.getItem(k) !== today) {
        localStorage.setItem(k, today);
        _enqueue('visit');
      }
    } catch (_) { _enqueue('visit'); }
  }

  // ── API publique ──────────────────────────────────────────────────────────
  var SmyleTrack = {
    event: function (name, props) { _enqueue(name, props); },
    pageView: function () { _enqueue('page_view'); },
    flush: function () { flush(false); },
    sessionId: function () { return SID; },
  };
  window.SmyleTrack = SmyleTrack;

  // ── Auto-instrumentation ──────────────────────────────────────────────────
  if (!dnt) {
    _visitOncePerDay();
    _enqueue('page_view');
    setInterval(function () { flush(false); }, 8000);
    window.addEventListener('beforeunload', function () { flush(true); });
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') flush(true);
    });
  }
})();
