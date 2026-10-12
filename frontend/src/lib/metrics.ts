import type { EvaluationCase, MetricValue } from '@/api/types'
import { formatCost, formatDuration, formatInteger, formatNumber, formatPercent, humanize } from './format'

const RATE = /(rate|accuracy|correctness|precision|recall|score|success)/i

export function formatMetric(key: string, value: MetricValue): string {
  if (typeof value !== 'number') return value === null || value === undefined ? '-' : String(value)
  if (/_ms$/.test(key)) return formatDuration(value)
  if (/cost/.test(key)) return formatCost(value)
  if (/tokens/.test(key)) return formatInteger(value)
  if (RATE.test(key) && value >= 0 && value <= 1) return formatPercent(value, 1)
  return formatNumber(value)
}

const ACRONYMS: Record<string, string> = { sql: 'SQL', llm: 'LLM', usd: 'USD', pii: 'PII' }

export function metricLabel(key: string): string {
  return humanize(key)
    .split(' ')
    .map((w) => ACRONYMS[w.toLowerCase()] ?? w)
    .join(' ')
    .replace(/\bms\b/i, '')
    .replace(/\busd\b/i, '')
    .replace(/\bp(\d+)\b/, 'p$1')
    .trim()
}

export function scalarMetrics(metrics: Record<string, MetricValue>): [string, MetricValue][] {
  return Object.entries(metrics).filter(([, v]) => v === null || typeof v !== 'object')
}

export interface CategoryRate {
  category: string
  pass_rate: number
  passed: number
  total: number
}

/** Pass rate per category, computed from cases (preferred) or the run's by_category metric. */
export function categoryRates(cases: EvaluationCase[] | undefined, byCategory: unknown): CategoryRate[] {
  if (cases && cases.length) {
    const map = new Map<string, { passed: number; total: number }>()
    for (const c of cases) {
      const entry = map.get(c.category) ?? { passed: 0, total: 0 }
      entry.total += 1
      if (c.passed) entry.passed += 1
      map.set(c.category, entry)
    }
    return [...map.entries()].map(([category, v]) => ({ category, ...v, pass_rate: v.total ? v.passed / v.total : 0 }))
  }
  if (byCategory && typeof byCategory === 'object') {
    return Object.entries(byCategory as Record<string, unknown>).flatMap(([category, v]) => {
      if (typeof v === 'number') return [{ category, pass_rate: v, passed: 0, total: 0 }]
      if (v && typeof v === 'object') {
        const o = v as Record<string, unknown>
        const total =
          typeof o.total === 'number'
            ? o.total
            : typeof o.cases === 'number'
              ? o.cases
              : typeof o.n === 'number'
                ? o.n
                : 0
        const passed = typeof o.passed === 'number' ? o.passed : 0
        const rate =
          typeof o.pass_rate === 'number'
            ? o.pass_rate
            : typeof o.accuracy === 'number'
              ? o.accuracy
              : total
                ? passed / total
                : 0
        return [{ category, pass_rate: rate, passed, total }]
      }
      return []
    })
  }
  return []
}

export function latencyBins(cases: EvaluationCase[], bins = 8): { label: string; count: number }[] {
  const values = cases.map((c) => c.latency_ms).filter((v): v is number => typeof v === 'number')
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const width = (max - min) / bins || 1
  const out = Array.from({ length: bins }, (_, i) => ({ label: `${formatDuration(min + i * width)}`, count: 0 }))
  for (const v of values) out[Math.min(bins - 1, Math.floor((v - min) / width))].count += 1
  return out
}
