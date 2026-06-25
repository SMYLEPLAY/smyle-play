// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — Monde Visuel public + page "voir tout".
//
// Étend le filet anti-régression avant la découpe des monolithes (handoff
// Phase 1) et vérifie que les endpoints publics du Monde Visuel répondent.
//
// ⚠️ NOTE D'ARCHITECTURE (audit 2026-06-25) : le chemin `/images` est servi par
// l'API FastAPI (JSON, listing public) car le routeur images n'a pas de
// préfixe — il MASQUE la page HTML Flask `/images`. La vitrine image est donc
// atteinte via le sélecteur de mode sur `index.html`, pas par l'URL /images en
// direct. On ne teste donc PAS `/images` comme page HTML ici (ce serait du
// JSON). `/sons`, lui, n'est pas masqué → vraie page.
// ─────────────────────────────────────────────────────────────────────────────

test('la page /sons (voir tout) se charge', async ({ page }) => {
  const resp = await page.goto('/sons', { waitUntil: 'domcontentloaded' });
  expect(resp, 'réponse de /sons').toBeTruthy();
  expect(resp.status(), 'statut HTTP de /sons').toBeLessThan(400);
  await expect(page).toHaveTitle(/WATT/i);
  await expect(page.locator('h1.mp-hero-title')).toBeVisible();
});

test('le catalogue public images répond', async ({ request }) => {
  const r = await request.get('/images');
  expect(r.status(), 'statut /images').toBe(200);
  const body = await r.json();
  // Forme documentée : { query, count, images: [...] }.
  expect(Array.isArray(body.images), 'images doit être un tableau').toBe(true);
});

test('le Top Images répond', async ({ request }) => {
  const r = await request.get('/images/top');
  expect(r.status(), 'statut /images/top').toBe(200);
  const body = await r.json();
  expect(body, 'corps JSON de /images/top').toBeTruthy();
});
