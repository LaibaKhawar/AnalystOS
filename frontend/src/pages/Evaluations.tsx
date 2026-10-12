import { ScalesIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorState } from '@/components/common/States'
import { EvalEmpty } from '@/components/evaluations/EvalEmpty'
import { Pill } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { useEvaluations } from '@/hooks/queries/evaluations'
import { MAX_COMPARE, MIN_COMPARE } from '@/lib/compare'
import { formatDateTime } from '@/lib/format'
import { formatMetric, metricLabel } from '@/lib/metrics'

const HEADLINE = ['numerical_accuracy', 'answer_accuracy', 'unsupported_claim_rate_final', 'latency_p50_ms']

function CompareBar({
  selected,
  onCompare,
  onClear,
}: {
  selected: string[]
  onCompare: () => void
  onClear: () => void
}) {
  const ready = selected.length >= MIN_COMPARE
  return (
    <div
      className="bg-muted/30 flex flex-col gap-2 rounded-lg border px-3 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between"
      role="region"
      aria-label="Compare runs"
    >
      <p className="text-muted-foreground" aria-live="polite">
        {selected.length === 0
          ? `Select ${MIN_COMPARE} to ${MAX_COMPARE} runs to compare their metrics side by side.`
          : `${selected.length} of ${MAX_COMPARE} selected.${ready ? '' : ' Select at least one more.'}`}
      </p>
      <div className="flex items-center gap-2">
        {selected.length > 0 && (
          <Button variant="ghost" size="sm" onClick={onClear}>
            Clear
          </Button>
        )}
        <Button size="sm" onClick={onCompare} disabled={!ready} data-testid="compare-runs">
          <ScalesIcon data-icon="inline-start" />
          Compare {ready ? selected.length : ''} runs
        </Button>
      </div>
    </div>
  )
}

export default function Evaluations() {
  const runs = useEvaluations()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string[]>([])
  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => (on ? [...prev, id].slice(0, MAX_COMPARE) : prev.filter((x) => x !== id)))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Evaluations"
        description="How accurately the analyst answers questions with known ground truth, and what it costs."
      />
      {runs.isPending && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}
      {runs.isError && <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />}
      {runs.data?.length === 0 && <EvalEmpty />}
      {(runs.data?.length ?? 0) > 1 && (
        <CompareBar
          selected={selected}
          onClear={() => setSelected([])}
          onCompare={() => navigate(`/evaluations/compare?runs=${selected.map(encodeURIComponent).join(',')}`)}
        />
      )}
      {(runs.data?.length ?? 0) > 0 && (
        <ul className="bg-card divide-y rounded-lg border">
          {runs.data?.map((run) => {
            const checked = selected.includes(run.id)
            const full = !checked && selected.length >= MAX_COMPARE
            return (
              <li key={run.id} className="hover:bg-muted/40 flex items-start gap-3 pl-4 sm:items-center">
                <Checkbox
                  checked={checked}
                  disabled={full}
                  onCheckedChange={(v) => toggle(run.id, v === true)}
                  aria-label={`Compare ${run.suite} run on ${run.model ?? 'unknown model'} from ${formatDateTime(run.created_at)}`}
                  title={full ? `You can compare up to ${MAX_COMPARE} runs` : undefined}
                  className="mt-4 sm:mt-0"
                />
                <Link
                  to={`/evaluations/${run.id}`}
                  className="focus-visible:ring-ring/60 flex min-w-0 flex-1 flex-col gap-2 py-3 pr-4 outline-none focus-visible:ring-2 sm:flex-row sm:items-center"
                >
                  <span className="min-w-0 flex-1">
                    <span className="text-foreground block text-sm font-medium">{run.suite}</span>
                    <span className="text-muted-foreground block text-xs">
                      {run.model ?? 'unknown model'}, {formatDateTime(run.created_at)}
                    </span>
                  </span>
                  <span className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                    {HEADLINE.filter((k) => k in run.metrics).map((k) => (
                      <span key={k} className="text-muted-foreground">
                        {metricLabel(k)}{' '}
                        <span className="tabular text-foreground font-mono">{formatMetric(k, run.metrics[k])}</span>
                      </span>
                    ))}
                  </span>
                  <Pill tone={run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : 'neutral'}>
                    {run.status}
                  </Pill>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
