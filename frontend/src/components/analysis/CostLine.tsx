import type { Analysis } from '@/api/types'
import { formatCost, formatDuration, formatTokens } from '@/lib/format'

/** Per-analysis cost and verification line. Local models cost $0.0000. */
export function CostLine({ analysis }: { analysis: Analysis }) {
  const v = analysis.answer?.verification
  const parts: { label: string; value: string }[] = [
    { label: 'Model', value: analysis.model ?? 'unknown' },
    {
      label: 'Tokens',
      value: `${formatTokens(analysis.input_tokens)} in / ${formatTokens(analysis.output_tokens)} out`,
    },
    { label: 'Cost', value: formatCost(analysis.cost_usd) },
    { label: 'Latency', value: formatDuration(analysis.latency_ms) },
  ]
  if (v) {
    parts.push({ label: 'Verified', value: String(v.verified ?? 0) })
    parts.push({ label: 'Removed', value: String(v.removed ?? 0) })
    parts.push({ label: 'Repaired', value: String(v.repaired ?? 0) })
    parts.push({ label: 'Charts verified', value: `${v.charts_verified ?? 0}/${v.charts_total ?? 0}` })
  }
  return (
    <dl className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-[11px]" data-testid="cost-line">
      {parts.map((p) => (
        <div key={p.label} className="flex gap-1">
          <dt>{p.label}</dt>
          <dd className="tabular text-foreground/80 font-mono">{p.value}</dd>
        </div>
      ))}
    </dl>
  )
}
