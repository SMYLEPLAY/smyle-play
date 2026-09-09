// @ts-check
// ─────────────────────────────────────────────────────────────────────────────
// Helpers partagés des smokes AUTHENTIFIÉS (D10, 2026-09-08).
//
// Ce fichier n'est pas un spec : le `testMatch` par défaut de Playwright ne
// ramasse que `*.spec.js` / `*.test.js`, il ne sera donc jamais exécuté comme
// un test — il est seulement `require()` par ceux qui en ont besoin.
//
// Pourquoi il existe : la parade contre l'auto-ouverture du rappel quotidien
// était écrite en dur dans smoke-launch-flags.spec.js et recopiée dans
// smoke-purchase-real.spec.js. Tout nouveau smoke authentifié qui clique dans
// l'en-tête heurtait l'overlay #streakModal — un échec déterministe, coûteux à
// diagnostiquer, que chacun redécouvrait pour son compte.
// ─────────────────────────────────────────────────────────────────────────────

// Le JWT vit dans localStorage (cf. ui/core/api.js + ui/modals/auth.js) : au
// boot, auth.js le lit, appelle GET /users/me et rend l'UI connectée.
const TOKEN_KEY = 'smyle_api_token';

// Drapeau de session que l'app utilise ELLE-MÊME comme garde-fou du rappel
// « Récompense du jour » (ui/modals/auth.js, `_maybeNudgeStreak`).
const STREAK_NUDGE_KEY = 'smyle_streak_autoopened';

// Drapeau « déjà vu » de l'onboarding premier-run (ui/core/onboarding.js,
// rechargé sur l'accueil par N-03, 09/09). Sans lui, sur un compte NEUF la
// modale #obWelcome (position:fixed; inset:0; z-index:1400) s'ouvre à t+0,9 s
// et recouvre l'en-tête ET le tiroir d'achat (.pd-overlay, z-index 1300) :
// même échec déterministe que #streakModal. L'onboarding est hors du périmètre
// de ces smokes ; on pose le drapeau que l'app utilise elle-même.
const ONBOARDING_SEEN_KEY = 'smyle_onboarded_v1';

/**
 * Prépare une session connectée AVANT le boot des scripts de la page :
 *   1. pose le JWT, comme le ferait une vraie connexion ;
 *   2. pose le verrou de session du rappel quotidien.
 *
 * Sur le point 2 : `ui/modals/auth.js` planifie `_maybeNudgeStreak()` à
 * t+1,2 s après le boot. Sur un compte NEUF, `GET /streak/me` répond
 * `can_checkin_today: true` → la « Récompense du jour » s'ouvre TOUTE SEULE, et
 * #streakModal est un overlay `position:fixed; inset:0; z-index:1000` qui
 * recouvre la barre d'en-tête : tout clic sur `#authArea .user-badge` est alors
 * intercepté (échec déterministe, pas une flakiness). smoke-purchase y échappe
 * seulement parce que .pd-overlay est en z-index 1300. On pose donc le drapeau
 * que l'app utilise elle-même pour ne proposer la récompense qu'une fois par
 * session : le rappel quotidien est hors du périmètre de ces smokes, aucune de
 * leurs assertions n'en dépend, et il ne doit surtout pas créditer de Smyles
 * pendant une mesure de solde.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} token JWT obtenu par /auth/login
 */
async function bootSessionAuthentifiee(page, token) {
  await page.addInitScript(([tokenKey, tok, streakKey, onboardingKey]) => {
    try { localStorage.setItem(tokenKey, tok); } catch (e) { /* */ }
    try { sessionStorage.setItem(streakKey, '1'); } catch (e) { /* */ }
    try { localStorage.setItem(onboardingKey, '1'); } catch (e) { /* */ }
  }, [TOKEN_KEY, token, STREAK_NUDGE_KEY, ONBOARDING_SEEN_KEY]);
}

module.exports = { TOKEN_KEY, STREAK_NUDGE_KEY, ONBOARDING_SEEN_KEY, bootSessionAuthentifiee };
