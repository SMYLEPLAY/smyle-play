// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE INTERACTION — Panneau de filtres mode-aware (fix 2026-06-25).
//
// Bug corrigé : sur l'accueil, le panneau « Filtres » inline restait figé sur
// la musique (Moods · sons / Rôles · artistes) même en mode Image. Il doit
// désormais montrer Styles · images + Usage + Créateurs visuels quand on passe
// en mode Image (en miroir de la loupe).
//
// Public (aucune auth) — le commutateur de mode et le panneau vivent sur la home.
// ─────────────────────────────────────────────────────────────────────────────

test('mode Image : le panneau de filtres montre les styles d’image, pas les moods musique', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });

  // Commutateur de mode présent sur la home.
  const imageBtn = page.locator('.mp-mode-btn[data-mode="image"]');
  await expect(imageBtn).toBeVisible({ timeout: 15000 });
  await imageBtn.click();

  // Ouvre le dépliant « Filtres ».
  await page.locator('.mp-hsb-toggle').first().click();

  const panel = page.locator('#mp-hsb-moods');
  // Chips de STYLE image présents + en-tête « Styles ».
  await expect(panel.locator('[data-style="realiste"]')).toBeVisible();
  await expect(panel).toContainText(/Styles/i);
  await expect(panel).toContainText(/Cr[ée]ateurs visuels/i);
  // Et PLUS les moods musique (preuve que le panneau a bien basculé).
  await expect(panel.locator('[data-mood="chill"]')).toHaveCount(0);
});

test('mode Musique : le panneau de filtres montre les moods sons', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const musiqueBtn = page.locator('.mp-mode-btn[data-mode="musique"]');
  await expect(musiqueBtn).toBeVisible({ timeout: 15000 });
  await musiqueBtn.click();
  await page.locator('.mp-hsb-toggle').first().click();
  const panel = page.locator('#mp-hsb-moods');
  await expect(panel.locator('[data-mood="chill"]')).toBeVisible();
  await expect(panel.locator('[data-style="realiste"]')).toHaveCount(0);
});
