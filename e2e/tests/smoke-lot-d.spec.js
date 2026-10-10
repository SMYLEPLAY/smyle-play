// @ts-check
const { test, expect } = require('@playwright/test');
const { bootSessionAuthentifiee } = require('./_helpers');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — Lot D (conformité DSA / RGPD).
//   - fenêtre bloquante de ré-acceptation des CGU ;
//   - suppression de compte : renonciation (case + SUPPRIMER) exigée ;
//   - signalement : déclaration de bonne foi obligatoire ;
//   - pied de page légal + « Cookies / mesure d'audience » qui rouvre le choix ;
//   - aucun identifiant de mesure posé avant l'accord.
// ─────────────────────────────────────────────────────────────────────────────

const PWD = 'Test123456';

async function compte(request) {
  const email = `e2e-lotd-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
  const reg = await request.post('/auth/register', {
    data: { email, password: PWD, accept_terms: true, age_confirmed: true },
  });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);
  const login = await request.post('/auth/login', { data: { email, password: PWD } });
  const { access_token: token } = await login.json();
  return { email, token, h: { Authorization: `Bearer ${token}` } };
}

function choixMesure(page, valeur) {
  return page.addInitScript((v) => {
    try { if (!localStorage.getItem('smyle_consent')) localStorage.setItem('smyle_consent', v); } catch (e) {}
  }, valeur);
}

test('CGU : fenêtre bloquante tant que la nouvelle version n’est pas acceptée', async ({ page, request }) => {
  const c = await compte(request);
  await choixMesure(page, 'denied');
  await bootSessionAuthentifiee(page, c.token);
  // Simule un compte antérieur aux nouvelles CGU (version non à jour).
  let accepte = false;
  await page.route('**/users/me', async (route) => {
    if (route.request().method() !== 'GET' || accepte) return route.continue();
    const r = await route.fetch();
    const j = await r.json();
    await route.fulfill({ response: r, json: { ...j, cgu_a_jour: false, accepted_terms_version: null } });
  });
  page.on('request', (req) => { if (req.url().endsWith('/users/me/accept-terms')) accepte = true; });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const gate = page.locator('#cgu-gate');
  await expect(gate).toBeVisible({ timeout: 15000 });
  await expect(gate.locator('a[href="/legal#cgu"]')).toBeVisible();
  await expect(page.locator('#cgu-gate-ok')).toBeDisabled();
  await page.locator('#cgu-gate-check').check();
  await page.locator('#cgu-gate-ok').click();
  await expect(gate).toHaveCount(0);
});

test('CGU : une écriture refusée (cgu_a_accepter) rouvre la fenêtre', async ({ page, request }) => {
  const c = await compte(request);
  await choixMesure(page, 'denied');
  await bootSessionAuthentifiee(page, c.token);
  await page.route('**/playlists', (route) => route.fulfill({
    status: 403, contentType: 'application/json',
    body: JSON.stringify({ detail: 'Accepte les nouvelles conditions', code: 'cgu_a_accepter', cgu_version: '2026-11-01' }),
  }));
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.apiFetch === 'function');
  await page.evaluate(() => window.apiFetch('/playlists', { method: 'POST', json: { title: 'x' } }).catch(() => {}));
  await expect(page.locator('#cgu-gate')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#cgu-gate')).toContainText('1er novembre 2026');
});

test('suppression de compte : renonciation exigée, puis compte supprimé', async ({ page, request }) => {
  const c = await compte(request);
  await choixMesure(page, 'denied');
  await bootSessionAuthentifiee(page, c.token);
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.dashDeleteAccount === 'function');
  await page.evaluate(() => window.dashDeleteAccount());
  const ov = page.locator('#dash-del-overlay');
  await expect(ov).toBeVisible();
  await expect(ov).toContainText('gagnés en vendant');
  await expect(ov).toContainText('tous tes Smyles (30)');
  const go = page.locator('#dash-del-go');
  await expect(go).toBeDisabled();
  await page.locator('#dash-del-type').fill('SUPPRIMER');
  await expect(go).toBeDisabled();            // case non cochée
  await page.locator('#dash-del-renonce').check();
  await expect(go).toBeEnabled();
  await go.click();
  await page.waitForURL((u) => new URL(u).pathname === '/', { timeout: 15000 });
  const me = await request.get('/users/me', { headers: c.h });
  expect(me.status()).toBe(401);
  // Le serveur refuse une suppression sans renonciation (vérifié côté API).
  const c2 = await compte(request);
  const r = await request.delete('/users/me', { headers: c2.h });
  expect(r.status()).toBe(422);
});

test('signalement : la déclaration de bonne foi est obligatoire', async ({ page }) => {
  await choixMesure(page, 'denied');
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!window.ReportModal);
  await page.evaluate(() => window.ReportModal.open({ targetType: 'playlist', targetId: '00000000-0000-0000-0000-000000000000', title: 'Ma playlist' }));
  await expect(page.locator('#rm-faith')).toBeVisible();
  await expect(page.locator('#rm-submit')).toBeDisabled();
  await page.locator('#rm-detail').fill('Pochette contrefaite');
  await page.locator('#rm-faith').check();
  await expect(page.locator('#rm-submit')).toBeEnabled();
  await page.locator('#rm-submit').click();
  await expect(page.locator('#rm-overlay')).toHaveCount(0);
});

test('pied de page légal + « Cookies » rouvre le choix ; rien n’est posé avant l’accord', async ({ page }) => {
  await page.goto('/comment-ca-marche', { waitUntil: 'domcontentloaded' });
  const footer = page.locator('#sp-legal-footer');
  await expect(footer).toBeVisible();
  for (const t of ['Mentions légales', 'CGU', 'Confidentialité', 'Cookies / mesure d’audience', 'Contact']) {
    await expect(footer).toContainText(t);
  }
  // Bannière affichée, aucun identifiant de mesure tant qu'on n'a pas choisi.
  await expect(page.locator('#smyle-consent')).toBeVisible();
  const avant = await page.evaluate(() => ({ sid: localStorage.getItem('smyle_sid'), v: localStorage.getItem('smyle_visit_day') }));
  expect(avant).toEqual({ sid: null, v: null });
  // Refus : toujours rien. Puis réouverture depuis le pied de page.
  await page.locator('#smyle-consent [data-consent="no"]').click();
  await expect(page.locator('#smyle-consent')).toHaveCount(0);
  await footer.getByRole('button', { name: 'Cookies / mesure d’audience' }).click();
  await expect(page.locator('#smyle-consent')).toBeVisible();
  await expect(page.locator('#smyle-consent')).toContainText('mesure refusée');
  // Accord : l'identifiant de session apparaît ; refus ensuite : il est effacé.
  await page.locator('#smyle-consent [data-consent="ok"]').click();
  await page.evaluate(() => window.SmyleTrack && window.SmyleTrack.flush());
  await expect.poll(() => page.evaluate(() => localStorage.getItem('smyle_sid'))).not.toBeNull();
  await footer.getByRole('button', { name: 'Cookies / mesure d’audience' }).click();
  await page.locator('#smyle-consent [data-consent="no"]').click();
  expect(await page.evaluate(() => localStorage.getItem('smyle_sid'))).toBeNull();
});
