// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — Monde Visuel public + pages "voir tout".
//
// Étend le filet anti-régression avant la découpe des monolithes (handoff
// Phase 1) : vérifie que la vitrine images publique se charge et que ses
// endpoints répondent. Constat audit 2026-06-25 : la route /images existe déjà
// (Flask sert le shell, marketplace.js gère la vue image) — ce smoke le prouve
// et protège la refonte à venir.
//
// Volontairement public (aucune auth) → déterministe, base vide OK.
// ─────────────────────────────────────────────────────────────────────────────

test('la page /images (vitrine Visuel) se charge', async ({ page }) => {
  const resp = await page.goto('/images', { waitUntil: 'domcontentloaded' });
  expect(resp, 'réponse de /images').toBeTruthy();
  expect(resp.status(), 'statut HTTP de /images').toBeLessThan(400);
  await expect(page).toHaveTitle(/WATT/i);
  // Même shell que la marketplace (servi par Flask) → hero présent.
  await expect(page.locator('h1.mp-hero-title')).toBeVisible();
});

test('la page /sons (voir tout) se charge', async ({ page }) => {
  const resp = await page.goto('/sons', { waitUntil: 'domcontentloaded' });
  expect(resp, 'réponse de /sons').toBeTruthy();
  expect(resp.status(), 'statut HTTP de /sons').toBeLessThan(400);
  await expect(page.locator('h1.mp-hero-title')).toBeVisible();
});

test('le catalogue public images répond', async ({ request }) => {
  const r = await request.get('/images');
  expect(r.status(), 'statut /images').toBe(200);
  const body = await r.json();
  // Forme documentée : { images: [...], count }.
  expect(Array.isArray(body.images), 'images doit être un tableau').toBe(true);
});

test('le Top Images répond', async ({ request }) => {
  const r = await request.get('/images/top');
  expect(r.status(), 'statut /images/top').toBe(200);
  const body = await r.json();
  expect(body, 'corps JSON de /images/top').toBeTruthy();
});
