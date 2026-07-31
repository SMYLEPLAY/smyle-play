// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE INTERACTION — Drawer d'achat (clic « Débloquer »).
//
// Vérifie le cœur du parcours d'achat côté UI (ui/modals/purchase-drawer.js) :
// l'ouverture du drawer rend titre/prix/bouton, et le clic « Débloquer »
// déclenche bien un POST sur le bon endpoint d'unlock.
//
// Pourquoi on n'achète pas un VRAI prompt : la base CI est vierge et il n'y a
// pas d'API simple pour semer un prompt publié. On intercepte donc l'appel
// d'unlock (mock backend) — ce qui teste précisément le CÂBLAGE clic→API, la
// partie qui casse lors d'une refonte de purchase-drawer.js. Un achat
// DB-réel viendra avec une fixture de seed dédiée.
// ─────────────────────────────────────────────────────────────────────────────

const TOKEN_KEY = 'smyle_api_token';
const FAKE_PROMPT_ID = '11111111-1111-1111-1111-111111111111';

async function _authedToken(request) {
  const email = `e2e-buy-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
  const password = 'Test123456';
  const reg = await request.post('/auth/register', { data: { email, password, accept_terms: true, age_confirmed: true } });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);
  const login = await request.post('/auth/login', { data: { email, password } });
  expect(login.status(), `login: ${await login.text()}`).toBe(200);
  const { access_token } = await login.json();
  expect(access_token).toBeTruthy();
  return access_token;
}

test('drawer d’achat : rendu + clic « Débloquer » appelle l’unlock', async ({ page, request }) => {
  const token = await _authedToken(request);

  // Intercepte l'unlock (mock backend) — on teste le câblage, pas le débit réel.
  let unlockUrl = null;
  await page.route('**/unlocks/prompts/**', async (route) => {
    unlockUrl = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, perk_applied: false }),
    });
  });

  await page.addInitScript(([key, tok]) => {
    try { localStorage.setItem(key, tok); } catch (e) { /* */ }
  }, [TOKEN_KEY, token]);

  await page.goto('/', { waitUntil: 'domcontentloaded' });

  // Le module drawer est chargé par index.html.
  await page.waitForFunction(() => !!(window.PurchaseDrawer && window.PurchaseDrawer.open), null, { timeout: 15000 });

  // Ouvre le drawer pour un prompt (type 'son'), prix 5.
  await page.evaluate((id) => {
    window.PurchaseDrawer.open({ type: 'son', id, price: 5, title: 'Smoke Produit' });
  }, FAKE_PROMPT_ID);

  // Rendu attendu.
  await expect(page.locator('#pd-overlay')).toBeVisible();
  await expect(page.locator('#pd-overlay .pd-title')).toHaveText('Smoke Produit');
  await expect(page.locator('#pd-overlay .pd-price')).toHaveText('5');
  const confirm = page.locator('#pd-overlay .pd-confirm');
  await expect(confirm).toBeVisible();

  // Clic « Débloquer » → POST sur /unlocks/prompts/{id}.
  await confirm.click();
  await expect.poll(() => unlockUrl, { timeout: 10000 }).toContain('/unlocks/prompts/' + FAKE_PROMPT_ID);
});
