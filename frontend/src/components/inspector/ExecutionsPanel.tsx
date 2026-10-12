import { useState } from 'react'
import { ErrorState } from '@/components/common/States'
import { Pill } from '@/components/common/StatusBadge'
import { Skeleton } from '@/components/ui/skeleton'
import { useExecutions } from '@/hooks/queries/analyses'
import { formatDuration, noDashes } from '@/lib/format'
import { ExecutionDetailSheet } from './ExecutionDetail'

export function ExecutionsPanel({ analysisId, active }: { analysisId: string; active: boolean }) {
  const executions = useExecutions(analysisId, active)
  const [open, setOpen] = useState<string | null>(null)
  if (executions.isPending)
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
    )
  if (executions.isError)
    return <ErrorState compact error={executions.error} onRetry={() => void executions.refetch()} />
  return (
    <>
      {executions.data.length === 0 ? (
        <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
          Tool calls appear here as steps run.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5" aria-label="Execution history">
          {executions.data.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => setOpen(e.id)}
                className="bg-card hover:border-foreground/20 focus-visible:ring-ring/60 w-full rounded-lg border px-3 py-2.5 text-left outline-none focus-visible:ring-2 active:scale-[0.99]"
                data-testid="execution-row"
              >
                <span className="flex items-center justify-between gap-2">
                  <code className="text-foreground truncate font-mono text-xs">{e.tool}</code>
                  <Pill tone={e.status === 'success' ? 'success' : 'danger'}>{e.status}</Pill>
                </span>
                <span className="text-muted-foreground mt-1 flex flex-wrap gap-x-3 text-[11px]">
                  <span>attempt {e.attempt}</span>
                  <span className="tabular">{formatDuration(e.duration_ms)}</span>
                  {e.error_kind && <span className="text-danger">{e.error_kind.replace(/_/g, ' ')}</span>}
                </span>
                {e.retry_reason && (
                  <span className="text-warning mt-1 block truncate text-[11px]">
                    Retry: {noDashes(e.retry_reason)}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <ExecutionDetailSheet analysisId={analysisId} executionId={open} onClose={() => setOpen(null)} />
    </>
  )
}
