/**
 * Équivalence euros pour les prix en crédits Smyle.
 *
 * Tom 2026-05-13 — donner un ordre d'idée du prix réel partout où un
 * prix crédits s'affiche (saisie dashboard, cards marketplace, modale unlock).
 *
 * Taux : 0.70 €/crédit (pack_50 médian de CREDIT_PACKS).
 * Format : '500 crédits (≈ 350€)' — le ≈ indique que le tarif varie
 * selon le pack acheté (0.60–0.80 €/crédit en réalité).
 *
 * API exposée sur window :
 *   - EUR_PER_CREDIT (float)
 *   - creditsToEurFloat(n)        → 350.0
 *   - formatEurApprox(n)          → '≈ 350€'
 *   - formatCreditsWithEur(n)     → '500 crédits (≈ 350€)'
 */
(function() {
  'use strict';

  const EUR_PER_CREDIT = 0.70;

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
    const credStr = credits.toLocaleString('fr-FR') + ' crédits';
    return eur ? credStr + ' (' + eur + ')' : credStr;
  }

  window.EUR_PER_CREDIT       = EUR_PER_CREDIT;
  window.creditsToEurFloat    = creditsToEurFloat;
  window.formatEurApprox      = formatEurApprox;
  window.formatCreditsWithEur = formatCreditsWithEur;
})();
