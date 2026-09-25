/**
 * SMYLE PLAY — ui/modals/credits-buy.js
 *
 * P1-C2a (2026-04-28) — Modale d'achat de SMYLES.
 * Déclenchée par un click sur le badge balance topbar (cf. ui/smyle-balance.js).
 *
 * Architecture :
 *   - Auto-injecté dans le DOM au 1er appel à openCreditsBuyModal()
 *   - Fetch /credits/packs (apiFetch) au boot pour la grille de packs
 *   - Lot 3 : clic pack = sélection ; case de renonciation obligatoire ;
 *     « Payer » → POST /credits/checkout → page de paiement Stripe. Le crédit
 *     arrive par le webhook signé côté serveur, jamais depuis le navigateur.
 *
 * État réel (S-11, 2026-09-04, annexe A §M5) :
 *   - la modale ne s'ouvre QUE si l'item de mode lancement `achatSmyles` est
 *     VISIBLE (`window.WATT_LAUNCH.achatSmyles`) ; sinon toast honnête ;
 *   - le stub « V1 gratuit » (POST /credits/grant) est RETIRÉ : depuis le
 *     gate `is_official`, il répondait 403 à tout compte normal — le clic
 *     « Acheter » ne pouvait que finir en « Échec de l'opération » ;
 *   - Stripe (V2) créditera par webhook signé vérifié côté serveur, jamais
 *     par un appel direct du front. C'est à ce moment qu'on rallumera
 *     `SHOW_ACHAT_SMYLES=true` et qu'on rebranchera le handler du clic pack.
 *
 * Disclaimer affiché à l'utilisateur pour rester honnête (règle Tom) :
 *   « Beta : les Smyles sont offerts — tu en gagnes en explorant et en jouant. »
 *
 * Dépendances globales attendues :
 *   - apiFetch  (ui/core/api.js) — fetch authentifié
 *   - smyleToast (ui/core/toast.js) — feedback succès / erreur
 *   - SmyleBalance.refresh() (ui/smyle-balance.js) — refresh badge (Stripe, plus tard)
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
    .credits-pack.is-selected { border-color: #ffd700; box-shadow: 0 0 0 2px rgba(255,215,0,.45); }
    .credits-modal__packs { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; margin: 14px 0 10px; }
    .credits-buy__tva { margin: 0 0 8px; font-size: 12px; color: rgba(255,255,255,.6); }
    .credits-buy__consent { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; line-height: 1.45; color: rgba(255,255,255,.85); cursor: pointer; margin: 6px 0; }
    .credits-buy__consent input { width: 18px; height: 18px; flex: 0 0 18px; margin-top: 1px; accent-color: #ffd700; }
    .credits-buy__legal { font-size: 12px; color: rgba(255,255,255,.55); margin: 6px 0 12px; }
    .credits-buy__legal a { color: #cc88ff; }
    .credits-buy__pay { width: 100%; padding: 13px 16px; border: none; border-radius: 12px; font-weight: 800; font-size: 15px; cursor: pointer; background: linear-gradient(120deg, #ffd700, #ff9f1a); color: #1a1206; }
    .credits-buy__pay:disabled { opacity: .45; cursor: not-allowed; }
    .credits-buy__pay:focus-visible, .credits-pack:focus-visible { outline: 2px solid #ffd700; outline-offset: 2px; }
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

    /* LANCEMENT 2026-07-20 — bloc « gagner des Smyles » (remplace la grille
       de packs payants, retirée tant que Stripe n'est pas branché). */
    .credits-modal__earn {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }
    @media (min-width: 480px) {
      .credits-modal__earn { grid-template-columns: 1fr 1fr; }
    }
    .credits-earn {
      display: flex;
      align-items: center;
      gap: 12px;
      text-align: left;
      background: rgba(255, 215, 0, 0.05);
      border: 1px solid rgba(255, 215, 0, 0.22);
      border-radius: 12px;
      padding: 14px;
      color: inherit;
      font: inherit;
      cursor: pointer;
      transition: all 0.18s ease;
    }
    .credits-earn:hover {
      border-color: rgba(255, 215, 0, 0.55);
      background: rgba(255, 215, 0, 0.10);
      transform: translateY(-2px);
    }
    .credits-earn__ico { font-size: 26px; line-height: 1; }
    .credits-earn__txt { display: flex; flex-direction: column; gap: 3px; }
    .credits-earn__txt strong { font-size: 14px; color: #fff; font-weight: 700; }
    .credits-earn__txt em { font-style: normal; font-size: 11px; color: #a098b8; }

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
          Tes Smyles
        </h2>
        <p class="credits-modal__sub">
          Les Smyles te permettent de débloquer des recettes, des ADN et des voix
          d'artistes. Tu en gagnes en explorant, en publiant et en revenant.
        </p>

        <!-- Lot 3 — Brique 5 : achat par carte (Stripe Checkout). Le crédit
             arrive par le serveur (webhook signé), jamais depuis cette page. -->
        <div class="credits-buy" id="creditsBuyBlock">
          <div class="credits-modal__packs" id="creditsPacks"></div>
          <p class="credits-buy__tva" id="creditsTva" hidden></p>
          <label class="credits-buy__consent">
            <input type="checkbox" id="creditsConsent" />
            <span>Je demande la fourniture immédiate du contenu numérique et je renonce à mon droit de rétractation.</span>
          </label>
          <p class="credits-buy__legal">En payant, tu acceptes les
            <a href="/legal#cgv-smyles" target="_blank" rel="noopener">conditions de vente des Smyles</a>.
            Paiement sécurisé par Stripe : WATT ne voit jamais ta carte.</p>
          <button type="button" class="credits-buy__pay" id="creditsPayBtn" disabled>Choisis un pack</button>
        </div>

        <div class="credits-modal__earn">
          <button type="button" class="credits-earn" id="creditsEarnStreak">
            <span class="credits-earn__ico" aria-hidden="true">🔥</span>
            <span class="credits-earn__txt">
              <strong>Récompense du jour</strong>
              <em>Reviens chaque jour pour en gagner</em>
            </span>
          </button>
          <button type="button" class="credits-earn" id="creditsEarnRef">
            <span class="credits-earn__ico" aria-hidden="true">🤝</span>
            <span class="credits-earn__txt">
              <strong>Parrainage</strong>
              <em>Invite un ami, vous gagnez tous les deux</em>
            </span>
          </button>
        </div>
      </div>
    `;

    const _consent = modal.querySelector('#creditsConsent');
    if (_consent) _consent.addEventListener('change', _refreshPayBtn);
    const _pay = modal.querySelector('#creditsPayBtn');
    if (_pay) _pay.addEventListener('click', _payByCard);

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

    // LANCEMENT 2026-07-20 — les deux raccourcis « gagner des Smyles » pointent
    // vers les panneaux existants (streak / parrainage), comme dans la boutique.
    // Lot 1 : série quotidienne cachée → on retire le raccourci.
    if (!(window.WATT_LAUNCH && window.WATT_LAUNCH.serie)) {
      const t = modal.querySelector('#creditsEarnStreak'); if (t) t.remove();
    }
    const _earnStreak = modal.querySelector('#creditsEarnStreak');
    const _earnRef    = modal.querySelector('#creditsEarnRef');
    if (_earnStreak) _earnStreak.addEventListener('click', () => {
      closeCreditsBuyModal();
      if (typeof window.openStreakPanel === 'function') window.openStreakPanel();
    });
    if (_earnRef) _earnRef.addEventListener('click', () => {
      closeCreditsBuyModal();
      if (typeof window.openReferralPanel === 'function') window.openReferralPanel();
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
      const tva = document.getElementById('creditsTva');
      if (tva) {
        tva.hidden = !(data && data.mention_tva);
        tva.textContent = (data && data.mention_tva) || '';
      }
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
            <button type="button" class="credits-pack" data-pack-id="${String(p.id).replace(/[^a-z0-9_]/gi, '')}"
              data-pack-credits="${p.credits}" data-pack-price="${String(priceDisplay).replace(/[<>"'`&]/g, '')}"
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

  // ── Lot 3 — sélection du pack + paiement par carte ─────────────────────
  let _selectedPack = null;

  function _refreshPayBtn() {
    const btn = document.getElementById('creditsPayBtn');
    const consent = document.getElementById('creditsConsent');
    if (!btn) return;
    const ok = !!_selectedPack && !!(consent && consent.checked);
    btn.disabled = !ok;
    btn.textContent = _selectedPack
      ? `Payer ${_selectedPack.price} par carte`
      : 'Choisis un pack';
  }

  async function _payByCard() {
    const btn = document.getElementById('creditsPayBtn');
    const consent = document.getElementById('creditsConsent');
    if (!_selectedPack || !consent || !consent.checked || !btn) return;
    btn.disabled = true;
    btn.textContent = 'Ouverture du paiement…';
    try {
      const out = await apiFetch('/credits/checkout', {
        method: 'POST',
        json: { pack_id: _selectedPack.id, renonce_retractation: true },
      });
      if (out && out.url && /^https:\/\/checkout\.stripe\.com\//.test(out.url)) {
        window.location.href = out.url;
        return;
      }
      throw new Error('url');
    } catch (err) {
      const s = err && err.status;
      _toast(s === 503
        ? 'Le paiement par carte n\'est pas encore disponible.'
        : 'Impossible d\'ouvrir le paiement. Réessaie dans un instant.', 'error');
      _refreshPayBtn();
    }
  }

  // ── Achat d'un pack ────────────────────────────────────────────────────
  // S-11 (2026-09-04, annexe A §M5) — l'appel POST /credits/grant est RETIRÉ.
  // C'était le stub « V1 gratuit » d'avant le gate is_official : depuis, il
  // répond 403 à tout compte normal, donc le clic « Acheter » ne pouvait que
  // finir en « Échec de l'opération ». Tant que Stripe n'est pas branché, on
  // dit la vérité au lieu d'échouer. Le vrai crédit passera par un webhook
  // Stripe signé, vérifié côté serveur — jamais par un appel direct du front.
  async function buyPack(btn) {
    if (!btn || btn.classList.contains('is-loading')) return;
    const credits = parseInt(btn.getAttribute('data-pack-credits'), 10);
    if (!credits || credits <= 0) return;
    // Lot 3 : un clic SÉLECTIONNE le pack ; le paiement part du bouton
    // « Payer », seulement une fois la case de renonciation cochée.
    document.querySelectorAll('#creditsPacks .credits-pack').forEach((b) => b.classList.remove('is-selected'));
    btn.classList.add('is-selected');
    _selectedPack = {
      id: btn.getAttribute('data-pack-id'),
      price: btn.getAttribute('data-pack-price') || '',
    };
    _refreshPayBtn();
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
    // F3-3 — INTENTION DE PAYER. Stripe n'est pas branche : ce clic est la
    // seule mesure disponible de la disposition reelle a payer, et c'est
    // l'un des 5 chiffres qui decideront de la suite de la beta.
    try {
      if (window.SmyleTrack && typeof window.SmyleTrack.event === 'function') {
        window.SmyleTrack.event('topup_click', { source: 'credits-buy' });
      }
    } catch (_) { /* la mesure ne bloque jamais l'ouverture */ }
    // S-11 (2026-09-04, annexe A §M5) — garde APRÈS la mesure : le clic est
    // compté (intention de payer), mais on n'ouvre pas une modale qui
    // promettrait un achat impossible tant que Stripe n'est pas branché.
    // Défensif : drapeau absent → masqué.
    if (!(window.WATT_LAUNCH && window.WATT_LAUNCH.achatSmyles)) {
      _toast('Tes Smyles se gagnent en explorant, en publiant et en jouant.', 'info');
      return;
    }
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

  // Lot 3 — retour de la page de paiement Stripe (?achat=ok / ?achat=annule).
  // Rien n'est crédité ici : le serveur crédite à la réception du webhook
  // signé. On prévient simplement et on rafraîchit le solde quelques fois.
  function _handleReturn() {
    let q;
    try { q = new URLSearchParams(window.location.search).get('achat'); } catch (_) { return; }
    if (!q) return;
    if (q === 'ok') {
      _toast('Paiement reçu — tes Smyles arrivent dans quelques secondes.', 'success');
      [3000, 8000, 15000].forEach((ms) => setTimeout(() => {
        try { if (window.SmyleBalance && window.SmyleBalance.refresh) window.SmyleBalance.refresh(); } catch (_) {}
      }, ms));
    } else if (q === 'annule') {
      _toast('Paiement annulé — aucun montant n\'a été prélevé.', 'info');
    }
    try {
      const u = new URL(window.location.href);
      u.searchParams.delete('achat');
      window.history.replaceState(null, '', u.pathname + u.search + u.hash);
    } catch (_) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _handleReturn);
  else _handleReturn();

  // Expositions globales
  window.openCreditsBuyModal  = openCreditsBuyModal;
  window.closeCreditsBuyModal = closeCreditsBuyModal;
  window._creditsBuyPack      = buyPack;
})();
