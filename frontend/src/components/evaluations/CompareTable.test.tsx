import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { EvaluationRun } from '@/api/types'
import { renderWithProviders } from '@/test/utils'
import { CompareTable } from './CompareTable'

const run = (id: string, model: string, metrics: EvaluationRun['metrics']): EvaluationRun => ({
  id,
  suite: 'core',
  model,
  status: 'completed',
  metrics,
  config: {},
  notes: null,
  created_at: '2026-10-01T10:00:00Z',
  completed_at: null,
})

describe('CompareTable', () => {
  it('highlights the best value per row in the right direction', () => {
    renderWithProviders(
      <CompareTable
        runs={[
          run('a', 'qwen3-8b', { pass_rate: 0.9444, latency_p50_ms: 74633, avg_cost_usd: 0 }),
          run('b', 'llama-3.1-8b', { pass_rate: 0.8571, latency_p50_ms: 94400, avg_cost_usd: 0 }),
        ]}
      />,
    )
    const cells = (key: string) => within(screen.getByTestId(`compare-row-${key}`)).getAllByRole('cell')
    expect(cells('pass_rate')[0]).toHaveAttribute('data-best', 'true')
    expect(cells('pass_rate')[0]).toHaveTextContent('(best)')
    expect(cells('pass_rate')[1]).not.toHaveAttribute('data-best')
    expect(cells('latency_p50_ms')[0]).toHaveAttribute('data-best', 'true')
    expect(cells('avg_cost_usd').some((c) => c.hasAttribute('data-best'))).toBe(false)
    expect(cells('model').map((c) => c.textContent)).toEqual(['qwen3-8b', 'llama-3.1-8b'])
  })
})
