/*
 * Compteur « places Pionnier restantes » — Brique 2, programme Pionnier.
 *
 * Levier de motivation : les 100 premiers créateurs qui publient une œuvre
 * deviennent Pionniers (commission plafonnée à 10 % à vie). Afficher les places
 * restantes pousse à publier.
 *
 * Totalement inerte tant que le programme n'est pas lancé : l'endpoint public
 * /pioneer/places répond 404 quand FEATURE_PIONEER est OFF, et l'encart reste
 * masqué. Masqué aussi quand il ne reste plus de place, ou en cas d'erreur.
 *
 * Usage : poser un élément vide `<div data-pioneer-counter hidden></div>`.
 */
(function () {
  'use strict';

  function render(el, d) {
    var restantes = Number(d && d.restantes);
    var total = Number(d && d.total) || 100;
    if (!isFinite(restantes) || restantes <= 0) return;
    var mot = restantes > 1 ? 'places Pionnier restantes' : 'place Pionnier restante';
    el.textContent = '';
    var fort = document.createElement('strong');
    fort.textContent = restantes + ' / ' + total + ' ' + mot;
    el.appendChild(fort);
    el.appendChild(document.createTextNode(
      ' — publie ta première œuvre pour décrocher ton rang : commission plafonnée à 10 % à vie.'
    ));
    el.hidden = false;
  }

  function load() {
    var els = document.querySelectorAll('[data-pioneer-counter]');
    if (!els.length) return;
    var req = (typeof apiFetch === 'function')
      ? apiFetch('/pioneer/places', { auth: false, retries: 0, timeoutMs: 5000 })
      : fetch('/pioneer/places').then(function (r) { if (!r.ok) throw r; return r.json(); });
    req.then(function (d) {
      for (var i = 0; i < els.length; i++) render(els[i], d);
    }).catch(function () { /* 404 = programme non lancé : on reste masqué */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
