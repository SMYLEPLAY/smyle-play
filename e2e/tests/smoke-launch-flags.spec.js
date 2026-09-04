// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — MODE_LANCEMENT (K-05, annexe B §4).
//
// Le mode lancement masque des mécaniques encore vides (packs, troc, revente,
// voix, paliers). La règle produit : RIEN n'est supprimé — chaque point
// d'entrée est gaté sur `window.WATT_LAUNCH.<item>`, servi par le JS dynamique
// `GET /ui/core/launch-flags.js` (source de vérité backend), avec un repli
// statique « tout masqué » si l'endpoint ne répond pas.
//
// Ce smoke prouve les DEUX sens, sinon un masquage en dur passerait pour un
// drapeau qui marche :
//   1. drapeaux réels de l'environnement (packs/troc masqués en CI) → aucun
//      point d'entrée « Ouvrir un pack », et aucun appel à /trades/offers/me ;
//   2. drapeaux rallumés (le JS de drapeaux est remplacé par `page.route`) →
//      le point d'entrée réapparaît, sans redéploiement.
//
// Le menu utilisateur n'existe qu'authentifié : on crée un vrai compte via
// l'API et on injecte le JWT, comme smoke-auth / smoke-purchase.
// ─────────────────────────────────────────────────────────────────────────────

const TOKEN_KEY = 'smyle_api_token';
const FLAGS_URL = '**/ui/core/launch-flags.js';

async function _authedToken(request) {
  const email = `e2e-flags-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
  const password = 'Test123456';
  const reg = await request.post('/auth/register', { data: { email, password, accept_terms: true, age_confirmed: true } });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);
  const login = await request.post('/auth/login', { data: { email, password } });
  expect(login.status(), `login: ${await login.text()}`).toBe(200);
  const { access_token } = await login.json();
  expect(access_token, 'access_token présent').toBeTruthy();
  return access_token;
}

async function _bootAuthed(page, token) {
  await page.addInitScript(([key, tok]) => {
    try { localStorage.setItem(key, tok); } catch (e) { /* */ }
  }, [TOKEN_KEY, token]);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
}

test('cas 1 — packs masqués : pas d’entrée « Ouvrir un pack », pas d’appel troc', async ({ page, request }) => {
  const token = await _authedToken(request);

  // Aucune requête ne doit partir vers l'API troc tant que l'item est masqué.
  const trocCalls = [];
  page.on('request', (r) => {
    if (r.url().includes('/trades/offers/me')) trocCalls.push(r.url());
  });

  await _bootAuthed(page, token);

  // Les drapeaux servis par l'environnement sont bien chargés (objet présent).
  const flags = await page.evaluate(() => window.WATT_LAUNCH);
  expect(flags, 'window.WATT_LAUNCH installé').toBeTruthy();
  expect(flags.packs, 'packs masqué par défaut en CI').toBeFalsy();
  expect(flags.troc, 'troc masqué par défaut en CI').toBeFalsy();

  // Le menu utilisateur ne propose pas « Ouvrir un pack ».
  await page.locator('#authArea .user-badge').click();
  await expect(page.locator('#user-menu-open-pack')).toHaveCount(0);

  // Et la fonction reste sans effet si un autre module l'appelle (garde interne).
  await page.evaluate(() => window.openPackModal && window.openPackModal());
  await expect(page.locator('#packModal')).toHaveCount(0);

  expect(trocCalls, 'aucun appel /trades/offers/me quand le troc est masqué').toEqual([]);
});

test('cas 2 — drapeaux rallumés : l’entrée « Ouvrir un pack » réapparaît', async ({ page, request }) => {
  const token = await _authedToken(request);

  // On remplace le JS de drapeaux servi par l'API : c'est exactement ce que
  // fait `SHOW_PACKS=True` côté backend, sans toucher à l'environnement CI.
  await page.route(FLAGS_URL, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: 'window.WATT_LAUNCH = { paliers: true, resale: true, packs: true, voix: true, troc: true, thePlan: true };',
    });
  });

  await _bootAuthed(page, token);

  const flags = await page.evaluate(() => window.WATT_LAUNCH);
  expect(flags.packs, 'packs rallumé par le drapeau').toBe(true);

  await page.locator('#authArea .user-badge').click();
  await expect(page.locator('#user-menu-open-pack')).toBeVisible();
});
