// Record the README demo against a running stack with a real LLM (nothing is mocked).
// Usage: node scripts/demo.mjs  (env: APP_URL, DEMO_EMAIL, DEMO_PASSWORD, QUESTION)
// Writes docs/demo/raw.webm and docs/demo/marks.json (when the analysis started and finished), which
// scripts/demo.sh uses to speed up only the wait for the model.
import { chromium } from '@playwright/test'
import { mkdirSync, renameSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const APP = process.env.APP_URL ?? 'http://localhost:5173'
const EMAIL = process.env.DEMO_EMAIL ?? 'demo@analystos.dev'
const PASSWORD = process.env.DEMO_PASSWORD ?? 'analystos-demo-2026'
const QUESTION = process.env.QUESTION ?? 'Which region had the highest revenue in 2026? Show it as a bar chart.'
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/demo')
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const size = { width: 1280, height: 800 }
const context = await browser.newContext({
  viewport: size,
  colorScheme: 'dark',
  recordVideo: { dir: OUT, size },
})
const page = await context.newPage()
const t0 = Date.now()
const marks = {}
const mark = (name) => (marks[name] = (Date.now() - t0) / 1000)
const pause = (ms) => page.waitForTimeout(ms)

await page.goto(`${APP}/login`)
await page.getByLabel(/email/i).fill(EMAIL)
await page.getByLabel(/password/i).fill(PASSWORD)
await pause(400)
await page.getByRole('button', { name: /sign in/i }).click()
await page.waitForURL((url) => !url.pathname.startsWith('/login'))
await page.getByTestId('stat-tiles').waitFor()
await pause(1500)

// The dataset: profile computed at upload.
await page.goto(`${APP}/datasets`)
await page.getByText('Sales 2025-2026').first().click()
await page.getByRole('tab', { name: 'Profile' }).click()
await page.getByTestId('profile-panel').waitFor()
await pause(2500)

// Ask.
await page.getByTestId('ask-question').click()
await page.getByTestId('ask-input').waitFor()
await page.getByTestId('ask-input').pressSequentially(QUESTION, { delay: 25 })
await pause(400)
await page.getByTestId('ask-submit').click()
const turn = page.getByTestId('analysis-turn').last()
mark('asked')
await turn.getByTestId('analysis-running').waitFor()
await page.waitForFunction(
  () => {
    const turns = document.querySelectorAll('[data-testid="analysis-turn"]')
    const status = turns[turns.length - 1]?.getAttribute('data-status')
    return status && !['queued', 'running'].includes(status)
  },
  null,
  { timeout: 15 * 60 * 1000, polling: 500 },
)
mark('answered')
const status = await turn.getAttribute('data-status')
if (status !== 'completed') throw new Error(`analysis ended as ${status}`)

// The answer, its chart and the evidence behind a number.
await turn.getByTestId('answer-headline').scrollIntoViewIfNeeded()
await pause(2500)
const chart = turn.getByTestId('chart-card').first()
if (await chart.count()) {
  await chart.scrollIntoViewIfNeeded()
  await pause(2500)
}
const claim = turn.locator('[data-testid="claim"][data-status="verified"]').first()
await claim.scrollIntoViewIfNeeded()
await pause(600)
await claim.click()
await page.getByTestId('evidence-drawer').waitFor()
await page.getByTestId('evidence-item').first().waitFor()
await pause(4000)
await page.keyboard.press('Escape')
await pause(800)
mark('end')

const video = page.video()
await context.close()
await browser.close()
renameSync(await video.path(), path.join(OUT, 'raw.webm'))
writeFileSync(path.join(OUT, 'marks.json'), JSON.stringify({ question: QUESTION, ...marks }, null, 2))
console.log('recorded', marks)
