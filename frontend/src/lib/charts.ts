import type { Chart, ChartDatum } from '@/api/types'

export type ChartRenderer =
  'line' | 'area' | 'bar' | 'stacked_bar' | 'scatter' | 'histogram' | 'box' | 'heatmap' | 'table'

export const MAX_SERIES = 6

export const SERIES_COLORS = Array.from({ length: MAX_SERIES }, (_, i) => `var(--chart-${i + 1})`)

const has = (row: ChartDatum | undefined, keys: string[]) => Boolean(row) && keys.every((k) => k in (row as ChartDatum))

/**
 * Pick how to draw a chart from its chart_type, falling back to a table when the data
 * does not have the shape that chart type needs (so a malformed spec never renders a misleading chart).
 */
export function selectRenderer(chart: Pick<Chart, 'chart_type' | 'spec' | 'data'>): ChartRenderer {
  const first = chart.data[0]
  if (!first) return 'table'
  const y = chart.spec?.y ?? []
  const x = chart.spec?.x
  switch (chart.chart_type) {
    case 'histogram':
      return has(first, ['label', 'count']) ? 'histogram' : 'table'
    case 'box':
      return has(first, ['group', 'min', 'q1', 'median', 'q3', 'max']) ? 'box' : 'table'
    case 'heatmap':
      return has(first, ['x', 'y', 'value']) ? 'heatmap' : 'table'
    case 'line':
    case 'area':
    case 'bar':
    case 'stacked_bar':
    case 'scatter':
      if (!x || y.length === 0 || !has(first, [x])) return 'table'
      if (!y.some((key) => key in first)) return 'table'
      return chart.chart_type as ChartRenderer
    default:
      return 'table'
  }
}

/** Series keys to plot, capped to the validated palette size. */
export function seriesKeys(chart: Pick<Chart, 'spec' | 'data'>): { keys: string[]; hidden: number } {
  const first = chart.data[0] ?? {}
  const keys = (chart.spec?.y ?? []).filter((k) => k in first)
  return { keys: keys.slice(0, MAX_SERIES), hidden: Math.max(0, keys.length - MAX_SERIES) }
}

/** Value domain lower bound: bars and areas always start at zero. */
export function zeroBasedDomain(values: number[]): [number, number] {
  const finite = values.filter((v) => Number.isFinite(v))
  if (finite.length === 0) return [0, 1]
  const min = Math.min(0, ...finite)
  const max = Math.max(0, ...finite)
  return [min, max === min ? min + 1 : max]
}

/** Table view of a chart's data (used for the accessible table toggle and the fallback renderer). */
export function chartTable(data: ChartDatum[]): { columns: string[]; rows: ChartDatum[keyof ChartDatum][][] } {
  const columns = Array.from(new Set(data.flatMap((row) => Object.keys(row))))
  return { columns, rows: data.map((row) => columns.map((c) => row[c] ?? null)) }
}

export function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value)
  return null
}
