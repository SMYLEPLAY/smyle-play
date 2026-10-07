/*
 * Barre « objectif 1000 actifs » — Étape 3, Brique 3.
 *
 * Affiche « {n} / 1000 actifs — à 1000, le retrait en euros s'ouvre pour tous
 * (au plus tard le 1er mai 2027) », une barre de progression et les paliers
 * (500 / 1000 / 2500). Un palier franchi s'affiche « débloqué » : c'est de
 * l'AFFICHAGE, aucun retrait ne s'ouvre automatiquement.
 *
 * Totalement inerte tant que la brique n'est pas allumée : l'endpoint public
 * /objectif/actifs répond 404 quand FEATURE_GOAL est OFF, et l'encart reste
 * masqué (même principe que le compteur Pionnier). Masqué aussi en cas
 * d'erreur.
 *
 * Usage : poser un élément vide `<div data-goal-bar hidden></div>`.
 * Aucun HTML injecté depuis la réponse : tout passe par textContent.
 */
(function () {
  'use strict';

  function fmt(n) {
    try { return Number(n).toLocaleString('fr-FR'); } catch (_) { return String(n); }
  }

  function render(el, d) {
    var actifs = Number(d && d.actifs);
    var cible = Number(d && d.cible);
    if (!isFinite(actifs) || !isFinite(cible) || cible <= 0) return;
    el.textContent = '';

    var titre = document.createElement('div');
    titre.style.fontSize = '13px';
    titre.style.lineHeight = '1.45';
    var fort = document.createElement('strong');
    fort.textContent = fmt(actifs) + ' / ' + fmt(cible) + ' actifs';
    titre.appendChild(fort);
    var reste = String(d.texte || '');
    var i = reste.indexOf('—');
    titre.appendChild(document.createTextNode(i >= 0 ? ' ' + reste.slice(i) : ''));
    el.appendChild(titre);

    var piste = document.createElement('div');
    piste.setAttribute('role', 'progressbar');
    piste.setAttribute('aria-valuemin', '0');
    piste.setAttribute('aria-valuemax', String(cible));
    piste.setAttribute('aria-valuenow', String(Math.min(actifs, cible)));
    piste.setAttribute('aria-label', 'Actifs vers l\'objectif de ' + fmt(cible));
    piste.style.height = '8px';
    piste.style.margin = '8px 0 6px';
    piste.style.borderRadius = '999px';
    piste.style.background = 'rgba(255,255,255,.10)';
    piste.style.overflow = 'hidden';
    var remplie = document.createElement('i');
    remplie.style.display = 'block';
    remplie.style.height = '100%';
    remplie.style.borderRadius = '999px';
    remplie.style.background = 'linear-gradient(90deg,#8b6cf6,#2fbf71)';
    remplie.style.width = Math.round(Math.max(0, Math.min(1, actifs / cible)) * 100) + '%';
    piste.appendChild(remplie);
    el.appendChild(piste);

    var paliers = Array.isArray(d.paliers) ? d.paliers : [];
    if (paliers.length) {
      var ligne = document.createElement('div');
      ligne.style.display = 'flex';
      ligne.style.flexWrap = 'wrap';
      ligne.style.gap = '6px 14px';
      ligne.style.fontSize = '12px';
      ligne.style.opacity = '.85';
      paliers.forEach(function (p) {
        var s = document.createElement('span');
        s.textContent = (p.atteint ? '✓ ' : '○ ') + fmt(p.seuil) +
          (p.atteint ? ' — débloqué' : '');
        ligne.appendChild(s);
      });
      el.appendChild(ligne);
    }
    el.hidden = false;
  }

  function load() {
    var els = document.querySelectorAll('[data-goal-bar]');
    if (!els.length) return;
    var req = (typeof apiFetch === 'function')
      ? apiFetch('/objectif/actifs', { auth: false, retries: 0, timeoutMs: 5000 })
      : fetch('/objectif/actifs').then(function (r) { if (!r.ok) throw r; return r.json(); });
    req.then(function (d) {
      for (var i = 0; i < els.length; i++) render(els[i], d);
    }).catch(function () { /* 404 = objectif non lancé : on reste masqué */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
