import { defineConfig, devices } from '@playwright/test'

/**
 * Two modes:
 *  - `npm run e2e`     against a live stack with the real LLM (start the backend, worker and `npm run dev` first)
 *  - `npm run e2e:ci`  deterministic: Playwright starts the real API with a rule-based LLM stand-in
 *                      (backend/tests/e2e_server.py) and a Vite dev server; no model, no worker, used in CI.
 */
const deterministic = process.env.E2E_DETERMINISTIC === '1'

export default defineConfig({
  testDir: './e2e',
  timeout: Number(process.env.E2E_TEST_TIMEOUT_MS ?? 30 * 60 * 1000),
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? (deterministic ? 'http://localhost:5174' : 'http://localhost:5173'),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
  webServer: deterministic
    ? [
        {
          command: '.venv/bin/python -m tests.e2e_server',
          cwd: '../backend',
          url: 'http://127.0.0.1:8001/api/health',
          timeout: 120_000,
          reuseExistingServer: false,
          env: { E2E_PORT: '8001', CORS_ORIGINS: 'http://localhost:5174' },
        },
        {
          command: 'npx vite --port 5174 --strictPort',
          url: 'http://localhost:5174',
          timeout: 120_000,
          reuseExistingServer: false,
          env: { VITE_API_PROXY: 'http://127.0.0.1:8001' },
        },
      ]
    : undefined,
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
})
