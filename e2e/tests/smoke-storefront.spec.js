// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — Entrée du parcours d'achat : le storefront se charge et le backend
// catalogue répond. C'est le premier maillon avant tout achat (H0.1b).
//
// Volontairement minimal et déterministe : on vérifie que la vitrine rend
// (HTML statique servi par Flask) + que l'endpoint catalogue public répond.
// L'auth, les crédits et l'achat effectif viendront dans un smoke dédié une
// fois une fixture utilisateur+seed en place — pas de flake d'auth ici.
// ─────────────────────────────────────────────────────────────────────────────

test('la vitrine WATT se charge (shell du parcours achat)', async ({ page }) => {
  const resp = await page.goto('/', { waitUntil: 'domcontentloaded' });
  expect(resp, 'réponse de /').toBeTruthy();
  expect(resp.status(), 'statut HTTP de /').toBeLessThan(400);

  // Titre de page servi par le front.
  await expect(page).toHaveTitle(/WATT/i);

  // Élément clé de la vitrine (hero) — présent dans le HTML statique,
  // donc rendu même base vide → assertion stable.
  await expect(page.locator('h1.mp-hero-title')).toBeVisible();

  // Le sélecteur de monde (Musique / Image) = entrée de la découverte.
  await expect(page.locator('#mp-mode-switch')).toBeVisible();
});

test('le catalogue public répond (backend du parcours achat)', async ({ request }) => {
  // Endpoint catalogue consommé par la vitrine, sans authentification.
  const r = await request.get('/watt/tracks-catalog');
  expect(r.status(), 'statut /watt/tracks-catalog').toBe(200);
  // La forme exacte peut varier ; on garantit juste un corps JSON exploitable.
  const body = await r.json();
  expect(body, 'corps JSON du catalogue').toBeTruthy();
});
