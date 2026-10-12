// Capture README screenshots from a running stack with real data.
// Usage: node scripts/screenshots.mjs  (env: APP_URL=http://localhost:5173, API_URL=http://localhost:8000,
//         DEMO_EMAIL, DEMO_PASSWORD, EVAL_RUN_ID optional)
import { chromium } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const APP = process.env.APP_URL ?? 'http://localhost:5173'
const API = process.env.API_URL ?? 'http://localhost:8000'
const EMAIL = process.env.DEMO_EMAIL ?? 'demo@analystos.dev'
const PASSWORD = process.env.DEMO_PASSWORD ?? 'analystos-demo-2026'
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/screenshots')

async function api(token, route) {
  const res = await fetch(`${API}${route}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`${route}: ${res.status}`)
  return res.json()
}

const login = await fetch(`${API}/api/auth/login`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
}).then((r) => r.json())
const token = login.access_token
const sources = await api(token, '/api/sources')
const sales = sources.find((s) => s.name.startsWith('Sales 2025')) ?? sources[0]
const analyses = await api(token, '/api/analyses?limit=20')
const done = analyses.filter((a) => a.status === 'completed' && a.data_source_id === sales.id)
const showcase = done.find((a) => (a.answer?.chart_ids ?? []).length > 0) ?? done[0]
const runs = await api(token, '/api/evaluations')
const run = process.env.EVAL_RUN_ID ?? runs.find((r) => r.status === 'completed')?.id

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' })
const page = await context.newPage()
const shot = async (name) => {
  await page.waitForTimeout(1200)
  await page.screenshot({ path: path.join(OUT, `${name}.png`) })
  console.log('saved', name)
}

await page.goto(`${APP}/welcome`)
await shot('landing')

// Sign in through the UI so the app stores its session the way it normally does.
await page.goto(`${APP}/login`)
await page.getByLabel(/email/i).fill(EMAIL)
await page.getByLabel(/password/i).fill(PASSWORD)
await page.getByRole('button', { name: /sign in/i }).click()
await page.waitForURL((url) => !url.pathname.startsWith('/login'))

await page.goto(`${APP}/`)
await page.getByTestId('stat-tiles').waitFor()
await shot('dashboard')

await page.goto(`${APP}/sources/${sales.id}`)
await page.getByRole('tab', { name: 'Profile' }).click()
await page.getByTestId('profile-panel').waitFor()
await shot('explorer')

if (showcase) {
  await page.goto(`${APP}/workspace/${showcase.conversation_id}`)
  await page.getByTestId('answer-headline').last().waitFor()
  await shot('workspace')
  await page.getByTestId('claim').first().click()
  await page.getByTestId('evidence-drawer').waitFor()
  await page.getByTestId('evidence-item').first().waitFor()
  await shot('evidence')
  await page.keyboard.press('Escape')
}

if (run) {
  await page.goto(`${APP}/evaluations/${run}`)
  await page.getByTestId('eval-metrics').waitFor()
  await shot('evaluations')
}

await browser.close()
