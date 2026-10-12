import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Schedule } from '@/api/types'
import { source } from '@/test/fixtures'
import { json, mockApi, renderWithProviders, sentBody, testUser } from '@/test/utils'
import { intervalLabel } from '@/lib/schedules'
import { ScheduleForm } from './ScheduleForm'

afterEach(() => vi.unstubAllGlobals())

const created: Schedule = {
  id: 'sch_1',
  data_source_id: 'src_1',
  conversation_id: 'cnv_9',
  name: 'Weekly check',
  question: 'Which region had the highest revenue?',
  interval_minutes: 10080,
  enabled: true,
  alert_min_severity: 'high',
  webhook_url: null,
  next_run_at: '2026-10-20T10:00:00Z',
  last_run_at: null,
  last_analysis_id: null,
  created_at: '2026-10-13T10:00:00Z',
}

function renderForm(onSaved = vi.fn()) {
  renderWithProviders(<ScheduleForm sources={[source()]} schedule={null} onSaved={onSaved} onCancel={vi.fn()} />, {
    user: testUser(),
  })
  return { user: userEvent.setup(), onSaved }
}

async function choose(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole('combobox', { name: label }))
  await user.click(await screen.findByRole('option', { name: option }))
}

describe('ScheduleForm', () => {
  it('preselects the only source and sends the chosen preset, threshold and toggle', async () => {
    const fetchMock = mockApi({ 'POST /api/schedules': () => json(201, created) })
    const { user, onSaved } = renderForm()
    expect(screen.getByTestId('schedule-source')).toHaveTextContent('sales')
    await user.type(screen.getByLabelText('Name'), 'Weekly check')
    await user.type(screen.getByLabelText('Question'), 'Which region had the highest revenue?')
    await choose(user, 'Runs', 'Weekly')
    await choose(user, 'Alert when', 'High only')
    await user.click(screen.getByRole('switch'))
    await user.click(screen.getByTestId('schedule-save'))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(created))
    expect(sentBody(fetchMock, 'POST /api/schedules')).toEqual({
      data_source_id: 'src_1',
      name: 'Weekly check',
      question: 'Which region had the highest revenue?',
      interval_minutes: 10080,
      alert_min_severity: 'high',
      webhook_url: null,
      enabled: false,
    })
  })

  it('enforces https webhooks and the 15 minute minimum on the client', async () => {
    const fetchMock = mockApi({})
    const { user } = renderForm()
    await user.type(screen.getByLabelText('Name'), 'Fast')
    await user.type(screen.getByLabelText('Question'), 'How many orders?')
    await choose(user, 'Runs', 'Custom interval')
    await user.type(screen.getByLabelText('Interval in minutes'), '5')
    await user.type(screen.getByLabelText(/Webhook URL/), 'http://hooks.example.com/x')
    await user.click(screen.getByTestId('schedule-save'))
    expect(screen.getByText('Webhook URLs must use https://')).toBeInTheDocument()
    expect(screen.getByText('Schedules can run at most every 15 minutes.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("shows the API's webhook validation message on the webhook field", async () => {
    mockApi({
      'POST /api/schedules': () =>
        json(422, {
          error: {
            code: 'validation_failed',
            message: 'Webhook hosts must be public (private, loopback and metadata addresses are blocked)',
            details: {},
          },
        }),
    })
    const { user } = renderForm()
    await user.type(screen.getByLabelText('Name'), 'Hook')
    await user.type(screen.getByLabelText('Question'), 'How many orders?')
    await user.type(screen.getByLabelText(/Webhook URL/), 'https://10.0.0.5/hook')
    await user.click(screen.getByTestId('schedule-save'))
    const message = await screen.findByText(/Webhook hosts must be public/)
    expect(screen.getByLabelText(/Webhook URL/).getAttribute('aria-describedby')).toBe(message.id)
  })

  it('labels intervals', () => {
    expect(intervalLabel(60)).toBe('Hourly')
    expect(intervalLabel(360)).toBe('Every 6 hours')
    expect(intervalLabel(1440)).toBe('Daily')
    expect(intervalLabel(10080)).toBe('Weekly')
    expect(intervalLabel(45)).toBe('Every 45 minutes')
    expect(intervalLabel(2880)).toBe('Every 2 days')
  })
})
