import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { analysis, claim } from '@/test/fixtures'
import { json, mockApi, renderWithProviders, testUser } from '@/test/utils'
import { AnswerView } from './AnswerView'
import { CostLine } from './CostLine'

afterEach(() => vi.unstubAllGlobals())

const HEADLINE = 'North had the highest revenue with 2,581,103.62.'
const headline = claim({ id: 'clm_head', section: 'headline', text: HEADLINE, ordinal: 0 })
const duplicate = claim({ id: 'clm_dup', section: 'summary', text: HEADLINE, ordinal: 1 })
const fact = claim({ id: 'clm_fact', section: 'segment', text: 'Coast had 1,923,494.92.', ordinal: 2 })

function stub(report: unknown = null) {
  return mockApi({
    'GET /api/analyses/ana_1/claims': [headline, duplicate, fact],
    'GET /api/analyses/ana_1/charts': [],
    'GET /api/analyses/ana_1/report': () =>
      report
        ? json(200, report)
        : json(404, { error: { code: 'not_found', message: 'No report has been generated', details: {} } }),
  })
}

describe('AnswerView headline', () => {
  it('opens the evidence drawer for the headline claim and does not list it again among the facts', async () => {
    stub()
    const onOpenClaim = vi.fn()
    renderWithProviders(
      <AnswerView analysis={analysis()} onOpenClaim={onOpenClaim} onFollowUp={vi.fn()} disabledFollowUps={false} />,
      { user: testUser() },
    )
    const button = await screen.findByRole('button', { name: /Open evidence for the headline/ })
    expect(button).toHaveAttribute('data-testid', 'answer-headline')
    expect(button).toHaveAttribute('data-status', 'verified')
    await userEvent.setup().click(button)
    expect(onOpenClaim).toHaveBeenCalledWith(headline)

    const claims = screen.getAllByTestId('claim')
    expect(claims).toHaveLength(1)
    expect(claims[0]).toHaveTextContent('Coast had 1,923,494.92.')
    expect(screen.getAllByText(HEADLINE)).toHaveLength(1)
  })

  it('falls back to plain text when the answer has no headline claim', async () => {
    mockApi({
      'GET /api/analyses/ana_1/claims': [fact],
      'GET /api/analyses/ana_1/charts': [],
      'GET /api/analyses/ana_1/report': () => json(404, { error: { code: 'not_found', message: 'x', details: {} } }),
    })
    renderWithProviders(
      <AnswerView analysis={analysis()} onOpenClaim={vi.fn()} onFollowUp={vi.fn()} disabledFollowUps={false} />,
      { user: testUser() },
    )
    await screen.findByTestId('claim')
    const el = screen.getByTestId('answer-headline')
    expect(el.tagName).toBe('P')
  })

  it("looks up the analysis' report directly and links to it", async () => {
    stub({ id: 'rpt_1', analysis_id: 'ana_1', title: 'r', content: {}, created_at: '2026-10-01T10:00:00Z' })
    renderWithProviders(
      <AnswerView analysis={analysis()} onOpenClaim={vi.fn()} onFollowUp={vi.fn()} disabledFollowUps={false} />,
      { user: testUser() },
    )
    expect(await screen.findByRole('button', { name: 'Open report' })).toBeInTheDocument()
  })

  it('offers to generate a report when the API answers 404', async () => {
    stub()
    renderWithProviders(
      <AnswerView analysis={analysis()} onOpenClaim={vi.fn()} onFollowUp={vi.fn()} disabledFollowUps={false} />,
      { user: testUser() },
    )
    expect(await screen.findByRole('button', { name: 'Generate report' })).toBeInTheDocument()
  })
})

describe('CostLine fast path', () => {
  it('says the answer came from the precomputed profile with 0 model calls', () => {
    renderWithProviders(<CostLine analysis={analysis({ plan: { fast_path: true }, llm_calls: 0, model: null })} />)
    const line = screen.getByTestId('cost-line')
    expect(within(line).getByTestId('fast-path')).toHaveTextContent(
      'Answered from the precomputed profile, 0 model calls',
    )
    expect(line).toHaveAttribute('data-fast-path', 'true')
  })

  it('shows the model call count otherwise', () => {
    renderWithProviders(<CostLine analysis={analysis({ llm_calls: 4 })} />)
    expect(screen.queryByTestId('fast-path')).not.toBeInTheDocument()
    expect(screen.getByTestId('cost-line')).toHaveTextContent('Model calls4')
  })
})
