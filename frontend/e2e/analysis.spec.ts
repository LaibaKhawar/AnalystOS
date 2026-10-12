import path from 'node:path'
import { expect, test } from '@playwright/test'

const SALES_CSV = path.resolve(import.meta.dirname, '../../backend/evals/data/sales.csv')
const QUESTION = 'Which region had the highest revenue in 2026?'
const FOLLOW_UP = 'Show total 2026 revenue for every region as a bar chart.'
// A shared local LLM can be slow under load; override with E2E_ANALYSIS_TIMEOUT_MS.
const ANALYSIS_TIMEOUT = Number(process.env.E2E_ANALYSIS_TIMEOUT_MS ?? 12 * 60 * 1000)
// The worker is shared; a job can wait in the queue before it starts running.
const QUEUE_TIMEOUT = Number(process.env.E2E_QUEUE_TIMEOUT_MS ?? 10 * 60 * 1000)

test('register, upload, profile, analyze, inspect evidence, report', async ({ page }) => {
  const email = `e2e-${Date.now()}@analystos.dev`

  await test.step('register', async () => {
    await page.goto('/register')
    await page.getByLabel('Name').fill('E2E Analyst')
    await page.getByLabel('Work email').fill(email)
    await page.getByLabel('Password').fill('e2e-password-2026')
    await page.getByRole('button', { name: 'Start analyzing' }).click()
    await expect(page).toHaveURL(/\/datasets$/)
  })

  await test.step('upload sales.csv and land in the explorer', async () => {
    await page.getByTestId('upload-input').setInputFiles(SALES_CSV)
    await expect(page).toHaveURL(/\/sources\/src_[a-z0-9]+/, { timeout: 120_000 })
    await expect(page.getByRole('heading', { level: 1 })).toContainText('sales')
  })

  await test.step('see profiling', async () => {
    await page.getByRole('tab', { name: 'Profile' }).click()
    const profile = page.getByTestId('profile-panel')
    await expect(profile).toBeVisible()
    await expect(profile.getByText('Duplicate rows')).toBeVisible()
    await expect(profile.getByTestId('column-profile').first()).toBeVisible()
  })

  await test.step('ask a question', async () => {
    await page.getByTestId('ask-question').click()
    await expect(page).toHaveURL(/\/workspace\/cnv_[a-z0-9]+/)
    await expect(page.getByTestId('workspace-source-name')).toContainText('sales')
    await page.getByTestId('ask-input').fill(QUESTION)
    await page.getByTestId('ask-submit').click()
  })

  const turn = page.getByTestId('analysis-turn').last()

  await test.step('observe progress', async () => {
    await expect(turn).toContainText(QUESTION)
    await expect(turn.getByTestId('analysis-running')).toBeVisible()
    await expect(page.getByTestId('ask-input')).toBeDisabled()
    await expect(turn).not.toHaveAttribute('data-status', 'queued', { timeout: QUEUE_TIMEOUT })
    if ((await turn.getAttribute('data-status')) === 'running') {
      await expect(turn.getByTestId('activity-feed')).toBeVisible({ timeout: ANALYSIS_TIMEOUT })
    }
  })

  await test.step('wait for completion', async () => {
    await expect(turn).toHaveAttribute('data-status', /completed|failed|needs_clarification|cancelled/, {
      timeout: ANALYSIS_TIMEOUT,
    })
    const status = await turn.getAttribute('data-status')
    if (status !== 'completed') {
      const detail = await turn.innerText()
      throw new Error(`Analysis ended with status ${status}: ${detail.slice(0, 500)}`)
    }
    await expect(turn.getByTestId('answer-headline')).toBeVisible()
    await expect(turn.getByTestId('cost-line')).toContainText('$0.0000')
  })

  await test.step('see a chart', async () => {
    let chartTurn = turn
    if ((await turn.getByTestId('chart-card').count()) === 0) {
      // The planner sometimes answers a "highest" question with a single-row aggregate and no chart.
      // Ask for the chart explicitly as a follow-up in the same conversation.
      test
        .info()
        .annotations.push({ type: 'note', description: 'First answer had no chart; asked a follow-up chart request.' })
      await expect(page.getByTestId('ask-input')).toBeEnabled()
      await page.getByTestId('ask-input').fill(FOLLOW_UP)
      await page.getByTestId('ask-submit').click()
      chartTurn = page.getByTestId('analysis-turn').last()
      await expect(chartTurn).toContainText(FOLLOW_UP)
      await expect(chartTurn).not.toHaveAttribute('data-status', 'queued', { timeout: QUEUE_TIMEOUT })
      await expect(chartTurn).toHaveAttribute('data-status', /completed|failed|needs_clarification|cancelled/, {
        timeout: ANALYSIS_TIMEOUT,
      })
      expect(await chartTurn.getAttribute('data-status')).toBe('completed')
    }
    const chart = chartTurn.getByTestId('chart-card').first()
    await expect(chart).toBeVisible()
    await expect(chart.locator('svg.recharts-surface').first()).toBeVisible()
  })

  await test.step('open evidence for a verified claim and see SQL', async () => {
    await turn.locator('[data-testid="claim"][data-status="verified"]').first().click()
    const drawer = page.getByTestId('evidence-drawer')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByTestId('evidence-item').first()).toBeVisible()
    await expect(drawer.locator('[data-slot="code-block"]').first()).toContainText(/SELECT/i)
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
  })

  await test.step('generate a report and download HTML', async () => {
    await turn.getByRole('button', { name: 'Generate report' }).click()
    await expect(page).toHaveURL(/\/reports\/rpt_[a-z0-9]+/, { timeout: 60_000 })
    await expect(page.getByTestId('report-frame')).toBeVisible()
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('download-html').click()])
    expect(download.suggestedFilename()).toMatch(/\.html$/)
  })
})
