/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/onboarding.js
   D1 (comprendre) — modal de bienvenue premier-run.

   But : qu'un inconnu comprenne en < 30 s ce qu'est WATT, ce qu'est un Smyle /
   un ADN / une recette, voie ses Smyles de bienvenue, et fasse un 1er pas.

   - S'affiche UNE seule fois (flag localStorage). Re-déclenchable via
     window.SmyleOnboarding.open().
   - Auto : au chargement, si connecté et pas encore vu.
   - Best-effort, dépendances souples (getAuthToken, SmyleBalance, SmyleTrack).
   - Télémétrie : onboarding_start (ouverture) · onboarding_complete (CTA/fin).
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;

  var FLAG = 'smyle_onboarded_v1';

  function _seen() { try { return localStorage.getItem(FLAG) === '1'; } catch (_) { return false; } }
  function _markSeen() { try { localStorage.setItem(FLAG, '1'); } catch (_) {} }
  function _loggedIn() {
    try {
      if (typeof getCurrentUser === 'function' && getCurrentUser()) return true;
      if (typeof getAuthToken === 'function' && getAuthToken()) return true;
    } catch (_) {}
    return false;
  }
  function _track(name) { try { if (window.SmyleTrack) window.SmyleTrack.event(name); } catch (_) {} }
  function _balance() {
    try {
      if (window.SmyleBalance && typeof window.SmyleBalance.get === 'function') {
        var b = window.SmyleBalance.get();
        if (b != null && isFinite(b)) return Math.round(b);
      }
    } catch (_) {}
    return null;
  }

  var STEPS = [
    { icon: '🎧', t: 'Écoute libre', d: "Parcours les sons, les artistes et les univers de WATT. Écouter ne coûte rien." },
    { icon: '⚡', t: 'Les Smyles', d: "La monnaie de WATT. Tu en reçois pour démarrer ; ils servent à débloquer ce qui te plaît." },
    { icon: '🧬', t: "L'ADN & la recette", d: "Débloquer, c'est obtenir la recette reproductible d'une œuvre — pas juste un fichier. De quoi créer à ton tour." },
  ];

  function _ensure() {
    var m = document.getElementById('obWelcome');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'obWelcome';
    m.style.cssText = 'position:fixed;inset:0;z-index:1400;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.78);padding:16px;';
    document.body.appendChild(m);
    m.addEventListener('click', function (e) { if (e.target === m) _close(true); });
    return m;
  }

  function _render() {
    var m = _ensure();
    var bal = _balance();
    var smyleLine = (bal != null)
      ? 'Tu as <b style="color:#ffb627">' + bal + ' Smyles</b> pour commencer.'
      : 'Tu as des <b style="color:#ffb627">Smyles de bienvenue</b> pour commencer.';
    var stepsHtml = STEPS.map(function (s) {
      return '<div style="display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-top:1px solid #221b34;">'
           + '<div style="font-size:22px;line-height:1.1">' + s.icon + '</div>'
           + '<div><div style="font-size:14px;font-weight:800">' + s.t + '</div>'
           + '<div style="font-size:13px;color:#9990ad;margin-top:2px">' + s.d + '</div></div></div>';
    }).join('');
    m.innerHTML =
      '<div style="position:relative;max-width:480px;width:100%;max-height:92vh;overflow:auto;background:#14101f;border:1px solid #2c2440;border-radius:18px;padding:26px;color:#eee;font-family:inherit;">'
      + '<button id="obClose" aria-label="Fermer" style="position:absolute;top:14px;right:18px;background:none;border:none;color:#aaa;font-size:24px;cursor:pointer;line-height:1">×</button>'
      + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#ffb627">Bienvenue sur WATT</div>'
      + '<h2 style="margin:6px 0 4px;font-size:22px">Branche-toi en 30 secondes</h2>'
      + '<p style="margin:0 0 6px;font-size:13px;color:#cfc6e6">' + smyleLine + '</p>'
      + '<div style="margin:10px 0 18px">' + stepsHtml + '</div>'
      + '<button id="obStart" style="width:100%;background:#6c4cf0;border:none;color:#fff;border-radius:12px;padding:14px;cursor:pointer;font-size:15px;font-weight:700">Compléter mon profil →</button>'
      + '<button id="obExplore" style="width:100%;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:11px;padding:11px;cursor:pointer;font-size:13px;margin-top:10px">Explorer d\'abord</button>'
      + '<div style="text-align:center;margin-top:12px"><a id="obMore" href="/comment-ca-marche" style="font-size:12px;color:#9990ad">Comment ça marche en détail ?</a></div>'
      + '</div>';
    m.querySelector('#obClose').addEventListener('click', function () { _close(true); });
    m.querySelector('#obExplore').addEventListener('click', function () { _close(true); });
    m.querySelector('#obStart').addEventListener('click', function () {
      _close(true);
      try { location.href = '/dashboard#profile'; } catch (_) {}
    });
    m.querySelector('#obMore').addEventListener('click', function () { _markSeen(); _track('onboarding_complete'); });
    return m;
  }

  function open() {
    var m = _render();
    m.style.display = 'flex';
    _track('onboarding_start');
  }
  function _close(complete) {
    var m = document.getElementById('obWelcome');
    if (m) m.style.display = 'none';
    _markSeen();
    if (complete) _track('onboarding_complete');
  }

  window.SmyleOnboarding = { open: open, reset: function () { try { localStorage.removeItem(FLAG); } catch (_) {} } };

  // Auto premier-run : connecté + jamais vu. Léger délai pour laisser la page
  // (et le solde) se charger.
  function _maybeAuto() {
    if (_seen() || !_loggedIn()) return;
    setTimeout(open, 900);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _maybeAuto);
  } else { _maybeAuto(); }
})();
