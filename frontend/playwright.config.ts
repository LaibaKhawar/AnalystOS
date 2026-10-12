import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against a live dev server and backend.
 * Start the backend (API + worker + LLM) and `npm run dev`, then `npm run e2e`.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: Number(process.env.E2E_TEST_TIMEOUT_MS ?? 30 * 60 * 1000),
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
})
