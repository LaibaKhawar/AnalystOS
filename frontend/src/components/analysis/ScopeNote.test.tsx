import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Answer } from '@/api/types'
import { plainAssumptions } from '@/lib/scope'
import { renderWithProviders } from '@/test/utils'
import { describeEvent } from './events'
import { ScopeNote } from './ScopeNote'

const issue = (detail: string) => ({ step_id: 's1', kind: 'filter', detail, column: 'region' })

describe('ScopeNote', () => {
  it('renders nothing when the plan matched the question', () => {
    const { container } = renderWithProviders(
      <ScopeNote answer={{ scope: { issues_found: 0, fixed: 0, remaining: [] } }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a small note when the plan was narrowed and corrected', () => {
    renderWithProviders(<ScopeNote answer={{ scope: { issues_found: 2, fixed: 2, remaining: [] } }} />)
    const note = screen.getByTestId('scope-note')
    expect(note).toHaveAttribute('data-state', 'fixed')
    expect(note).toHaveTextContent('Scope corrected')
    expect(note).toHaveTextContent('2 places')
  })

  it('shows a visible caveat listing restrictions that remain', () => {
    const answer: Answer = {
      scope: {
        issues_found: 2,
        fixed: 1,
        remaining: [issue("Filters region = 'North', which the question did not ask for")],
      },
      assumptions: ["Scope: Filters region = 'North', which the question did not ask for", 'Revenue is net of refunds'],
    }
    renderWithProviders(<ScopeNote answer={answer} />)
    const note = screen.getByTestId('scope-note')
    expect(note).toHaveAttribute('data-state', 'remaining')
    expect(note).toHaveTextContent('This answer is narrower than your question')
    expect(note).toHaveTextContent('1 was corrected')
    expect(note).toHaveTextContent("Filters region = 'North'")
    expect(plainAssumptions(answer)).toEqual(['Revenue is net of refunds'])
  })

  it('falls back to "Scope:" assumptions when the answer has no scope report', () => {
    renderWithProviders(<ScopeNote answer={{ assumptions: ['Scope: Limits the period to 2025'] }} />)
    expect(screen.getByTestId('scope-note')).toHaveTextContent('Limits the period to 2025')
  })

  it('describes scope_check stream events', () => {
    const text = describeEvent({
      id: 3,
      type: 'scope_check',
      message: 'Plan narrows the question in 1 place(s); correcting the scope',
      payload: {},
      created_at: '2026-10-13T10:00:00Z',
    })
    expect(text).toEqual({
      text: 'Scope check: Plan narrows the question in 1 place(s); correcting the scope',
      tone: 'warning',
    })
  })
})
