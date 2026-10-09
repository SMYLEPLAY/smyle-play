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
  await page.addInitScript(([tokenKey, tok, streakKey]) => {
    try { localStorage.setItem(tokenKey, tok); } catch (e) { /* */ }
    try { sessionStorage.setItem(streakKey, '1'); } catch (e) { /* */ }
  }, [TOKEN_KEY, token, STREAK_NUDGE_KEY]);
}

/**
 * Configuration « jour J » (FEATURE_SELL_GATE allumé, cf. e2e.yml) : pour
 * METTRE EN VENTE, un créateur doit avoir N abonnés réels (emails vérifiés).
 * Ce helper donne au vendeur de test exactement les abonnés qui lui manquent,
 * comme dans la vraie vie : profil publié, puis N comptes qui le suivent.
 * Sans seuil (configuration actuelle), il ne fait RIEN.
 * Prérequis : le vendeur a déjà un nom d'artiste (PATCH /users/me).
 *
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} token JWT du vendeur
 */
async function qualifierPourVendre(request, token) {
  const { expect } = require('@playwright/test');
  const auth = { Authorization: `Bearer ${token}` };
  const r = await request.get('/me/droit-de-vendre', { headers: auth });
  expect(r.status(), `droit-de-vendre: ${await r.text()}`).toBe(200);
  const etat = await r.json();
  if (etat.peut_vendre) return etat;

  const pub = await request.post('/watt/me/profile/publish', { headers: auth });
  expect(pub.status(), `publication du profil: ${await pub.text()}`).toBe(200);
  const { artistSlug } = await pub.json();

  for (let i = 0; i < (etat.manquants || 0); i += 1) {
    const email = `e2e-abonne-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
    const password = 'Test123456';
    const reg = await request.post('/auth/register', {
      data: { email, password, accept_terms: true, age_confirmed: true },
    });
    expect(reg.status(), `abonné register: ${await reg.text()}`).toBe(201);
    const login = await request.post('/auth/login', { data: { email, password } });
    expect(login.status(), `abonné login: ${await login.text()}`).toBe(200);
    const { access_token } = await login.json();
    const f = await request.post(`/watt/artists/${artistSlug}/follow`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect([200, 201], `follow: ${await f.text()}`).toContain(f.status());
  }
  const apres = await (await request.get('/me/droit-de-vendre', { headers: auth })).json();
  expect(apres.peut_vendre, `seuil de vente atteint : ${JSON.stringify(apres)}`).toBe(true);
  return apres;
}

module.exports = { TOKEN_KEY, STREAK_NUDGE_KEY, bootSessionAuthentifiee, qualifierPourVendre };
