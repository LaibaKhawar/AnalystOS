import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Alert } from '@/api/types'
import { json, mockApi, renderWithProviders, testUser } from '@/test/utils'
import { ALERT_POLL_MS } from '@/hooks/queries/alerts'
import { AlertsBell } from './AlertsBell'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const alert = (id: string, over: Partial<Alert> = {}): Alert => ({
  id,
  schedule_id: 'sch_1',
  analysis_id: 'ana_1',
  severity: 'high',
  title: `Anomaly ${id}`,
  message: 'Revenue in North dropped 40%',
  delivery_status: 'sent',
  read_at: null,
  created_at: '2026-10-13T09:00:00Z',
  ...over,
})

describe('AlertsBell', () => {
  it('shows the unread count from /alerts/unread-count without loading the list', async () => {
    const fetchMock = mockApi({ 'GET /api/alerts/unread-count': { unread: 3 } })
    renderWithProviders(<AlertsBell />, { user: testUser() })
    expect(await screen.findByTestId('alerts-count')).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: 'Alerts, 3 unread' })).toBeInTheDocument()
    const paths = fetchMock.mock.calls.map((call) => new URL(String(call[0]), 'http://x').pathname)
    expect(paths).toEqual(['/api/alerts/unread-count'])
  })

  it('caps the badge at 99+', async () => {
    mockApi({ 'GET /api/alerts/unread-count': { unread: 140 } })
    renderWithProviders(<AlertsBell />, { user: testUser() })
    expect(await screen.findByTestId('alerts-count')).toHaveTextContent('99+')
  })

  it('shows no badge when everything is read', async () => {
    mockApi({ 'GET /api/alerts/unread-count': { unread: 0 } })
    renderWithProviders(<AlertsBell />, { user: testUser() })
    expect(await screen.findByRole('button', { name: 'Alerts, none unread' })).toBeInTheDocument()
    expect(screen.queryByTestId('alerts-count')).not.toBeInTheDocument()
  })

  it('polls every minute', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let unread = [alert('a1')]
    mockApi({ 'GET /api/alerts/unread-count': () => json(200, { unread: unread.length }) })
    renderWithProviders(<AlertsBell />, { user: testUser() })
    expect(await screen.findByTestId('alerts-count')).toHaveTextContent('1')
    unread = [alert('a1'), alert('a2')]
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ALERT_POLL_MS + 10)
    })
    await waitFor(() => expect(screen.getByTestId('alerts-count')).toHaveTextContent('2'))
  })

  it('lists unread alerts in the panel and marks one read', async () => {
    let unread = [alert('a1', { title: 'Revenue anomaly', delivery_status: 'not_configured' })]
    mockApi({
      'GET /api/alerts': () => json(200, unread),
      'GET /api/alerts/unread-count': () => json(200, { unread: unread.length }),
      'POST /api/alerts/a1/read': () => {
        const read = { ...unread[0], read_at: '2026-10-13T10:00:00Z' }
        unread = []
        return json(200, read)
      },
    })
    const user = userEvent.setup()
    renderWithProviders(<AlertsBell />, { user: testUser() })
    await user.click(await screen.findByRole('button', { name: 'Alerts, 1 unread' }))
    const item = await screen.findByTestId('alert-item')
    expect(item).toHaveTextContent('Revenue anomaly')
    expect(item).toHaveTextContent('High')
    expect(item).toHaveTextContent('In app only')
    expect(item.querySelector('a[href="/workspace/by-analysis/ana_1"]')).not.toBeNull()
    await user.click(screen.getByRole('button', { name: 'Mark "Revenue anomaly" as read' }))
    await waitFor(() => expect(screen.queryByTestId('alerts-count')).not.toBeInTheDocument())
  })
})
