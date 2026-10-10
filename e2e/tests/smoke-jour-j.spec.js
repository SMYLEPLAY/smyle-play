// @ts-check
const { test, expect } = require('@playwright/test');
const { bootSessionAuthentifiee } = require('./_helpers');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — CONFIGURATION « JOUR J » (1er novembre 2026), Lot E.
//
// Lancé seulement par la variante `jour-j` du workflow e2e.yml
// (E2E_JOUR_J=1), où TOUS les interrupteurs du lancement sont allumés :
// REQUIRE_EMAIL_VERIFIED, FEATURE_PIONEER, FEATURE_MARKET_SMYLES,
// MODE_LANCEMENT, FEATURE_GOAL, FEATURE_QUETES_PARRAINAGE, FEATURE_SELL_GATE
// (+ SELL_GATE_DEPUIS). Les autres smokes tournent AUSSI dans cette
// configuration : ce fichier vérifie en plus que chaque interrupteur produit
// bien son effet visible.
//
// Comptes : un déclencheur posé par le workflow (étape « Fixture jour J ») marque vérifiés les
// comptes « e2e-… » (pas de boîte mail en CI), sauf « e2e-nonverifie-… ».
// ─────────────────────────────────────────────────────────────────────────────

test.skip(!process.env.E2E_JOUR_J, 'variante « jour J » du workflow e2e uniquement');

const PASSWORD = 'Test123456';

function _email(prefix) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
}

async function _inscrire(request, prefix) {
  const email = _email(prefix);
  const reg = await request.post('/auth/register', {
    data: { email, password: PASSWORD, accept_terms: true, age_confirmed: true },
  });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);
  return email;
}

test('email non vérifié : connexion refusée (REQUIRE_EMAIL_VERIFIED)', async ({ request }) => {
  const email = await _inscrire(request, 'e2e-nonverifie');
  const login = await request.post('/auth/login', { data: { email, password: PASSWORD } });
  expect(login.status(), await login.text()).toBe(403);
});

test('interrupteurs publics allumés : objectif 1000 actifs, places Pionnier', async ({ request }) => {
  const objectif = await request.get('/objectif/actifs');
  expect(objectif.status(), 'FEATURE_GOAL').toBe(200);
  const places = await request.get('/pioneer/places');
  expect(places.status(), 'FEATURE_PIONEER').toBe(200);
  // MODE_LANCEMENT : les items masqués le restent (ex. packs).
  const flags = await request.get('/ui/core/launch-flags.js');
  expect(await flags.text()).toContain('"packs": false');
});

test('compte vérifié : connexion, seuil de vente et quêtes actifs', async ({ page, request }) => {
  const email = await _inscrire(request, 'e2e-jourj');
  const login = await request.post('/auth/login', { data: { email, password: PASSWORD } });
  expect(login.status(), await login.text()).toBe(200);
  const { access_token } = await login.json();
  const auth = { Authorization: `Bearer ${access_token}` };

  const vente = await request.get('/me/droit-de-vendre', { headers: auth });
  expect(vente.status()).toBe(200);
  const statut = await vente.json();
  expect(statut.actif, 'FEATURE_SELL_GATE').toBe(true);

  const quetes = await request.post('/referrals/quetes', { headers: auth });
  expect(quetes.status(), 'FEATURE_QUETES_PARRAINAGE').toBe(200);

  // L'interface se charge, connectée, avec tous les interrupteurs allumés.
  const erreurs = [];
  page.on('pageerror', (e) => erreurs.push(String(e)));
  await bootSessionAuthentifiee(page, access_token);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.dash-topbar')).toBeVisible();
  expect(erreurs, 'aucune erreur JavaScript').toEqual([]);
});
