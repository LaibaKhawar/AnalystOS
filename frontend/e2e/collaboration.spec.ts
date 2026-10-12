import path from 'node:path'
import { expect, test, type Browser, type Page } from '@playwright/test'

const SALES_CSV = path.resolve(import.meta.dirname, '../../backend/evals/data/sales.csv')
const QUESTION = 'Which region had the highest revenue in 2026?'
const ANALYSIS_TIMEOUT = Number(process.env.E2E_ANALYSIS_TIMEOUT_MS ?? 12 * 60 * 1000)
const QUEUE_TIMEOUT = Number(process.env.E2E_QUEUE_TIMEOUT_MS ?? 10 * 60 * 1000)
const PASSWORD = 'e2e-password-2026'

async function newPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL })
  return context.newPage()
}

async function register(page: Page, name: string, email: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Name').fill(name)
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Start analyzing' }).click()
  await expect(page).toHaveURL(/\/datasets$/)
}

test('share a dataset, saved metrics, roles and schedules across two users', async ({ browser }) => {
  const stamp = Date.now()
  const emailA = `e2e-owner-${stamp}@analystos.dev`
  const emailB = `e2e-guest-${stamp}@analystos.dev`
  const a = await newPage(browser)
  const b = await newPage(browser)
  let explorerUrl = ''

  await test.step('register user A and user B', async () => {
    await register(a, 'Owner A', emailA)
    await register(b, 'Guest B', emailB)
    // B owns nothing yet.
    await expect(b.getByText('No datasets yet')).toBeVisible()
  })

  await test.step('A uploads sales.csv', async () => {
    await a.getByTestId('upload-input').setInputFiles(SALES_CSV)
    await expect(a).toHaveURL(/\/sources\/src_[a-z0-9]+/, { timeout: 120_000 })
    await expect(a.getByRole('heading', { level: 1 })).toContainText('sales')
    explorerUrl = new URL(a.url()).pathname
  })

  await test.step('A creates a saved metric, after an inline server validation error', async () => {
    await a.getByRole('tab', { name: /Metrics/ }).click()
    const panel = a.getByTestId('metrics-panel')
    await expect(panel.getByText('No saved metrics yet')).toBeVisible()
    await panel.getByRole('button', { name: 'New metric' }).click()
    const dialog = a.getByTestId('metric-dialog')
    await dialog.getByLabel('Label').fill('Average revenue per row')
    await expect(dialog.getByLabel('Name')).toHaveValue('average_revenue_per_row')
    await dialog.getByTestId('metric-expression').fill('revenue')
    await dialog.getByTestId('metric-save').click()
    await expect(dialog.getByText('A metric must aggregate')).toBeVisible()
    await dialog.getByTestId('metric-expression').fill('SUM(revenue) / COUNT(*)')
    await dialog.getByTestId('metric-save').click()
    await expect(dialog).toBeHidden()
    const row = panel.getByTestId('metric-row')
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('average_revenue_per_row')
    await expect(row).toContainText('SUM(revenue) / COUNT(*)')
  })

  await test.step('A shares the dataset with B as a viewer', async () => {
    await a.getByTestId('share-source').click()
    const dialog = a.getByTestId('share-dialog')
    await expect(dialog.getByText('Not shared with anyone yet')).toBeVisible()
    await dialog.getByLabel('Email').fill(emailB)
    await dialog.getByRole('button', { name: 'Share', exact: true }).click()
    const share = dialog.getByTestId('share-row')
    await expect(share).toHaveCount(1)
    await expect(share).toContainText(emailB)
    await expect(dialog.getByRole('combobox', { name: `Access for ${emailB}` })).toContainText('Viewer')
  })

  await test.step('B sees the dataset read only, without an ask action', async () => {
    await b.goto('/datasets')
    const item = b.getByTestId('source-list').getByRole('listitem').first()
    await expect(item.getByTestId('shared-badge')).toContainText('Shared with you')
    await expect(item.getByTestId('shared-badge')).toContainText('Read only')
    await expect(item.getByRole('button', { name: /Delete/ })).toHaveCount(0)
    await item.getByRole('link').click()
    await expect(b).toHaveURL(new RegExp(`${explorerUrl}$`))
    await expect(b.getByTestId('read-only-notice')).toBeVisible()
    await expect(b.getByTestId('ask-question')).toHaveCount(0)
    await expect(b.getByTestId('share-source')).toHaveCount(0)
    await b.getByRole('tab', { name: /Metrics/ }).click()
    await expect(b.getByTestId('metric-row')).toContainText('average_revenue_per_row')
    await expect(b.getByRole('button', { name: 'New metric' })).toHaveCount(0)
  })

  await test.step('A changes B to analyst', async () => {
    const dialog = a.getByTestId('share-dialog')
    await dialog.getByRole('combobox', { name: `Access for ${emailB}` }).click()
    await a.getByRole('option', { name: 'Analyst' }).click()
    await expect(dialog.getByRole('combobox', { name: `Access for ${emailB}` })).toContainText('Analyst')
    await a.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  })

  await test.step('B asks a question and gets a verified answer', async () => {
    await b.reload()
    await expect(b.getByTestId('read-only-notice')).toHaveCount(0)
    await b.getByTestId('ask-question').click()
    await expect(b).toHaveURL(/\/workspace\/cnv_[a-z0-9]+/)
    await b.getByTestId('ask-input').fill(QUESTION)
    await b.getByTestId('ask-submit').click()
    const turn = b.getByTestId('analysis-turn').last()
    await expect(turn).not.toHaveAttribute('data-status', 'queued', { timeout: QUEUE_TIMEOUT })
    await expect(turn).toHaveAttribute('data-status', /completed|failed|needs_clarification|cancelled/, {
      timeout: ANALYSIS_TIMEOUT,
    })
    expect(await turn.getAttribute('data-status')).toBe('completed')
    await expect(turn.getByTestId('answer-headline')).toBeVisible()
    await expect(turn.locator('[data-testid="claim"][data-status="verified"]').first()).toBeVisible()
  })

  await test.step('A creates a schedule, runs it now and sees it listed', async () => {
    await a.goto('/schedules')
    await expect(a.getByText('No schedules yet')).toBeVisible()
    await a.getByTestId('new-schedule').click()
    const dialog = a.getByTestId('schedule-dialog')
    await expect(dialog.getByTestId('schedule-source')).toContainText('sales')
    await dialog.getByLabel('Name').fill('Daily revenue check')
    await dialog.getByLabel('Question').fill(QUESTION)
    await dialog.getByLabel('Webhook URL').fill('http://hooks.example.com/x')
    await dialog.getByTestId('schedule-save').click()
    await expect(dialog.getByText('Webhook URLs must use https://')).toBeVisible()
    await dialog.getByLabel('Webhook URL').fill('')
    await dialog.getByTestId('schedule-save').click()
    await expect(dialog).toBeHidden()

    const row = a.getByTestId('schedule-row')
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Daily revenue check')
    await expect(row).toContainText('Daily')
    await expect(row).toContainText('Never')
    await row.getByTestId('schedule-run').click()
    await expect(row.getByTestId('schedule-last-analysis')).toBeVisible({ timeout: 30_000 })
    await expect(row).not.toContainText('Never')

    await a.reload()
    await expect(a.getByTestId('schedule-row')).toContainText('Daily revenue check')
    await a.getByTestId('schedule-last-analysis').click()
    await expect(a).toHaveURL(/\/workspace\/cnv_[a-z0-9]+/)
    const turn = a.getByTestId('analysis-turn').last()
    await expect(turn).toContainText(QUESTION)
    await expect(turn).toHaveAttribute('data-status', /completed|failed|needs_clarification|cancelled/, {
      timeout: ANALYSIS_TIMEOUT,
    })
  })

  await test.step('the first account on a fresh database is the admin', async () => {
    // Specs share one database; this account is the admin only when this spec ran first.
    const admin = (await a.getByRole('link', { name: 'Users' }).count()) > 0
    test.info().annotations.push({ type: 'note', description: `User A admin: ${admin}` })
    if (admin) {
      await a.getByRole('link', { name: 'Users' }).click()
      await expect(a.getByTestId('admin-user-row')).toHaveCount(2)
    } else {
      await a.goto('/admin/users')
      await expect(a.getByText('Admins only')).toBeVisible()
    }
  })
})
