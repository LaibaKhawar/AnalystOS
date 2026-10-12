import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClaimEvidence } from '@/api/types'
import { renderWithProviders } from '@/test/utils'
import { EvidenceContent } from './EvidenceContent'
import { EvidenceDrawer } from './EvidenceDrawer'

const SQL = 'SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region'

const evidence: ClaimEvidence = {
  claim: {
    id: 'clm_1',
    ordinal: 0,
    section: 'summary',
    kind: 'fact',
    text: 'Karachi generated the highest revenue in 2026 with $2,581,103.62.',
    original_text: null,
    status: 'verified',
    numbers: ['$2,581,103.62'],
    verification: {
      matches: [
        {
          token: '$2,581,103.62',
          value: 2581103.62,
          value_key: 'revenue',
          finding_id: 'f1',
          finding_label: 'F1',
          derived_formula: null,
        },
      ],
      unsupported: [],
      notes: ['$2,581,103.62 matched uncited finding F1'],
      citations: ['F1'],
    },
    evidence: [],
  },
  evidence: [
    {
      id: 'evd_1',
      source_type: 'sql_query',
      values: { revenue: 2581103.62 },
      formula: null,
      description: null,
      finding: { label: 'F1', statement: 'total revenue in 2026 for Karachi', kind: 'value' },
      execution: {
        id: 'exec_abc',
        tool: 'aggregate_metric',
        status: 'success',
        attempt: 1,
        input: {},
        duration_ms: 17,
        created_at: '2026-10-12T12:50:51Z',
      },
      sql: [
        { id: 'sql_1', sql: SQL, status: 'success', row_count: 5, duration_ms: 3, created_at: '2026-10-12T12:50:51Z' },
      ],
      python: [],
      result: {
        id: 'res_1',
        name: 'total revenue by region',
        columns: [{ name: 'region' }, { name: 'revenue' }],
        rows: [
          ['Karachi', 2581103.62],
          ['Lahore', 1923494.92],
        ],
        row_count: 5,
        truncated: false,
      },
    },
  ],
}

describe('EvidenceContent', () => {
  it('renders the claim, number checks, finding, SQL, rows and execution metadata', () => {
    renderWithProviders(<EvidenceContent data={evidence} analysisId="ana_1" />)
    expect(screen.getByTestId('evidence-claim-text')).toHaveTextContent('Karachi generated the highest revenue')
    expect(screen.getByText('Verified')).toBeInTheDocument()
    expect(screen.getByText('total revenue in 2026 for Karachi')).toBeInTheDocument()
    expect(screen.getByText('SQL query')).toBeInTheDocument()
    expect(screen.getAllByText(/SELECT region, SUM\(revenue\)/).length).toBeGreaterThan(0)
    const table = screen.getByRole('table', { name: 'total revenue by region' })
    expect(within(table).getByText('Lahore')).toBeInTheDocument()
    expect(screen.getByText('exec_abc')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Download result CSV/ })).toBeInTheDocument()
    expect(screen.getByText(/matched uncited finding F1/)).toBeInTheDocument()
  })

  it('shows unsupported numbers and hides downloads in preview mode', () => {
    const data: ClaimEvidence = {
      ...evidence,
      claim: { ...evidence.claim, status: 'qualified', verification: { unsupported: ['12%'], notes: [] } },
    }
    renderWithProviders(<EvidenceContent data={data} analysisId="x" preview />)
    expect(screen.getByText('Unsupported numbers: 12%')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Download result CSV/ })).not.toBeInTheDocument()
  })

  it('explains claims that have no numbers', () => {
    const data: ClaimEvidence = { claim: { ...evidence.claim, status: 'no_numbers', verification: {} }, evidence: [] }
    renderWithProviders(<EvidenceContent data={data} analysisId="x" />)
    expect(screen.getByText(/contains no numbers/)).toBeInTheDocument()
  })
})

describe('EvidenceDrawer', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => vi.stubGlobal('fetch', fetchMock))
  afterEach(() => {
    fetchMock.mockReset()
    vi.unstubAllGlobals()
  })

  it('fetches evidence for the selected claim and closes', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(evidence), { status: 200 }))
    const onClose = vi.fn()
    renderWithProviders(<EvidenceDrawer analysisId="ana_1" claimId="clm_1" onClose={onClose} />)
    expect(await screen.findByTestId('evidence-claim-text')).toBeInTheDocument()
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/analyses/ana_1/claims/clm_1/evidence')
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('shows the backend error message with a retry action', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'not_found', message: 'Claim not found', details: {} } }), {
        status: 404,
      }),
    )
    renderWithProviders(<EvidenceDrawer analysisId="ana_1" claimId="clm_x" onClose={() => undefined} />)
    expect(await screen.findByText('Claim not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
  })
})
