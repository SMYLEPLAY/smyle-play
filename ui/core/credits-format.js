/**
 * Équivalence euros pour les prix en Smyles.
 *
 * Tom 2026-05-13 — donner un ordre d'idée du prix réel partout où un
 * prix crédits s'affiche (saisie dashboard, cards marketplace, modale unlock).
 *
 * Taux : 0.07 €/Smyle (pack de 500 médian de CREDIT_PACKS, redénomination
 * ×10 du 9/10/2026). Format : '15 Smyles (≈ 1€)' — le ≈ indique que le tarif
 * varie selon le pack acheté (0.06–0.08 €/Smyle en réalité).
 *
 * API exposée sur window :
 *   - EUR_PER_CREDIT (float)
 *   - creditsToEurFloat(n)        → 1.05
 *   - formatEurApprox(n)          → '≈ 1€'
 *   - formatCreditsWithEur(n)     → '15 Smyles (≈ 1€)'
 */
(function() {
  'use strict';

  const EUR_PER_CREDIT = 0.07;

  function creditsToEurFloat(n) {
    const c = parseInt(n, 10);
    if (!Number.isFinite(c) || c <= 0) return 0;
    return c * EUR_PER_CREDIT;
  }

  function formatEurApprox(n) {
    const eur = creditsToEurFloat(n);
    if (eur <= 0) return '';
    if (eur < 1) {
      return '≈ ' + eur.toFixed(2).replace('.', ',') + '€';
    }
    if (eur < 100) {
      return '≈ ' + Math.round(eur) + '€';
    }
    return '≈ ' + Math.round(eur).toLocaleString('fr-FR') + '€';
  }

  function formatCreditsWithEur(n) {
    const credits = parseInt(n, 10);
    if (!Number.isInteger(credits) || credits <= 0) return '';
    const eur = formatEurApprox(credits);
    const credStr = credits.toLocaleString('fr-FR') + ' Smyles';
    return eur ? credStr + ' (' + eur + ')' : credStr;
  }

  window.EUR_PER_CREDIT       = EUR_PER_CREDIT;
  window.creditsToEurFloat    = creditsToEurFloat;
  window.formatEurApprox      = formatEurApprox;
  window.formatCreditsWithEur = formatCreditsWithEur;
})();
