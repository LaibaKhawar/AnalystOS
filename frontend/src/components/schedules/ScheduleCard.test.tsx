import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Schedule } from '@/api/types'
import { source } from '@/test/fixtures'
import { mockApi, renderWithProviders, testUser } from '@/test/utils'
import { ScheduleCard } from './ScheduleCard'

afterEach(() => vi.unstubAllGlobals())

const schedule = (over: Partial<Schedule> = {}): Schedule => ({
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
  last_run_at: '2026-10-13T10:00:00Z',
  last_analysis_id: 'ana_1',
  last_status: 'failed',
  created_at: '2026-10-13T10:00:00Z',
  ...over,
})

function renderCard(s: Schedule) {
  mockApi({})
  renderWithProviders(
    <ul>
      <ScheduleCard schedule={s} source={source()} canRun onEdit={vi.fn()} />
    </ul>,
    { user: testUser() },
  )
}

describe('ScheduleCard', () => {
  it('shows the status of the last run next to its time', () => {
    renderCard(schedule())
    expect(screen.getByTestId('schedule-last-status')).toHaveTextContent('Failed')
    expect(screen.getByTestId('schedule-last-analysis')).toHaveAttribute('href', '/workspace/by-analysis/ana_1')
  })

  it('shows no status before the first run', () => {
    renderCard(schedule({ last_run_at: null, last_analysis_id: null, last_status: null }))
    expect(screen.queryByTestId('schedule-last-status')).not.toBeInTheDocument()
    expect(screen.getByText('Never')).toBeInTheDocument()
  })
})
