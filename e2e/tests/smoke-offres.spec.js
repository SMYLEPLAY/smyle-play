// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — Page Offres créateur (C6). La page /offres se charge et présente les
// trois paliers avec leur commission (20 / 12 / 5). Rendu statique : stable même
// base vide (le surlignage du palier courant dépend de /users/me, non testé ici).
// ─────────────────────────────────────────────────────────────────────────────

test('la page /offres se charge avec les 3 paliers', async ({ page }) => {
  const resp = await page.goto('/offres', { waitUntil: 'domcontentloaded' });
  expect(resp, 'réponse de /offres').toBeTruthy();
  expect(resp.status(), 'statut HTTP de /offres').toBeLessThan(400);

  await expect(page).toHaveTitle(/Offres/i);

  // Les trois cartes paliers sont rendues par le script inline.
  await expect(page.locator('#off-grid .off-card')).toHaveCount(3);

  // Les trois commissions du barème sont visibles.
  await expect(page.getByText('20%', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('12%', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('5%', { exact: false }).first()).toBeVisible();
});
