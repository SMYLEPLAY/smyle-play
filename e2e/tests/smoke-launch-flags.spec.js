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
//      point d'entrée « Ouvrir un pack », la fonction reste sans effet, et
//      aucun appel à /trades/offers/me ;
//   2. drapeaux rallumés (le JS de drapeaux est remplacé par `page.route`) →
//      le point d'entrée réapparaît ET la garde interne s'efface, sans
//      redéploiement.
//
// Le menu utilisateur n'existe qu'authentifié : on crée un vrai compte via
// l'API et on injecte le JWT, comme smoke-auth / smoke-purchase.
// ─────────────────────────────────────────────────────────────────────────────

const TOKEN_KEY = 'smyle_api_token';
// Drapeau de session que l'app utilise ELLE-MÊME comme garde-fou du rappel
// « Récompense du jour » (ui/modals/auth.js, `_maybeNudgeStreak`).
const STREAK_NUDGE_KEY = 'smyle_streak_autoopened';
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
  await page.addInitScript(([tokenKey, tok, streakKey]) => {
    try { localStorage.setItem(tokenKey, tok); } catch (e) { /* */ }
    // ui/modals/auth.js planifie `_maybeNudgeStreak()` à t+1,2 s après le
    // boot. Sur un compte NEUF, `GET /streak/me` répond `can_checkin_today:
    // true` → la « Récompense du jour » s'ouvre TOUTE SEULE, et #streakModal
    // est un overlay `position:fixed; inset:0; z-index:1000` qui recouvre la
    // barre d'en-tête : tout clic sur `#authArea .user-badge` est alors
    // intercepté (échec déterministe, pas une flakiness). smoke-purchase y
    // échappe seulement parce que .pd-overlay est en z-index 1300.
    // On pose donc le drapeau de session que l'app utilise elle-même pour ne
    // proposer la récompense qu'une fois par session : le rappel quotidien
    // est hors du périmètre de ce smoke et aucune assertion de drapeau de
    // lancement n'en dépend.
    try { sessionStorage.setItem(streakKey, '1'); } catch (e) { /* */ }
  }, [TOKEN_KEY, token, STREAK_NUDGE_KEY]);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
}

// Ouvre le menu utilisateur par un VRAI clic, et prouve qu'il est ouvert ET
// peuplé : sans ce contrôle, « l'entrée pack est absente » passerait aussi
// quand le menu entier ne s'est pas rendu — l'assertion négative du cas 1
// serait vide de sens.
async function _openUserMenu(page) {
  await page.locator('#authArea .user-badge').click();
  const menu = page.locator('#smyle-user-menu');
  await expect(menu, 'le menu utilisateur est ouvert').toHaveClass(/\bopen\b/);
  await expect(
    menu.locator('.user-menu-item', { hasText: 'Récompense du jour' }),
    'repère non gaté : le menu est bien rendu',
  ).toHaveCount(1);
  return menu;
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

  // Le menu utilisateur s'ouvre, mais ne propose pas « Ouvrir un pack ».
  const menu = await _openUserMenu(page);
  await expect(menu.locator('#user-menu-open-pack')).toHaveCount(0);

  // Et la fonction reste sans effet si un autre module l'appelle (garde
  // interne) : ni modale, ni appel /packs/mystery.
  await page.evaluate(() => { if (window.openPackModal) window.openPackModal(); });
  await expect(page.locator('#packModal'), 'aucune modale pack quand l’item est masqué').toHaveCount(0);

  expect(trocCalls, 'aucun appel /trades/offers/me quand le troc est masqué').toEqual([]);
});

test('cas 2 — drapeaux rallumés : l’entrée « Ouvrir un pack » réapparaît', async ({ page, request }) => {
  const token = await _authedToken(request);

  // On remplace le JS de drapeaux servi par l'API : c'est exactement ce que
  // fait `SHOW_PACKS=True` côté backend, sans toucher à l'environnement CI.
  // Posé AVANT toute navigation : le script est chargé en tête de <head>.
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

  const menu = await _openUserMenu(page);
  const entry = menu.locator('#user-menu-open-pack');
  await expect(entry).toBeVisible();
  await expect(entry).toHaveText(/Ouvrir un pack/);

  // Symétrie du cas 1 : la garde interne s'efface aussi — la modale s'ouvre.
  await page.evaluate(() => { if (window.openPackModal) window.openPackModal(); });
  await expect(page.locator('#packModal'), 'la modale pack s’ouvre quand l’item est visible').toHaveCount(1);
});
