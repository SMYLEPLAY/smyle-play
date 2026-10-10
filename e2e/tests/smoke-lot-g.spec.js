// @ts-check
// ─────────────────────────────────────────────────────────────────────────────
// SMOKE Lot G — comportements de l'interface modifiés avant l'ouverture :
//   - achat : le prix affiché est envoyé ; s'il a changé (409 prix_change),
//     l'interface demande de confirmer puis rejoue au nouveau prix ;
//   - publication : plus de limite « 6 sons », pochette et version de
//     l'outil obligatoires ;
//   - compte suspendu : la connexion propose l'export et la suppression ;
//   - pied de page : lien « Comment ça marche ».
// ─────────────────────────────────────────────────────────────────────────────
const { test, expect } = require('@playwright/test');
const { bootSessionAuthentifiee } = require('./_helpers');

const PWD = 'Test123456';

async function compte(request) {
  const email = `e2e-lotg-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
  const reg = await request.post('/auth/register', {
    data: { email, password: PWD, accept_terms: true, age_confirmed: true },
  });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);
  const login = await request.post('/auth/login', { data: { email, password: PWD } });
  expect(login.status(), `login: ${await login.text()}`).toBe(200);
  const { access_token: token } = await login.json();
  return { email, token };
}

test('achat : prix changé → confirmation puis achat au nouveau prix', async ({ page, request }) => {
  const c = await compte(request);
  const corps = [];
  await page.route('**/unlocks/prompts/**', async (route) => {
    corps.push(route.request().postDataJSON());
    if (corps.length === 1) {
      await route.fulfill({
        status: 409, contentType: 'application/json',
        body: JSON.stringify({ detail: { code: 'prix_change', message: 'Le prix a changé : 30 Smyles', prix: 30 } }),
      });
    } else {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ perk_applied: false }) });
    }
  });
  const dialogues = [];
  page.on('dialog', (d) => { dialogues.push(d.message()); d.accept(); });
  await bootSessionAuthentifiee(page, c.token);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!(window.PurchaseDrawer && window.smyleAcheter));
  await page.evaluate(() => window.PurchaseDrawer.open({
    type: 'son', id: '22222222-2222-2222-2222-222222222222', price: 15, title: 'Prix mouvant',
  }));
  await page.locator('#pd-overlay .pd-confirm').click();
  await expect.poll(() => corps.length, { timeout: 10000 }).toBe(2);
  expect(corps[0]).toEqual({ prix_attendu: 15 });
  expect(corps[1]).toEqual({ prix_attendu: 30 });
  expect(dialogues[0]).toContain('Le prix a changé : 30 Smyles');
  await expect(page.locator('#pd-overlay')).toHaveCount(0);
});

test('achat : prix changé → refus de confirmer, rien n’est rejoué', async ({ page, request }) => {
  const c = await compte(request);
  let appels = 0;
  await page.route('**/unlocks/prompts/**', async (route) => {
    appels += 1;
    await route.fulfill({
      status: 409, contentType: 'application/json',
      body: JSON.stringify({ detail: { code: 'prix_change', message: 'Le prix a changé : 45 Smyles', prix: 45 } }),
    });
  });
  page.on('dialog', (d) => d.dismiss());
  await bootSessionAuthentifiee(page, c.token);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!(window.PurchaseDrawer && window.smyleAcheter));
  await page.evaluate(() => window.PurchaseDrawer.open({
    type: 'son', id: '33333333-3333-3333-3333-333333333333', price: 15, title: 'Prix mouvant',
  }));
  await page.locator('#pd-overlay .pd-confirm').click();
  await expect(page.locator('#pd-overlay .pd-confirm')).toBeEnabled();
  expect(appels).toBe(1);
});

test('publication : plus de limite « 6 sons », pochette et version obligatoires', async ({ page, request }) => {
  const c = await compte(request);
  await bootSessionAuthentifiee(page, c.token);
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.uploadTrack === 'function');
  const html = await page.content();
  expect(html).not.toContain('6 sons');
  expect(html).not.toContain('dashFreeCounter');
  await expect(page.locator('.dash-topbar-badge')).toHaveCount(0);   // badge « Bêta »
  const pochette = page.locator('#dashCoverDrop').locator('xpath=..').locator('.dash-label').first();
  await expect(pochette).toContainText('Pochette');
  await expect(pochette.locator('.dash-req')).toHaveCount(1);
  await expect(page.locator('#dashPromptModelVersion')).toHaveAttribute('required', '');
});

test('compte suspendu : la connexion propose l’export et la suppression des données', async ({ page }) => {
  await page.route('**/auth/login', (route) => route.fulfill({
    status: 403, contentType: 'application/json',
    body: JSON.stringify({
      detail: 'Compte suspendu. Tu peux encore télécharger tes données ou supprimer ton compte.',
      code: 'compte_suspendu', jeton_rgpd: 'jeton-de-test',
    }),
  }));
  await page.goto('/?auth=login', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.submitLogin === 'function');
  await page.evaluate(() => { if (window.openAuthModal) window.openAuthModal('login'); });
  await page.locator('#login-email').fill('suspendu@smyleplay.example');
  await page.locator('#login-password').fill(PWD);
  await page.evaluate(() => window.submitLogin());
  const msg = page.locator('#authMsg');
  await expect(msg).toContainText('Compte suspendu');
  await expect(msg.getByRole('button', { name: 'Télécharger mes données' })).toBeVisible();
  await expect(msg.getByRole('button', { name: 'Supprimer mon compte' })).toBeVisible();
});

test('pied de page : lien « Comment ça marche »', async ({ page }) => {
  await page.goto('/legal', { waitUntil: 'domcontentloaded' });
  const lien = page.locator('#sp-legal-footer a[href="/comment-ca-marche"]');
  await expect(lien).toHaveText('Comment ça marche');
});
