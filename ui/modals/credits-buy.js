/**
 * SMYLE PLAY — ui/modals/credits-buy.js
 *
 * P1-C2a (2026-04-28) — Modale d'achat de SMYLES.
 * Déclenchée par un click sur le badge balance topbar (cf. ui/smyle-balance.js).
 *
 * Architecture :
 *   - Auto-injecté dans le DOM au 1er appel à openCreditsBuyModal()
 *   - Fetch /credits/packs (apiFetch) au boot pour la grille de packs
 *   - Click pack → POST /credits/grant (stub V1) → refresh balance + toast
 *
 * Important — V1 / V2 :
 *   - V1 (actuelle) : POST /credits/grant crédite GRATUITEMENT le user connecté.
 *     Pratique pour test/dev/staging. Risque sécu en prod publique → l'endpoint
 *     doit être désactivé ou restreint avant ouverture publique (cf. P1-C2a-SEC).
 *   - V2 (Phase 11) : remplacer /credits/grant par Stripe Checkout. La modale
 *     ne change pas — seul le handler du click pack bascule sur l'URL Stripe.
 *
 * Disclaimer affiché à l'utilisateur pour rester honnête (règle Tom) :
 *   « Version test : crédits accordés gratuitement. Le paiement réel arrive bientôt. »
 *
 * Dépendances globales attendues :
 *   - apiFetch  (ui/core/api.js) — fetch authentifié
 *   - smyleToast (ui/core/toast.js) — feedback succès / erreur
 *   - SmyleBalance.refresh() (ui/smyle-balance.js) — refresh badge après grant
 */
(function () {
  'use strict';

  const MODAL_ID = 'creditsBuyModal';
  const STYLE_ID = 'credits-buy-modal-style';

  // ── Style modale (cohérent ADN PLUG WATT : noir/chrome/bleu/mauve + or pour le SMYLE) ──
  const CSS = `
    .credits-modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(5, 0, 12, 0.78);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 100000;
      padding: 20px;
      animation: creditsModalFadeIn 0.2s ease-out;
    }
    .credits-modal-overlay.is-open { display: flex; }

    @keyframes creditsModalFadeIn {
      from { opacity: 0; }
      to   { opacity: 1; }
    }
    @keyframes creditsModalSlideUp {
      from { opacity: 0; transform: translateY(20px) scale(0.98); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }

    .credits-modal {
      background: linear-gradient(180deg, #0e0118 0%, #050010 100%);
      border: 1px solid rgba(170, 0, 255, 0.32);
      border-radius: 18px;
      box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.04) inset,
        0 24px 60px rgba(0, 0, 0, 0.6),
        0 0 80px rgba(170, 0, 255, 0.18);
      max-width: 540px;
      width: 100%;
      max-height: 90vh;
      overflow-y: auto;
      padding: 28px 28px 24px;
      color: #e8e4f0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      animation: creditsModalSlideUp 0.25s ease-out;
      position: relative;
    }

    .credits-modal__close {
      position: absolute;
      top: 14px;
      right: 14px;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #b8b0cc;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      line-height: 1;
      transition: all 0.15s ease;
    }
    .credits-modal__close:hover {
      background: rgba(255, 255, 255, 0.08);
      color: #fff;
    }

    .credits-modal__title {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.01em;
      margin: 0 0 6px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .credits-modal__title-icon {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #2a0048, #0a0014);
      box-shadow: 0 0 8px rgba(170, 0, 255, 0.5);
    }
    .credits-modal__sub {
      font-size: 13px;
      color: #a098b8;
      margin: 0 0 22px;
      line-height: 1.5;
    }

    .credits-modal__packs {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      margin-bottom: 18px;
    }
    @media (min-width: 480px) {
      .credits-modal__packs {
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
      }
    }

    .credits-pack {
      background: linear-gradient(180deg, rgba(255, 215, 0, 0.06), rgba(255, 215, 0, 0.02));
      border: 1px solid rgba(255, 215, 0, 0.22);
      border-radius: 12px;
      padding: 16px 14px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      transition: all 0.18s ease;
      text-align: center;
      position: relative;
    }
    .credits-pack:hover:not(.is-loading) {
      border-color: rgba(255, 215, 0, 0.55);
      background: linear-gradient(180deg, rgba(255, 215, 0, 0.12), rgba(255, 215, 0, 0.04));
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(255, 215, 0, 0.18);
    }
    .credits-pack.is-loading {
      opacity: 0.6;
      cursor: wait;
      pointer-events: none;
    }
    .credits-pack__credits {
      font-size: 26px;
      font-weight: 700;
      color: #FFD700;
      font-variant-numeric: tabular-nums;
      line-height: 1;
    }
    .credits-pack__credits-label {
      font-size: 10px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: rgba(255, 215, 0, 0.65);
      font-weight: 600;
    }
    .credits-pack__price {
      font-size: 16px;
      font-weight: 600;
      color: #fff;
      margin-top: 4px;
    }
    .credits-pack__unit {
      font-size: 10px;
      color: #8a82a0;
      letter-spacing: 0.04em;
    }

    .credits-modal__disclaimer {
      background: rgba(0, 100, 255, 0.06);
      border: 1px solid rgba(0, 100, 255, 0.22);
      border-radius: 10px;
      padding: 11px 14px;
      font-size: 12px;
      line-height: 1.5;
      color: #a8c8ff;
    }
    .credits-modal__disclaimer strong { color: #d4e4ff; }

    .credits-modal__loading,
    .credits-modal__error {
      text-align: center;
      padding: 32px 16px;
      color: #8a82a0;
      font-size: 14px;
    }
    .credits-modal__error {
      color: #ff8a8a;
    }
  `;

  // ── DOM scaffolding ────────────────────────────────────────────────────
  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function ensureModal() {
    let modal = document.getElementById(MODAL_ID);
    if (modal) return modal;

    modal = document.createElement('div');
    modal.id = MODAL_ID;
    modal.className = 'credits-modal-overlay';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'creditsBuyTitle');

    modal.innerHTML = `
      <div class="credits-modal" role="document">
        <button type="button" class="credits-modal__close" aria-label="Fermer"
          onclick="window.closeCreditsBuyModal()">×</button>

        <h2 class="credits-modal__title" id="creditsBuyTitle">
          <span class="credits-modal__title-icon" aria-hidden="true"></span>
          Acheter des Smyles
        </h2>
        <p class="credits-modal__sub">
          Les Smyles te permettent de débloquer des prompts, des ADN et des voix
          d'artistes. Choisis ton pack.
        </p>

        <div class="credits-modal__packs" id="creditsPacks">
          <div class="credits-modal__loading">Chargement des packs…</div>
        </div>

        <div class="credits-modal__disclaimer">
          <strong>Version test :</strong> les crédits sont actuellement
          accordés gratuitement pour valider la mécanique. Le paiement réel
          (Stripe) arrive bientôt.
        </div>
      </div>
    `;

    // Click outside the modal closes it
    modal.addEventListener('click', (ev) => {
      if (ev.target === modal) closeCreditsBuyModal();
    });

    // ESC key closes it
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && modal.classList.contains('is-open')) {
        closeCreditsBuyModal();
      }
    });

    document.body.appendChild(modal);
    return modal;
  }

  // ── Render des packs ───────────────────────────────────────────────────
  async function loadAndRenderPacks() {
    const container = document.getElementById('creditsPacks');
    if (!container) return;
    container.innerHTML = '<div class="credits-modal__loading">Chargement des packs…</div>';

    if (typeof apiFetch !== 'function') {
      container.innerHTML = '<div class="credits-modal__error">⚠ API non disponible. Recharge la page.</div>';
      return;
    }

    try {
      const data = await apiFetch('/credits/packs');
      const packs = (data && data.packs) || [];
      if (packs.length === 0) {
        container.innerHTML = '<div class="credits-modal__error">Aucun pack disponible pour le moment.</div>';
        return;
      }

      container.innerHTML = packs
        .map((p) => {
          // Format prix : 8.00 € → 8 € si entier, sinon garder les centimes
          const priceDisplay = p.price_eur_display || `${(p.price_eur_cents / 100).toFixed(2)} €`;
          const unitCents = p.unit_price_cents || 0;
          const unitDisplay = unitCents
            ? `${(unitCents / 100).toFixed(2)} € / Smyle`
            : '';
          return `
            <button type="button" class="credits-pack" data-pack-id="${p.id}"
              data-pack-credits="${p.credits}"
              onclick="window._creditsBuyPack(this)">
              <span class="credits-pack__credits">${p.credits}</span>
              <span class="credits-pack__credits-label">Smyles</span>
              <span class="credits-pack__price">${priceDisplay}</span>
              ${unitDisplay ? `<span class="credits-pack__unit">${unitDisplay}</span>` : ''}
            </button>
          `;
        })
        .join('');
    } catch (err) {
      console.warn('[credits-buy] fetch packs failed:', err);
      container.innerHTML = `
        <div class="credits-modal__error">
          ⚠ Impossible de charger les packs.<br>
          Vérifie ta connexion et réessaie.
        </div>
      `;
    }
  }

  // ── Achat d'un pack (V1 : grant gratuit, V2 : Stripe) ──────────────────
  async function buyPack(btn) {
    if (!btn || btn.classList.contains('is-loading')) return;
    const credits = parseInt(btn.getAttribute('data-pack-credits'), 10);
    const packId  = btn.getAttribute('data-pack-id');
    if (!credits || credits <= 0) return;

    btn.classList.add('is-loading');

    if (typeof apiFetch !== 'function') {
      btn.classList.remove('is-loading');
      _toast('⚠ API non disponible.', 'error');
      return;
    }

    try {
      await apiFetch('/credits/grant', {
        method: 'POST',
        json: {
          credits,
          reason: `V1 stub — pack ${packId}`,
        },
      });
      // Refresh badge balance topbar (existant)
      if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
        try { await window.SmyleBalance.refresh(); } catch (_) {}
      }
      _toast(`✓ ${credits} Smyles ajoutés à ton compte`, 'success');
      closeCreditsBuyModal();
    } catch (err) {
      console.error('[credits-buy] grant failed:', err);
      // C4 (2026-04-29) — En prod publique, l'endpoint renvoie 403 avec
      // detail.code='grant_disabled_in_prod' tant que Stripe n'est pas
      // branché. On bascule la modale en mode informatif (bandeau + boutons
      // désactivés) plutôt que de répéter le toast d'erreur à chaque click.
      if (err && err.status === 403) {
        _showStripeArrivingMode();
        btn.classList.remove('is-loading');
        return;
      }
      const detail = err && err.body && err.body.detail;
      const msg = (typeof detail === 'string' ? detail : null)
               || (detail && detail.message)
               || (err && err.message)
               || 'Échec de l\'opération. Réessaie.';
      _toast(`⚠ ${msg}`, 'error');
      btn.classList.remove('is-loading');
    }
  }

  // C4 (2026-04-29) — Bascule la modale en "mode Stripe à venir".
  // Désactive tous les boutons pack et remplace le disclaimer V1 par un
  // bandeau honnête expliquant que le paiement réel est en route.
  function _showStripeArrivingMode() {
    const container = document.getElementById('creditsPacks');
    if (container) {
      container.querySelectorAll('.credits-pack').forEach((b) => {
        b.classList.add('is-loading');
        b.style.cursor = 'not-allowed';
        b.style.opacity = '0.55';
      });
    }
    const modal = document.getElementById(MODAL_ID);
    if (modal) {
      const disclaimer = modal.querySelector('.credits-modal__disclaimer');
      if (disclaimer) {
        disclaimer.innerHTML = `
          <strong>Paiement réel en route.</strong>
          L'achat direct de crédits est actuellement désactivé sur cette
          version publique. Stripe Checkout est en intégration — tu
          pourras acheter tes Smyles ici sous peu.
        `;
      }
    }
  }

  function _toast(text, type) {
    if (typeof window.smyleToast === 'function') {
      window.smyleToast(text, { type: type || 'info', duration: 2800 });
    } else {
      // Fallback minimaliste
      try { console.log('[credits-buy]', text); } catch (_) {}
    }
  }

  // ── API publique ───────────────────────────────────────────────────────
  function openCreditsBuyModal() {
    injectStyle();
    const modal = ensureModal();
    modal.classList.add('is-open');
    // Lock scroll body
    document.body.style.overflow = 'hidden';
    // Charge les packs à chaque ouverture (au cas où le serveur a changé)
    loadAndRenderPacks();
  }

  function closeCreditsBuyModal() {
    const modal = document.getElementById(MODAL_ID);
    if (modal) modal.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  // Expositions globales
  window.openCreditsBuyModal  = openCreditsBuyModal;
  window.closeCreditsBuyModal = closeCreditsBuyModal;
  window._creditsBuyPack      = buyPack;
})();
