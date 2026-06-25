// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE INTERACTION — Session connectée (fondation du filet d'interaction).
//
// Premier test d'interaction réelle (au-delà du simple chargement de page),
// prérequis pour sécuriser la découpe des monolithes (handoff Phase 1) : il
// prouve que la chaîne d'authentification fonctionne de bout en bout.
//
// Mécanique réelle (cf. ui/core/api.js + ui/modals/auth.js) :
//   - le JWT vit dans localStorage['smyle_api_token'] ;
//   - au boot, auth.js lit ce token, appelle GET /users/me, puis rend l'UI
//     connectée (#authArea → .user-badge avec les initiales).
// On crée donc un vrai compte via l'API, on injecte le token, et on laisse
// l'app faire le reste — pas de simulation fragile de l'état interne.
//
// Rate-limit register désactivé en CI (ENVIRONMENT=test).
// ─────────────────────────────────────────────────────────────────────────────

const TOKEN_KEY = 'smyle_api_token';

test('connexion : un compte authentifié voit l’UI connectée', async ({ page, request }) => {
  const email = `e2e-auth-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
  const password = 'Test123456';

  // 1. Inscription via l'API (201).
  const reg = await request.post('/auth/register', { data: { email, password } });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);

  // 2. Login → JWT.
  const login = await request.post('/auth/login', { data: { email, password } });
  expect(login.status(), `login: ${await login.text()}`).toBe(200);
  const { access_token } = await login.json();
  expect(access_token, 'access_token présent').toBeTruthy();

  // 3. Injecte le token AVANT le boot des scripts de la page.
  await page.addInitScript(([key, tok]) => {
    try { localStorage.setItem(key, tok); } catch (e) { /* */ }
  }, [TOKEN_KEY, access_token]);

  // 4. Charge l'accueil → auth.js lit le token, fait /users/me, rend l'UI connectée.
  await page.goto('/', { waitUntil: 'domcontentloaded' });

  // 5. Le badge utilisateur (état connecté) apparaît après le bootstrap async.
  await expect(page.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
});

test('déconnecté : pas de badge utilisateur', async ({ page }) => {
  // Aucun token injecté → l'UI reste en état déconnecté (pas de .user-badge).
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('h1.mp-hero-title')).toBeVisible();
  await expect(page.locator('#authArea .user-badge')).toHaveCount(0);
});
