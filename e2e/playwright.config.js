// @ts-check
const { defineConfig, devices } = require('@playwright/test');

// Filet anti-régression front (H0.1b). L'app prod est servie par
// `uvicorn main:app` : FastAPI seul rend l'API, les pages et les statiques
// (app/routers/pages.py) — Flask et a2wsgi ont été retirés le 2026-07-30
// (P0-c). En CI on démarre ce process puis on pointe la baseURL dessus.
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';

module.exports = defineConfig({
  testDir: './tests',
  // Déterminisme : pas de parallélisme surprise, et 2 retries en CI pour
  // absorber un cold-start lent sans rendre la CI faussement rouge.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  // En CI on ajoute le reporter `github` : il publie le nom du test, le
  // fichier:ligne et l'assertion en ANNOTATION GitHub — lisible sur la page
  // du job sans télécharger l'artefact HTML (le log brut, lui, demande une
  // session). Sans ça, un échec e2e n'affiche que « exit code 1 ».
  reporter: process.env.CI
    ? [['list'], ['github'], ['html', { open: 'never' }]]
    : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // Le storefront est servi en local : on attend que le réseau se calme.
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
