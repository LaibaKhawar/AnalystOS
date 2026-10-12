import { describe, expect, it } from 'vitest'
import type { EvaluationCase } from '@/api/types'
import { categoryRates, formatMetric } from './metrics'

describe('evaluation metrics', () => {
  it('reads by_category in the shape the eval runner writes', () => {
    const rates = categoryRates(undefined, { numeric: { cases: 2, passed: 1, pass_rate: 0.5 } })
    expect(rates).toEqual([{ category: 'numeric', pass_rate: 0.5, passed: 1, total: 2 }])
  })

  it('prefers per-case results when present', () => {
    const c = (category: string, passed: boolean) => ({ category, passed }) as EvaluationCase
    expect(categoryRates([c('a', true), c('a', false), c('b', true)], undefined)).toEqual([
      { category: 'a', passed: 1, total: 2, pass_rate: 0.5 },
      { category: 'b', passed: 1, total: 1, pass_rate: 1 },
    ])
  })

  it('formats metric values by key', () => {
    expect(formatMetric('numerical_accuracy', 0.95)).toBe('95%')
    expect(formatMetric('latency_p50_ms', 382945)).toBe('6m 23s')
    expect(formatMetric('avg_cost_usd', 0)).toBe('$0.0000')
    expect(formatMetric('avg_input_tokens', 8158)).toBe('8,158')
    expect(formatMetric('safety_pass_rate', null)).toBe('-')
  })
})
