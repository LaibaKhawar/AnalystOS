// Record the static replay demo: browse a running stack as the demo user and store every API response the
// pages load in public/replay.json (see src/api/replay.ts). Run scripts/showcase.mjs first.
// Usage: node scripts/record-replay.mjs  (env: APP_URL, API_URL, DEMO_EMAIL, DEMO_PASSWORD, MODEL_LABEL)
import { chromium } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const APP = process.env.APP_URL ?? 'http://localhost:5173'
const API = process.env.API_URL ?? 'http://localhost:8000'
const EMAIL = process.env.DEMO_EMAIL ?? 'demo@analystos.dev'
const PASSWORD = process.env.DEMO_PASSWORD ?? 'analystos-demo-2026'
const MODEL = process.env.MODEL_LABEL ?? 'Qwen3 8B (local, Ollama)'
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../public/replay.json')
const MAX_CLAIMS = 8

function key(method, url) {
  const parsed = new URL(url)
  const route = parsed.pathname.replace(/^\/api/, '')
  const params = [...parsed.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b))
  const query = params.length ? `?${new URLSearchParams(params).toString()}` : ''
  return `${method} ${route}${query}`
}

async function api(token, route) {
  const res = await fetch(`${API}/api${route}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`${route}: ${res.status}`)
  return res.json()
}

const login = await fetch(`${API}/api/auth/login`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
}).then((r) => r.json())
const token = login.access_token
const sources = await api(token, '/sources')
const conversations = await api(token, '/conversations')
const runs = await api(token, '/evaluations')
const reports = await api(token, '/reports')

const responses = {}
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
page.on('response', async (response) => {
  const request = response.request()
  if (request.method() !== 'GET' || !new URL(response.url()).pathname.startsWith('/api/')) return
  if (new URL(response.url()).pathname.endsWith('/stream')) return
  const type = response.headers()['content-type'] ?? ''
  try {
    if (type.includes('application/json')) {
      responses[key('GET', response.url())] = { status: response.status(), body: await response.json() }
    } else if (type.includes('text/html') || type.includes('text/csv')) {
      responses[key('GET', response.url())] = { status: response.status(), text: await response.text(), type }
    }
  } catch {
    // body unavailable (navigation away); the page is visited again later if needed
  }
})

const settle = () => page.waitForLoadState('networkidle').then(() => page.waitForTimeout(600))
const visit = async (route) => {
  await page.goto(`${APP}${route}`)
  await settle()
}

await page.goto(`${APP}/login`)
await page.getByLabel(/email/i).fill(EMAIL)
await page.getByLabel(/password/i).fill(PASSWORD)
await page.getByRole('button', { name: /sign in/i }).click()
await page.waitForURL((url) => !url.pathname.startsWith('/login'))
await settle()

for (const route of [
  '/',
  '/datasets',
  '/connections',
  '/workspace',
  '/reports',
  '/schedules',
  '/alerts',
  '/evaluations',
]) {
  await visit(route)
}
await visit('/welcome')

for (const source of sources) {
  await visit(`/sources/${source.id}`)
  for (const tab of await page.getByRole('tab').all()) {
    await tab.click()
    await settle()
  }
}

for (const conversation of conversations) {
  await visit(`/workspace/${conversation.id}`)
  for (const turn of await page.getByTestId('analysis-turn').all()) {
    const claims = await turn.getByTestId('claim').all()
    for (const claim of claims.slice(0, MAX_CLAIMS)) {
      await claim.scrollIntoViewIfNeeded()
      await claim.click()
      await page.getByTestId('evidence-drawer').waitFor()
      await settle()
      await page.keyboard.press('Escape')
      await page.waitForTimeout(200)
    }
  }
}

for (const report of reports) await visit(`/reports/${report.id}`)
for (const run of runs.filter((r) => r.status === 'completed')) await visit(`/evaluations/${run.id}`)
const compare = runs
  .filter((r) => r.status === 'completed')
  .slice(0, 3)
  .map((r) => r.id)
if (compare.length > 1) await visit(`/evaluations/compare?runs=${compare.join(',')}`)

await browser.close()
// The replay session never refreshes; drop auth endpoints other than "who am I".
for (const k of Object.keys(responses)) if (k.startsWith('GET /auth/') && k !== 'GET /auth/me') delete responses[k]
writeFileSync(OUT, JSON.stringify({ recorded_at: new Date().toISOString(), model: MODEL, responses }))
console.log(`recorded ${Object.keys(responses).length} responses -> ${OUT}`)
