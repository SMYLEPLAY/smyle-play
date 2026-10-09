/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/pwa/pwa.js · application installable (Lot E).

   Injecté par le serveur dans toutes les pages HTML (app/routers/pages.py),
   avec l'attribut data-sw="on" ou "off" (interrupteur PWA_ACTIVE).

   1. Service worker : enregistré si data-sw="on" ; si "off", tout worker
      déjà installé est désinscrit et ses caches vidés (arrêt à distance).
   2. Bandeau discret « Installer l'app » :
        • Android / Chrome : bouton qui ouvre la fenêtre d'installation du
          navigateur (événement beforeinstallprompt) ;
        • iPhone / iPad (Safari) : fenêtre d'explication en français
          (« Appuie sur Partager puis "Sur l'écran d'accueil" »).
      Jamais affiché si l'app est déjà installée (mode plein écran), ni
      pendant 14 jours après un refus.
   Aucun script inline (compatible CSP), aucune dépendance.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  var script = document.currentScript;
  var SW_ACTIF = !script || script.getAttribute('data-sw') !== 'off';
  var CLE_REFUS = 'watt_pwa_refus';
  var DELAI_REFUS_MS = 14 * 24 * 60 * 60 * 1000;
  var DELAI_AFFICHAGE_MS = 4000;

  // ── 1. Service worker ──────────────────────────────────────────────────
  function gererServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    if (SW_ACTIF) {
      navigator.serviceWorker
        .register('/sw.js', { scope: '/', updateViaCache: 'none' })
        .catch(function () { /* navigation privée, http… : sans gravité */ });
      return;
    }
    // Arrêt à distance : désinscription + caches vidés.
    navigator.serviceWorker.getRegistrations().then(function (regs) {
      regs.forEach(function (r) { r.unregister(); });
    }).catch(function () {});
    if (window.caches && caches.keys) {
      caches.keys().then(function (noms) {
        noms.forEach(function (n) { if (n.indexOf('watt-') === 0) caches.delete(n); });
      }).catch(function () {});
    }
  }

  // ── 2. Bandeau « Installer l'app » ─────────────────────────────────────
  function dejaInstallee() {
    try {
      if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true;
    } catch (e) { /* */ }
    return window.navigator.standalone === true; // Safari iOS
  }

  function refusRecent() {
    try {
      var t = parseInt(window.localStorage.getItem(CLE_REFUS) || '0', 10);
      return t > 0 && (Date.now() - t) < DELAI_REFUS_MS;
    } catch (e) {
      return false;
    }
  }

  function noterRefus() {
    try { window.localStorage.setItem(CLE_REFUS, String(Date.now())); } catch (e) { /* */ }
  }

  function estIOS() {
    var ua = navigator.userAgent || '';
    var iDevice = /iPhone|iPad|iPod/.test(ua) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); // iPadOS
    return iDevice;
  }

  var promptDiffere = null;
  var bandeau = null;

  function fermerBandeau(refus) {
    if (refus) noterRefus();
    if (bandeau && bandeau.parentNode) bandeau.parentNode.removeChild(bandeau);
    bandeau = null;
  }

  function aideIOS() {
    var fond = document.createElement('div');
    fond.className = 'watt-pwa-aide';
    fond.setAttribute('role', 'dialog');
    fond.setAttribute('aria-modal', 'true');
    fond.setAttribute('aria-labelledby', 'watt-pwa-aide-titre');
    fond.innerHTML =
      '<div class="watt-pwa-aide-boite">' +
        '<img src="/ui/pwa/icones/icone-192.png" alt="" width="56" height="56">' +
        '<h2 id="watt-pwa-aide-titre">Installer WATT sur ton iPhone</h2>' +
        '<ol>' +
          '<li>Appuie sur <strong>Partager</strong>&nbsp;' +
            '<span class="watt-pwa-partage" aria-hidden="true">' +
              '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M8 7l4-4 4 4"/><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/></svg>' +
            '</span> ;</li>' +
          '<li>puis sur <strong>« Sur l’écran d’accueil »</strong>.</li>' +
        '</ol>' +
        '<p>L’icône WATT apparaît sur ton écran d’accueil et l’app s’ouvre en plein écran.</p>' +
        '<button type="button" class="watt-pwa-ok">J’ai compris</button>' +
      '</div>';
    function fermer() {
      if (fond.parentNode) fond.parentNode.removeChild(fond);
      document.removeEventListener('keydown', echap);
    }
    function echap(e) { if (e.key === 'Escape') fermer(); }
    fond.addEventListener('click', function (e) { if (e.target === fond) fermer(); });
    fond.querySelector('.watt-pwa-ok').addEventListener('click', fermer);
    document.addEventListener('keydown', echap);
    document.body.appendChild(fond);
    fond.querySelector('.watt-pwa-ok').focus();
  }

  function installer() {
    if (promptDiffere) {
      var p = promptDiffere;
      promptDiffere = null;
      fermerBandeau(false);
      p.prompt();
      if (p.userChoice && p.userChoice.then) {
        p.userChoice.then(function (choix) {
          if (!choix || choix.outcome !== 'accepted') noterRefus();
        }).catch(function () {});
      }
      return;
    }
    if (estIOS()) {
      // Les explications ont été lues : on ne relance pas avant 14 jours.
      fermerBandeau(true);
      aideIOS();
    }
  }

  function afficherBandeau() {
    if (bandeau || dejaInstallee() || refusRecent() || !document.body) return;
    bandeau = document.createElement('div');
    bandeau.className = 'watt-pwa-bandeau';
    bandeau.setAttribute('role', 'region');
    bandeau.setAttribute('aria-label', 'Installer l’application WATT');
    bandeau.innerHTML =
      '<button type="button" class="watt-pwa-installer">' +
        '<img src="/ui/pwa/icones/icone-192.png" alt="" width="24" height="24">' +
        '<span>Installer l’app</span>' +
      '</button>' +
      '<button type="button" class="watt-pwa-fermer" aria-label="Plus tard">×</button>';
    bandeau.querySelector('.watt-pwa-installer').addEventListener('click', installer);
    bandeau.querySelector('.watt-pwa-fermer').addEventListener('click', function () {
      fermerBandeau(true);
    });
    document.body.appendChild(bandeau);
  }

  // Affiche le bandeau après un court délai, et pas tant que le bandeau de
  // consentement (mesure d'audience) occupe le bas de l'écran.
  function planifierBandeau() {
    if (dejaInstallee() || refusRecent()) return;
    var essais = 0;
    function tenter() {
      essais += 1;
      var consentement = document.getElementById('smyle-consent');
      if (consentement && consentement.offsetParent !== null && essais < 30) {
        window.setTimeout(tenter, 3000);
        return;
      }
      afficherBandeau();
    }
    window.setTimeout(tenter, DELAI_AFFICHAGE_MS);
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); // pas de mini-bannière automatique : notre bandeau
    promptDiffere = e;
    planifierBandeau();
  });

  window.addEventListener('appinstalled', function () {
    promptDiffere = null;
    fermerBandeau(false);
  });

  function demarrer() {
    gererServiceWorker();
    // iPhone / iPad : pas d'événement d'installation, on explique.
    if (estIOS()) planifierBandeau();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', demarrer);
  } else {
    demarrer();
  }

  // Exposé pour les tests et un éventuel bouton « Installer » du site.
  window.WattPWA = {
    installer: installer,
    afficherBandeau: afficherBandeau,
    dejaInstallee: dejaInstallee,
    refusRecent: refusRecent,
  };
})();
