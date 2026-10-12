import { describe, expect, it } from 'vitest'
import type { EvaluationRun } from '@/api/types'
import { bestIndices, COMPARE_ROWS, compareValue, parseRunIds } from './compare'

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

describe('bestIndices', () => {
  it('picks the highest value when higher is better', () => {
    expect([...bestIndices([0.9, 0.95, 0.8], 'higher')]).toEqual([1])
  })
  it('picks the lowest value when lower is better', () => {
    expect([...bestIndices([74633, 94400, 477021], 'lower')]).toEqual([0])
  })
  it('marks every tie as best', () => {
    expect([...bestIndices([0.5, 1, 1], 'higher')]).toEqual([1, 2])
  })
  it('ignores missing and non-numeric values', () => {
    expect([...bestIndices([null, 0.2, 'n/a', 0.1], 'lower')]).toEqual([3])
  })
  it('highlights nothing when values are all equal, fewer than two are numeric, or there is no direction', () => {
    expect(bestIndices([0, 0, 0], 'lower').size).toBe(0)
    expect(bestIndices([0.5, null], 'higher').size).toBe(0)
    expect(bestIndices([1, 2], null).size).toBe(0)
  })
})

describe('compare rows', () => {
  it('has the right direction for each key metric', () => {
    const better = Object.fromEntries(COMPARE_ROWS.map((r) => [r.key, r.better]))
    expect(better).toMatchObject({
      model: null,
      pass_rate: 'higher',
      numerical_accuracy: 'higher',
      entity_accuracy: 'higher',
      unsupported_claim_rate_final: 'lower',
      unsupported_claim_rate_draft: 'lower',
      retry_recovery_rate: 'higher',
      first_pass_success_rate: 'higher',
      latency_p50_ms: 'lower',
      latency_p95_ms: 'lower',
      avg_cost_usd: 'lower',
      avg_llm_calls: 'lower',
    })
  })

  it('reads the model and metrics from runs', () => {
    const runs = [
      run('a', 'qwen3-8b', { pass_rate: 0.94, avg_llm_calls: 2.4 }),
      run('b', 'llama-3.1-8b', { pass_rate: 0.86, avg_llm_calls: 2.6 }),
    ]
    expect(runs.map((r) => compareValue(r, 'model'))).toEqual(['qwen3-8b', 'llama-3.1-8b'])
    const passRates = runs.map((r) => compareValue(r, 'pass_rate'))
    expect([...bestIndices(passRates, 'higher')]).toEqual([0])
    expect(compareValue(runs[0], 'entity_accuracy')).toBeNull()
  })

  it('parses at most four unique run ids', () => {
    expect(parseRunIds('a,b,,a,c,d,e')).toEqual(['a', 'b', 'c', 'd'])
    expect(parseRunIds(null)).toEqual([])
  })
})
