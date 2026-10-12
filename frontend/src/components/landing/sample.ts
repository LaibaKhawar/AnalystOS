/**
 * SAMPLE DATA for the public landing page previews only. These objects are rendered by the
 * same components the app uses, and every preview is labelled "Sample data" on screen.
 */
import type { AnalysisEvent, Chart, ClaimEvidence } from '@/api/types'

const SQL = `SELECT region,
       SUM(revenue) AS revenue
FROM sales
WHERE date >= DATE '2026-01-01'
  AND date <  DATE '2027-01-01'
GROUP BY region
ORDER BY revenue DESC
LIMIT 5000`

export const SAMPLE_CHART: Chart = {
  id: 'sample-chart',
  title: 'Revenue by region, 2026 (sample data)',
  chart_type: 'bar',
  spec: { x: 'region', y: ['revenue'], x_label: 'region', y_label: 'revenue', y_zero: true },
  data: [
    { region: 'North', revenue: 2581103.62 },
    { region: 'Coast', revenue: 1923494.92 },
    { region: 'Capital', revenue: 1774909.68 },
    { region: 'Valley', revenue: 1314771.85 },
    { region: 'South', revenue: 1080019.98 },
  ],
  data_hash: 'sample',
  interpretation: null,
  verified: true,
  result_table_id: 'sample-result',
}

export const SAMPLE_EVIDENCE: ClaimEvidence = {
  claim: {
    id: 'sample-claim',
    ordinal: 0,
    section: 'summary',
    kind: 'fact',
    text: 'North generated the highest revenue in 2026 with $2,581,103.62, 34% more than Coast.',
    original_text: null,
    status: 'verified',
    numbers: ['$2,581,103.62', '34%'],
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
        {
          token: '34%',
          value: 34.19,
          value_key: null,
          finding_id: 'f1',
          finding_label: 'F1',
          derived_formula: '(F1.revenue - F2.revenue) / F2.revenue = 34.19%',
        },
      ],
      unsupported: [],
      notes: [],
      citations: ['F1', 'F2'],
    },
    evidence: [],
  },
  evidence: [
    {
      id: 'sample-evidence',
      source_type: 'sql_query',
      values: { revenue: 2581103.62 },
      formula: null,
      description: null,
      finding: { label: 'F1', statement: 'Total revenue in 2026 for region North', kind: 'value' },
      execution: null,
      sql: [
        {
          id: 'sample-sql',
          sql: SQL,
          status: 'success',
          row_count: 5,
          duration_ms: 3,
          created_at: '2026-10-12T12:50:51Z',
        },
      ],
      python: [],
      result: {
        id: 'sample-result',
        name: 'total revenue by region',
        columns: [{ name: 'region' }, { name: 'revenue' }],
        rows: [
          ['North', 2581103.62],
          ['Coast', 1923494.92],
          ['Capital', 1774909.68],
        ],
        row_count: 5,
        truncated: false,
      },
    },
  ],
}

const t = (s: number) => new Date(Date.UTC(2026, 9, 12, 12, 50, s)).toISOString()
export const SAMPLE_EVENTS: AnalysisEvent[] = [
  { id: 1, type: 'status', message: 'Planning the analysis', payload: {}, created_at: t(2) },
  { id: 2, type: 'plan', message: 'Plan with 3 steps', payload: {}, created_at: t(9) },
  { id: 3, type: 'step_completed', message: 'Aggregate revenue by region', payload: {}, created_at: t(11) },
  {
    id: 4,
    type: 'retry',
    message: 'Retrying Compare to prior year after unknown column',
    payload: {},
    created_at: t(14),
  },
  { id: 5, type: 'step_completed', message: 'Compare to prior year', payload: {}, created_at: t(17) },
  {
    id: 6,
    type: 'verification',
    message: '7 claims verified, 1 unsupported removed, 1/1 charts verified',
    payload: {},
    created_at: t(31),
  },
]

export const BLOCKED_SQL = `-- Proposed by the model
DELETE FROM sales WHERE region = 'South';

-- Validator: rejected before execution
-- Only single SELECT statements may run.`
