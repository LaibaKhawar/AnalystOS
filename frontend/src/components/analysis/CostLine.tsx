import { LightningIcon } from '@phosphor-icons/react'
import type { Analysis } from '@/api/types'
import { formatCost, formatDuration, formatInteger, formatTokens } from '@/lib/format'

/**
 * Per-analysis cost and verification line. Local models cost $0.0000. Answers served from the precomputed
 * dataset profile (plan.fast_path) say so: they made no model calls at all.
 */
export function CostLine({ analysis }: { analysis: Analysis }) {
  const v = analysis.answer?.verification
  const fast = analysis.plan?.fast_path === true
  const parts: { label: string; value: string }[] = [
    { label: 'Model', value: fast ? 'none' : (analysis.model ?? 'unknown') },
    { label: 'Model calls', value: formatInteger(analysis.llm_calls) },
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
    <dl
      className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]"
      data-testid="cost-line"
      data-fast-path={fast || undefined}
    >
      {fast && (
        <div className="text-brand-text flex items-center gap-1 font-medium" data-testid="fast-path">
          <dt className="sr-only">Path</dt>
          <dd className="flex items-center gap-1">
            <LightningIcon className="size-3" weight="fill" aria-hidden="true" />
            Answered from the precomputed profile, 0 model calls
          </dd>
        </div>
      )}
      {parts.map((p) => (
        <div key={p.label} className="flex gap-1">
          <dt>{p.label}</dt>
          <dd className="tabular text-foreground/80 font-mono">{p.value}</dd>
        </div>
      ))}
    </dl>
  )
}
