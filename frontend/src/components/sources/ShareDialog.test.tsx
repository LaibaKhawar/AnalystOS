import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SourceShare } from '@/api/types'
import { json, mockApi, renderWithProviders, sentBody, testUser } from '@/test/utils'
import { ShareDialog } from './ShareDialog'

afterEach(() => vi.unstubAllGlobals())

const bob: SourceShare = {
  id: 'shr_1',
  user_id: 'usr_2',
  email: 'bob@example.com',
  name: 'Bob',
  role: 'viewer',
  created_at: '2026-10-01T10:00:00Z',
}

async function open() {
  const user = userEvent.setup()
  renderWithProviders(<ShareDialog source={{ id: 'src_1', name: 'sales' }} />, { user: testUser() })
  await user.click(screen.getByTestId('share-source'))
  return { user, dialog: await screen.findByTestId('share-dialog') }
}

describe('ShareDialog', () => {
  it('lists current shares with a remove button and removes one', async () => {
    let shares = [bob]
    const fetchMock = mockApi({
      'GET /api/sources/src_1/shares': () => json(200, shares),
      'DELETE /api/sources/src_1/shares/shr_1': () => {
        shares = []
        return new Response(null, { status: 204 })
      },
    })
    const { user, dialog } = await open()
    const row = await within(dialog).findByTestId('share-row')
    expect(row).toHaveTextContent('bob@example.com')
    expect(within(row).getByRole('combobox', { name: 'Access for bob@example.com' })).toHaveTextContent('Viewer')
    await user.click(within(row).getByRole('button', { name: 'Remove access for bob@example.com' }))
    await waitFor(() => expect(within(dialog).queryByTestId('share-row')).not.toBeInTheDocument())
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true)
  })

  it('shares by email with the chosen role', async () => {
    let shares: SourceShare[] = []
    const fetchMock = mockApi({
      'GET /api/sources/src_1/shares': () => json(200, shares),
      'POST /api/sources/src_1/shares': () => {
        shares = [{ ...bob, role: 'analyst' }]
        return json(201, shares[0])
      },
    })
    const { user, dialog } = await open()
    expect(await within(dialog).findByText(/Not shared with anyone yet/)).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Email'), 'bob@example.com')
    await user.click(within(dialog).getByRole('combobox', { name: 'Access' }))
    await user.click(await screen.findByRole('option', { name: 'Analyst' }))
    await user.click(within(dialog).getByRole('button', { name: 'Share' }))
    const row = await within(dialog).findByTestId('share-row')
    expect(row).toHaveTextContent('bob@example.com')
    expect(within(row).getByRole('combobox', { name: 'Access for bob@example.com' })).toHaveTextContent('Analyst')
    expect(sentBody(fetchMock, 'POST /api/sources/src_1/shares')).toEqual({ email: 'bob@example.com', role: 'analyst' })
  })

  it('changes the role of an existing share', async () => {
    const fetchMock = mockApi({
      'GET /api/sources/src_1/shares': [bob],
      'POST /api/sources/src_1/shares': () => json(201, { ...bob, role: 'analyst' }),
    })
    const { user, dialog } = await open()
    await user.click(await within(dialog).findByRole('combobox', { name: 'Access for bob@example.com' }))
    await user.click(await screen.findByRole('option', { name: 'Analyst' }))
    await waitFor(() =>
      expect(sentBody(fetchMock, 'POST /api/sources/src_1/shares')).toEqual({
        email: 'bob@example.com',
        role: 'analyst',
      }),
    )
  })

  it('validates the email and shows the server message inline', async () => {
    mockApi({
      'GET /api/sources/src_1/shares': [],
      'POST /api/sources/src_1/shares': () =>
        json(404, { error: { code: 'not_found', message: 'No account exists with that email', details: {} } }),
    })
    const { user, dialog } = await open()
    await user.click(within(dialog).getByRole('button', { name: 'Share' }))
    expect(within(dialog).getByText(/Enter the email address/)).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Email'), 'nobody@example.com')
    await user.click(within(dialog).getByRole('button', { name: 'Share' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('No account exists with that email')
  })
})
