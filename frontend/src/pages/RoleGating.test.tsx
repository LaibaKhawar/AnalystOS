import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { ErrorState } from '@/components/common/States'
import { SidebarNav } from '@/components/layout/SidebarNav'
import { source, table } from '@/test/fixtures'
import { mockApi, renderWithProviders, testUser } from '@/test/utils'
import Connections from './Connections'
import Datasets from './Datasets'
import Explorer from './Explorer'
import Schedules from './Schedules'

afterEach(() => vi.unstubAllGlobals())

const viewer = testUser({ role: 'viewer' })
const analyst = testUser({ role: 'analyst' })

function renderExplorer(user = analyst, over: Parameters<typeof source>[0] = {}) {
  const s = source(over)
  mockApi({
    'GET /api/sources/src_1': s,
    'GET /api/sources/src_1/tables': [table()],
    'GET /api/sources/src_1/metrics': [],
  })
  return renderWithProviders(
    <Routes>
      <Route path="/sources/:sourceId" element={<Explorer />} />
    </Routes>,
    { user, route: '/sources/src_1' },
  )
}

describe('role gating', () => {
  it('hides uploads from viewers and explains why', async () => {
    mockApi({ 'GET /api/sources': [source({ access: 'read', owned: false, name: 'shared sales' })] })
    renderWithProviders(<Datasets />, { user: viewer })
    expect(screen.getByText('Uploading is not available for your role')).toBeInTheDocument()
    expect(screen.queryByTestId('upload-input')).not.toBeInTheDocument()
    expect(await screen.findByText('shared sales')).toBeInTheDocument()
    expect(screen.getByTestId('shared-badge')).toHaveTextContent('Shared with you')
    expect(screen.getByTestId('shared-badge')).toHaveTextContent('Read only')
    expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument()
  })

  it('lets analysts upload', () => {
    mockApi({ 'GET /api/sources': [] })
    renderWithProviders(<Datasets />, { user: analyst })
    expect(screen.getByTestId('upload-input')).toBeInTheDocument()
    expect(screen.queryByTestId('access-notice')).not.toBeInTheDocument()
  })

  it('hides the connection form from viewers', () => {
    mockApi({ 'GET /api/sources': [] })
    renderWithProviders(<Connections />, { user: viewer })
    expect(screen.getByText('Connecting databases is not available for your role')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Test and save' })).not.toBeInTheDocument()
  })

  it('hides schedule creation from viewers', async () => {
    mockApi({ 'GET /api/schedules': [], 'GET /api/sources': [] })
    renderWithProviders(<Schedules />, { user: viewer })
    expect(screen.getByText('Scheduling is not available for your role')).toBeInTheDocument()
    expect(screen.queryByTestId('new-schedule')).not.toBeInTheDocument()
    expect(await screen.findByText('No schedules yet')).toBeInTheDocument()
  })

  it('shows owners the share, delete and ask actions', async () => {
    renderExplorer(analyst)
    expect(await screen.findByTestId('ask-question')).toBeInTheDocument()
    expect(screen.getByTestId('share-source')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete sales' })).toBeInTheDocument()
    expect(screen.queryByTestId('read-only-notice')).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Edit revenue' })).toBeInTheDocument()
  })

  it('makes a read share read only: no ask, share, delete or column edits', async () => {
    renderExplorer(analyst, { access: 'read', owned: false })
    expect(await screen.findByTestId('read-only-notice')).toHaveTextContent('read-only access')
    expect(screen.queryByTestId('ask-question')).not.toBeInTheDocument()
    expect(screen.queryByTestId('share-source')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete sales' })).not.toBeInTheDocument()
    expect((await screen.findAllByText('revenue')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Edit revenue' })).not.toBeInTheDocument()
  })

  it('lets an analyst share ask but not manage', async () => {
    renderExplorer(analyst, { access: 'ask', owned: false })
    expect(await screen.findByTestId('ask-question')).toBeInTheDocument()
    expect(screen.queryByTestId('share-source')).not.toBeInTheDocument()
    expect(screen.getByTestId('shared-badge')).toHaveTextContent('Can ask')
  })

  it('shows the Users nav item only to admins', () => {
    const { unmount } = renderWithProviders(<SidebarNav />, { user: analyst })
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Schedules' })).toBeInTheDocument()
    unmount()
    renderWithProviders(<SidebarNav />, { user: testUser({ role: 'admin', is_admin: true }) })
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument()
  })
})

describe('forbidden and rate limited errors', () => {
  it('explains a 403 and offers no pointless retry', () => {
    const error = new ApiError(403, 'forbidden', 'This action needs one of these roles: analyst, admin')
    renderWithProviders(<ErrorState error={error} onRetry={() => undefined} />)
    expect(screen.getByRole('alert')).toHaveTextContent('You do not have permission')
    expect(screen.getByRole('alert')).toHaveTextContent('This action needs one of these roles: analyst, admin')
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('shows how long to wait on a 429', () => {
    const error = new ApiError(429, 'rate_limited', 'Too many requests. Try again in 1740 seconds.', {
      retry_after_seconds: 1740,
    })
    renderWithProviders(<ErrorState error={error} onRetry={() => undefined} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Slow down')
    expect(screen.getByRole('alert')).toHaveTextContent('Too many requests. Try again in 29 minutes.')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
