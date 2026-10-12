import type { EvaluationRun, MetricValue } from '@/api/types'

export type Better = 'higher' | 'lower'

export interface CompareRow {
  key: string
  label: string
  /** Which direction wins; rows without one (the model name) are never highlighted. */
  better: Better | null
}

export const COMPARE_ROWS: CompareRow[] = [
  { key: 'model', label: 'Model', better: null },
  { key: 'pass_rate', label: 'Pass rate', better: 'higher' },
  { key: 'numerical_accuracy', label: 'Numerical accuracy', better: 'higher' },
  { key: 'entity_accuracy', label: 'Entity accuracy', better: 'higher' },
  { key: 'unsupported_claim_rate_draft', label: 'Unsupported claims, draft', better: 'lower' },
  { key: 'unsupported_claim_rate_final', label: 'Unsupported claims, final', better: 'lower' },
  { key: 'retry_recovery_rate', label: 'Retry recovery', better: 'higher' },
  { key: 'first_pass_success_rate', label: 'First pass success', better: 'higher' },
  { key: 'latency_p50_ms', label: 'Latency p50', better: 'lower' },
  { key: 'latency_p95_ms', label: 'Latency p95', better: 'lower' },
  { key: 'avg_cost_usd', label: 'Average cost', better: 'lower' },
  { key: 'avg_llm_calls', label: 'Average LLM calls', better: 'lower' },
]

export const MIN_COMPARE = 2
export const MAX_COMPARE = 4

export function compareValue(run: EvaluationRun, key: string): MetricValue {
  if (key === 'model') return run.model
  return run.metrics[key] ?? null
}

/**
 * Indices of the best value in a row. Only finite numbers compete; ties are all best.
 * Nothing is highlighted when fewer than two runs have a number, or when every number is equal,
 * because a "winner" there would mean nothing.
 */
export function bestIndices(values: MetricValue[], better: Better | null): Set<number> {
  const best = new Set<number>()
  if (!better) return best
  const numeric = values
    .map((v, i) => ({ v, i }))
    .filter((x): x is { v: number; i: number } => typeof x.v === 'number' && Number.isFinite(x.v))
  if (numeric.length < 2) return best
  const target = better === 'higher' ? Math.max(...numeric.map((x) => x.v)) : Math.min(...numeric.map((x) => x.v))
  if (numeric.every((x) => x.v === target)) return best
  for (const x of numeric) if (x.v === target) best.add(x.i)
  return best
}

/** Parse and clamp the `runs` query parameter: unique ids, at most MAX_COMPARE. */
export function parseRunIds(param: string | null): string[] {
  if (!param) return []
  return [
    ...new Set(
      param
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ].slice(0, MAX_COMPARE)
}
