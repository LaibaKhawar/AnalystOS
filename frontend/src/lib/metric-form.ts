import type { JsonValue, MetricDefinition, MetricFilter, MetricFormat, MetricInput } from '@/api/types'

export const METRIC_FORMATS: { value: MetricFormat; label: string }[] = [
  { value: 'number', label: 'Number' },
  { value: 'currency', label: 'Currency' },
  { value: 'percent', label: 'Percent' },
]

export const FILTER_OPS: { value: string; label: string; needsValue: boolean }[] = [
  { value: '=', label: 'equals', needsValue: true },
  { value: '!=', label: 'does not equal', needsValue: true },
  { value: '>', label: 'greater than', needsValue: true },
  { value: '>=', label: 'at least', needsValue: true },
  { value: '<', label: 'less than', needsValue: true },
  { value: '<=', label: 'at most', needsValue: true },
  { value: 'in', label: 'is one of', needsValue: true },
  { value: 'not_in', label: 'is not one of', needsValue: true },
  { value: 'contains', label: 'contains', needsValue: true },
  { value: 'is_null', label: 'is empty', needsValue: false },
  { value: 'not_null', label: 'is not empty', needsValue: false },
]

const opNeedsValue = (op: string) => FILTER_OPS.find((o) => o.value === op)?.needsValue ?? true
const isListOp = (op: string) => op === 'in' || op === 'not_in'

export interface FilterDraft {
  key: string
  column: string
  op: string
  value: string
}

export interface MetricDraft {
  name: string
  label: string
  description: string
  table: string
  expression: string
  format: MetricFormat
  filters: FilterDraft[]
}

export type MetricField = 'name' | 'label' | 'description' | 'table' | 'expression' | 'format' | 'filters'
export type MetricErrors = Partial<Record<MetricField | 'form', string>>

export const METRIC_NAME = /^[a-z][a-z0-9_]{1,62}$/

let filterSeq = 0
export const newFilter = (column = ''): FilterDraft => ({ key: `f${(filterSeq += 1)}`, column, op: '=', value: '' })

function valueToText(value: JsonValue): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map((v) => (v === null ? '' : String(v))).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function emptyDraft(table = ''): MetricDraft {
  return { name: '', label: '', description: '', table, expression: '', format: 'number', filters: [] }
}

export function draftFromMetric(metric: MetricDefinition): MetricDraft {
  const format = (['number', 'currency', 'percent'] as const).find((f) => f === metric.format) ?? 'number'
  return {
    name: metric.name,
    label: metric.label,
    description: metric.description ?? '',
    table: metric.table_name,
    expression: metric.expression,
    format,
    filters: (metric.filters ?? []).map((f: MetricFilter) => ({
      ...newFilter(f.column),
      op: f.op || '=',
      value: valueToText(f.value),
    })),
  }
}

/** "Average order value" to avg_order_value, as a name suggestion while typing the label. */
export function suggestName(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/^(\d)/, 'm_$1')
    .slice(0, 63)
}

/** Client-side checks that mirror the API's, so obvious mistakes are caught before a round trip. */
export function validateMetricDraft(d: MetricDraft): MetricErrors {
  const e: MetricErrors = {}
  const name = d.name.trim()
  if (!name) e.name = 'Give the metric a name, for example avg_order_value.'
  else if (!METRIC_NAME.test(name))
    e.name = 'Use snake_case: lowercase letters, digits and underscores, starting with a letter (2 to 63 characters).'
  if (!d.label.trim()) e.label = 'Add a human readable label, for example Average order value.'
  if (!d.table) e.table = 'Choose the table the metric is computed on.'
  const expr = d.expression.trim()
  if (expr.length < 3) e.expression = 'Write an aggregate expression, for example SUM(revenue) / COUNT(*).'
  if (d.description.length > 2000) e.description = 'Use 2000 characters or fewer.'
  const incomplete = d.filters.find((f) => !f.column || (opNeedsValue(f.op) && f.value.trim() === ''))
  if (incomplete) e.filters = 'Each filter needs a column and, except for empty checks, a value. Remove unused rows.'
  return e
}

function parseScalar(text: string): JsonValue {
  const t = text.trim()
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t)
  if (t === 'true') return true
  if (t === 'false') return false
  return t
}

export function filterValue(f: Pick<FilterDraft, 'op' | 'value'>): JsonValue {
  if (!opNeedsValue(f.op)) return null
  if (isListOp(f.op))
    return f.value
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean)
      .map(parseScalar)
  return parseScalar(f.value)
}

export function toMetricInput(d: MetricDraft): MetricInput {
  return {
    name: d.name.trim(),
    label: d.label.trim(),
    description: d.description.trim() || null,
    table: d.table,
    expression: d.expression.trim(),
    format: d.format,
    filters: d.filters.map((f) => ({ column: f.column, op: f.op, value: filterValue(f) })),
  }
}

/**
 * Attach a server validation message to the field it is about. The API's messages are precise
 * ("A metric must aggregate, for example SUM(...)"), so they are shown verbatim next to that field.
 */
export function fieldForServerError(message: string): MetricField | 'form' {
  const pydantic = /^(name|label|description|table|expression|format|filters)[.:]/.exec(message)
  if (pydantic) return pydantic[1] as MetricField
  if (/metric named|metric names/i.test(message)) return 'name'
  if (/unknown table/i.test(message)) return 'table'
  if (/expression|aggregate|unknown column|sql validator|not valid sql|not a query/i.test(message)) return 'expression'
  return 'form'
}
