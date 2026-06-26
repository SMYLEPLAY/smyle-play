/* ─────────────────────────────────────────────────────────────────────────
   WATT — reflet « miroir » des cartes ID (verre).
   Additif et NON intrusif : écoute le survol au niveau document (délégation,
   donc marche pour les cartes rendues dynamiquement) et pose --mx/--my sur la
   carte sous le curseur. Le rendu du reflet est 100 % CSS (.mp-son-card::before).
   Ne touche AUCUNE structure ni mécanique. Défensif : si erreur, ne fait rien.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  try {
    document.addEventListener('mousemove', function (e) {
      var t = e.target;
      var card = t && t.closest ? t.closest('.mp-son-card') : null;
      if (!card) return;
      var b = card.getBoundingClientRect();
      if (!b.width || !b.height) return;
      card.style.setProperty('--mx', ((e.clientX - b.left) / b.width * 100).toFixed(1) + '%');
      card.style.setProperty('--my', ((e.clientY - b.top) / b.height * 100).toFixed(1) + '%');
    }, { passive: true });
  } catch (e) { /* effet optionnel : ne jamais casser l'app */ }
})();
