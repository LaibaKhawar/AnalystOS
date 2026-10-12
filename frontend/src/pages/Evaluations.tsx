import { Link } from 'react-router'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorState } from '@/components/common/States'
import { EvalEmpty } from '@/components/evaluations/EvalEmpty'
import { Pill } from '@/components/common/StatusBadge'
import { Skeleton } from '@/components/ui/skeleton'
import { useEvaluations } from '@/hooks/queries/evaluations'
import { formatDateTime } from '@/lib/format'
import { formatMetric, metricLabel } from '@/lib/metrics'

const HEADLINE = ['numerical_accuracy', 'answer_accuracy', 'unsupported_claim_rate_final', 'latency_p50_ms']

export default function Evaluations() {
  const runs = useEvaluations()
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
      {(runs.data?.length ?? 0) > 0 && (
        <ul className="bg-card divide-y rounded-lg border">
          {runs.data?.map((run) => (
            <li key={run.id}>
              <Link
                to={`/evaluations/${run.id}`}
                className="hover:bg-muted/40 focus-visible:ring-ring/60 flex flex-col gap-2 px-4 py-3 outline-none focus-visible:ring-2 sm:flex-row sm:items-center"
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
          ))}
        </ul>
      )}
    </div>
  )
}
