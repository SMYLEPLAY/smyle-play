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
 *   (Lot J) message honnête : bonus d'inscription, parrainage et ventes.
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
    #creditsPacks { display: block; padding-top: 4px; }
    .credits-libre__lbl { display: block; font-size: 13px; font-weight: 700; color: rgba(255,255,255,.9); margin-bottom: 8px; }
    .credits-libre__row { display: flex; gap: 8px; align-items: stretch; }
    .credits-libre__input { flex: 1; min-width: 0; text-align: center; font-size: 26px; font-weight: 800; color: #ffd700; background: rgba(255,215,0,.06); border: 1px solid rgba(255,215,0,.35); border-radius: 12px; padding: 10px; -moz-appearance: textfield; }
    .credits-libre__input::-webkit-outer-spin-button, .credits-libre__input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    .credits-libre__input:focus { outline: 2px solid #ffd700; outline-offset: 1px; }
    .credits-libre__step { width: 48px; border-radius: 12px; border: 1px solid rgba(255,215,0,.35); background: rgba(255,215,0,.08); color: #ffd700; font-size: 22px; font-weight: 800; cursor: pointer; }
    .credits-libre__chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 12px; }
    .credits-libre__chip { flex: 1 1 0; min-width: 64px; padding: 8px 6px; border-radius: 999px; border: 1px solid rgba(255,215,0,.3); background: transparent; color: #ffe680; font-weight: 700; font-size: 13px; cursor: pointer; }
    .credits-libre__chip.is-selected { background: #ffd700; color: #1a1206; border-color: #ffd700; }
    .credits-libre__prix { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 10px; border-radius: 12px; background: rgba(255,255,255,.04); }
    .credits-libre__prix strong { font-size: 28px; color: #fff; white-space: nowrap; }
    .credits-libre__prix span { font-size: 13px; color: rgba(255,255,255,.82); text-align: center; }
    .credits-libre__astuce { margin: 8px 0 0; font-size: 13px; color: #ffe680; text-align: center; }
    .credits-libre__grille { margin: 10px 0 4px; font-size: 13px; color: rgba(255,255,255,.85); }
    .credits-libre__grille summary { cursor: pointer; color: #cc88ff; }
    .credits-libre__grille ul { list-style: none; padding: 0; margin: 8px 0; }
    .credits-libre__grille li { display: grid; grid-template-columns: 1fr auto 48px; gap: 8px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,.06); }
    .credits-libre__grille em { color: #ffd700; font-style: normal; text-align: right; }
    .credits-libre__grille p { margin: 6px 0 0; font-size: 12px; color: rgba(255,255,255,.75); }
    .credits-pack.is-selected { border-color: #ffd700; box-shadow: 0 0 0 2px rgba(255,215,0,.45); }
    .credits-modal__packs { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; margin: 14px 0 10px; }
    .credits-buy__tva { margin: 0 0 8px; font-size: 12px; color: rgba(255,255,255,.82); }
    .credits-buy__consent { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; line-height: 1.45; color: rgba(255,255,255,.85); cursor: pointer; margin: 6px 0; }
    .credits-buy__consent input { width: 18px; height: 18px; flex: 0 0 18px; margin-top: 1px; accent-color: #ffd700; }
    .credits-buy__legal { font-size: 12px; color: rgba(255,255,255,.82); margin: 6px 0 12px; }
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
          Les Smyles te permettent de débloquer des sons, des images et leurs
          recettes. Tu en reçois 50 à l'inscription et 20 par ami parrainé.
          Les Smyles achetés servent uniquement sur WATT : ils ne sont ni
          remboursables ni convertibles en euros.
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
          <label class="credits-buy__consent">
            <input type="checkbox" id="creditsMajeur" />
            <span>J'ai 18 ans ou plus.</span>
          </label>
          <p class="credits-buy__legal">En payant, tu acceptes les
            <a href="/legal#cgv-smyles" target="_blank" rel="noopener">conditions de vente des Smyles</a>.
            Paiement sécurisé par Stripe : WATT ne voit jamais ta carte.</p>
          <button type="button" class="credits-buy__pay" id="creditsPayBtn" disabled>Choisis ton nombre de Smyles</button>
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
    const _majeur = modal.querySelector('#creditsMajeur');
    if (_majeur) _majeur.addEventListener('change', _refreshPayBtn);
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
      // Étape 2 : paiement non proposé à ce compte (clé Stripe de test hors
      // admin, ou achat par carte suspendu) → on le dit, sans bouton.
      const _ouvert = !!(data && data.paiement_carte);
      ['creditsConsent', 'creditsPayBtn'].forEach((id) => {
        const el = document.getElementById(id);
        const box = el && (el.closest('label') || el);
        if (box) box.style.display = _ouvert ? '' : 'none';
      });
      const _legal = document.querySelector('#creditsBuyBlock .credits-buy__legal');
      if (_legal) _legal.style.display = _ouvert ? '' : 'none';
      let _msg = document.getElementById('creditsBuyMsg');
      if (!_ouvert) {
        if (!_msg) {
          _msg = document.createElement('p');
          _msg.id = 'creditsBuyMsg';
          _msg.className = 'credits-buy__legal';
          const blk = document.getElementById('creditsBuyBlock');
          if (blk) blk.appendChild(_msg);
        }
        _msg.textContent = (data && data.message) || "L'achat par carte arrive bientôt.";
        _msg.style.display = '';
      } else if (_msg) {
        _msg.style.display = 'none';
      }
      const tva = document.getElementById('creditsTva');
      if (tva) {
        tva.hidden = !(data && data.mention_tva);
        tva.textContent = (data && data.mention_tva) || '';
      }
      if (packs.length === 0) {
        container.innerHTML = '<div class="credits-modal__error">Achat de Smyles indisponible pour le moment.</div>';
        return;
      }

      // 02/11/2026 — ACHAT AU MONTANT LIBRE : l'acheteur tape son nombre de
      // Smyles ; le prix vient de la grille du serveur (le serveur recalcule
      // tout au paiement : ce qui est affiché ici n'est qu'un aperçu).
      _grille = {
        tranches: (data.tranches || []).map((t) => ({ seuil: +t.a_partir_de, m: +t.prix_millieme, remise: +t.remise_pct || 0 })),
        min: +data.min_smyles || 100, max: +data.max_smyles || 50000, pas: +data.pas_smyles || 10,
      };
      if (!_grille.tranches.length) {
        container.innerHTML = '<div class="credits-modal__error">Aucun prix disponible pour le moment.</div>';
        return;
      }
      const chips = packs.map((p) => {
        const n = parseInt(p.credits, 10) || 0;
        return `<button type="button" class="credits-libre__chip" data-qty="${n}">${n.toLocaleString('fr-FR')}</button>`;
      }).join('');
      const grilleHtml = _grille.tranches.map((t, i) => {
        const fin = (_grille.tranches[i + 1] ? _grille.tranches[i + 1].seuil - 1 : _grille.max);
        return `<li><span>${t.seuil.toLocaleString('fr-FR')} à ${fin.toLocaleString('fr-FR')}</span>`
          + `<b>${_unitFr(t.m)}</b>${t.remise ? `<em>−${t.remise} %</em>` : '<em></em>'}</li>`;
      }).join('');
      container.innerHTML = `
        <div class="credits-libre">
          <label class="credits-libre__lbl" for="creditsQty">Combien de Smyles veux-tu ?</label>
          <div class="credits-libre__row">
            <button type="button" class="credits-libre__step" data-step="-1" aria-label="Moins">−</button>
            <input id="creditsQty" class="credits-libre__input" type="number" inputmode="numeric"
              min="${_grille.min}" max="${_grille.max}" step="${_grille.pas}" value="${_qtyInitiale()}" />
            <button type="button" class="credits-libre__step" data-step="1" aria-label="Plus">+</button>
          </div>
          <div class="credits-libre__chips">${chips}</div>
          <div class="credits-libre__prix" aria-live="polite">
            <strong id="creditsPrix"></strong>
            <span id="creditsUnit"></span>
          </div>
          <p class="credits-libre__astuce" id="creditsAstuce" hidden></p>
          <details class="credits-libre__grille">
            <summary>Voir la grille des prix</summary>
            <ul>${grilleHtml}</ul>
            <p>Le prix de ta tranche s'applique à tous les Smyles de l'achat. De ${_grille.min.toLocaleString('fr-FR')} à ${_grille.max.toLocaleString('fr-FR')} Smyles par paiement.</p>
          </details>
        </div>`;
      const qty = container.querySelector('#creditsQty');
      qty.addEventListener('input', () => _majPrix(false));
      qty.addEventListener('change', () => _majPrix(true));
      container.querySelectorAll('.credits-libre__chip').forEach((b) => b.addEventListener('click', () => {
        qty.value = b.getAttribute('data-qty'); _majPrix(true);
      }));
      container.querySelectorAll('.credits-libre__step').forEach((b) => b.addEventListener('click', () => {
        const v = parseInt(qty.value, 10) || _grille.min;
        const pasClic = v >= 10000 ? 1000 : v >= 1000 ? 100 : _grille.pas * 5;
        qty.value = v + (parseInt(b.getAttribute('data-step'), 10) * pasClic); _majPrix(true);
      }));
      _majPrix(true);
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

  // ── 02/11/2026 — montant libre : aperçu du prix ───────────────────────
  let _grille = null;
  let _qtyDemandee = 0;     // Smyles manquants passés à l'ouverture (achat bloqué)

  function _unitFr(m) {      // millièmes d'euro → « 0,065 € »
    return (m / 1000).toFixed(3).replace(/0+$/, '').replace(/\.$/, '').replace('.', ',') + ' €';
  }
  function _eurosFr(cents) {
    return (cents / 100).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }
  function _tranche(n) {
    let t = _grille.tranches[0];
    _grille.tranches.forEach((x) => { if (n >= x.seuil) t = x; });
    return t;
  }
  function _centimes(n) { return Math.round(n * _tranche(n).m / 10); }
  function _arrondi(n) {
    const p = _grille.pas;
    n = Math.ceil((parseInt(n, 10) || 0) / p) * p;
    return Math.min(_grille.max, Math.max(_grille.min, n));
  }
  function _qtyInitiale() {
    if (_qtyDemandee > 0) return _arrondi(_qtyDemandee);
    return _arrondi(1000);
  }
  function _majPrix(normaliser) {
    const input = document.getElementById('creditsQty');
    if (!input || !_grille) return;
    let n = parseInt(input.value, 10) || 0;
    if (normaliser) { n = _arrondi(n); input.value = n; }
    const ok = n >= _grille.min && n <= _grille.max && n % _grille.pas === 0;
    const prixEl = document.getElementById('creditsPrix');
    const unitEl = document.getElementById('creditsUnit');
    const astuce = document.getElementById('creditsAstuce');
    document.querySelectorAll('.credits-libre__chip').forEach((b) =>
      b.classList.toggle('is-selected', parseInt(b.getAttribute('data-qty'), 10) === n));
    if (!ok) {
      prixEl.textContent = '—';
      unitEl.textContent = `Entre ${_grille.min.toLocaleString('fr-FR')} et ${_grille.max.toLocaleString('fr-FR')} Smyles, par multiples de ${_grille.pas}.`;
      if (astuce) astuce.hidden = true;
      _selectedPack = null; _refreshPayBtn();
      return;
    }
    const t = _tranche(n);
    const cents = _centimes(n);
    prixEl.textContent = _eurosFr(cents);
    unitEl.textContent = `${n.toLocaleString('fr-FR')} Smyles · ${_unitFr(t.m)} / Smyle` + (t.remise ? ` · −${t.remise} %` : '');
    // Astuce : la tranche suivante est proche → on le dit (même prix ou presque).
    const idx = _grille.tranches.indexOf(t);
    const suiv = _grille.tranches[idx + 1];
    if (astuce) {
      if (suiv && suiv.seuil - n <= Math.max(n * 0.5, 200)) {
        const ajout = suiv.seuil - n;
        const diff = _centimes(suiv.seuil) - cents;
        astuce.textContent = diff <= 0
          ? `Astuce : ${suiv.seuil.toLocaleString('fr-FR')} Smyles coûtent moins cher (${_eurosFr(_centimes(suiv.seuil))}) — tous à ${_unitFr(suiv.m)}.`
          : `Astuce : ajoute ${ajout.toLocaleString('fr-FR')} Smyles (+${_eurosFr(diff)}) et tous passent à ${_unitFr(suiv.m)}.`;
        astuce.hidden = false;
      } else {
        astuce.hidden = true;
      }
    }
    _selectedPack = { id: 'pack_' + n, price: _eurosFr(cents) };
    _refreshPayBtn();
  }

  // ── Lot 3 — sélection du pack + paiement par carte ─────────────────────
  let _selectedPack = null;

  function _refreshPayBtn() {
    const btn = document.getElementById('creditsPayBtn');
    const consent = document.getElementById('creditsConsent');
    const majeur = document.getElementById('creditsMajeur');
    if (!btn) return;
    const ok = !!_selectedPack && !!(consent && consent.checked) && !!(majeur && majeur.checked);
    btn.disabled = !ok;
    btn.textContent = _selectedPack
      ? `Payer ${_selectedPack.price} par carte`
      : 'Choisis ton nombre de Smyles';
  }

  async function _payByCard() {
    const btn = document.getElementById('creditsPayBtn');
    const consent = document.getElementById('creditsConsent');
    const majeur = document.getElementById('creditsMajeur');
    if (!_selectedPack || !consent || !consent.checked || !majeur || !majeur.checked || !btn) return;
    btn.disabled = true;
    btn.textContent = 'Ouverture du paiement…';
    try {
      const out = await apiFetch('/credits/checkout', {
        method: 'POST',
        json: { pack_id: _selectedPack.id, renonce_retractation: true, majeur: true },
      });
      if (out && out.url && /^https:\/\/checkout\.stripe\.com\//.test(out.url)) {
        window.location.href = out.url;
        return;
      }
      throw new Error('url');
    } catch (err) {
      const s = err && err.status;
      // Lot L : le serveur explique pourquoi (email à confirmer, majorité…).
      const d = err && err.body && err.body.detail;
      _toast(s === 503
        ? 'Le paiement par carte n\'est pas encore disponible.'
        : (s === 422 && typeof d === 'string') ? d
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
  // opts.manque : Smyles qui manquent pour l'achat en cours → pré-remplis.
  function openCreditsBuyModal(opts) {
    _qtyDemandee = (opts && parseInt(opts.manque, 10) > 0) ? parseInt(opts.manque, 10) : 0;
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
      _toast("Tes Smyles : 50 offerts à l'inscription, +20 pour toi et pour ton ami à chaque parrainage, et ceux que tu gagnes quand on débloque tes créations.", 'info');
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
