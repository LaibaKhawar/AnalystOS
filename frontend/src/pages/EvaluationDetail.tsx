import { ArrowLeftIcon } from '@phosphor-icons/react'
import { Link, useParams } from 'react-router'
import { PageHeader } from '@/components/common/PageHeader'
import { StatTile } from '@/components/common/Stat'
import { ErrorState } from '@/components/common/States'
import { Pill } from '@/components/common/StatusBadge'
import { CasesTable } from '@/components/evaluations/CasesTable'
import { LatencyChart, PassRateChart } from '@/components/evaluations/EvalCharts'
import { Skeleton } from '@/components/ui/skeleton'
import { useEvaluation } from '@/hooks/queries/evaluations'
import { formatDateTime, noDashes } from '@/lib/format'
import { categoryRates, formatMetric, latencyBins, metricLabel, scalarMetrics } from '@/lib/metrics'

export default function EvaluationDetail() {
  const { runId = '' } = useParams()
  const run = useEvaluation(runId)
  if (run.isError)
    return (
      <ErrorState error={run.error} title="Could not load this evaluation run" onRetry={() => void run.refetch()} />
    )
  if (run.isPending)
    return (
      <div className="flex flex-col gap-6" aria-busy="true">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    )
  const r = run.data
  const metrics = scalarMetrics(r.metrics)
  const rates = categoryRates(r.cases, r.metrics.by_category)
  const latency = latencyBins(r.cases)
  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/evaluations"
        className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1.5 text-xs"
      >
        <ArrowLeftIcon className="size-3.5" /> All runs
      </Link>
      <PageHeader
        title={`${r.suite} evaluation`}
        description={`${r.model ?? 'unknown model'}, started ${formatDateTime(r.created_at)}${r.completed_at ? `, finished ${formatDateTime(r.completed_at)}` : ''}`}
        actions={
          <Pill tone={r.status === 'completed' ? 'success' : r.status === 'failed' ? 'danger' : 'neutral'}>
            {r.status}
          </Pill>
        }
      >
        {r.notes && <p className="text-muted-foreground mt-2 text-sm">{noDashes(r.notes)}</p>}
      </PageHeader>
      {metrics.length > 0 && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" data-testid="eval-metrics">
          {metrics.map(([k, v]) => (
            <StatTile key={k} label={metricLabel(k)} value={formatMetric(k, v)} />
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="bg-card rounded-lg border p-4">
          <h2 className="text-foreground text-sm font-medium">Pass rate by category</h2>
          {rates.length ? (
            <PassRateChart data={rates} />
          ) : (
            <p className="text-muted-foreground mt-3 text-sm">No category data in this run.</p>
          )}
        </section>
        <section className="bg-card rounded-lg border p-4">
          <h2 className="text-foreground text-sm font-medium">Latency distribution</h2>
          {latency.length ? (
            <LatencyChart data={latency} />
          ) : (
            <p className="text-muted-foreground mt-3 text-sm">No latency recorded for these cases.</p>
          )}
        </section>
      </div>
      <section className="flex flex-col gap-3">
        <h2 className="text-foreground text-sm font-medium">Cases</h2>
        {r.cases.length ? (
          <CasesTable cases={r.cases} />
        ) : (
          <p className="text-muted-foreground text-sm">This run has no recorded cases.</p>
        )}
      </section>
    </div>
  )
}
