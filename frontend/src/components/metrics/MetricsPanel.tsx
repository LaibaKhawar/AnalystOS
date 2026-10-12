import { FunctionIcon, PencilSimpleIcon, PlusIcon, TrashIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { MetricDefinition, Table } from '@/api/types'
import { EmptyState, ErrorState } from '@/components/common/States'
import { Pill } from '@/components/common/StatusBadge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useDeleteMetric, useMetrics } from '@/hooks/queries/metrics'
import { FILTER_OPS, METRIC_FORMATS } from '@/lib/metric-form'
import { MetricForm } from './MetricForm'

function filterText(f: MetricDefinition['filters'][number]): string {
  const op = FILTER_OPS.find((o) => o.value === f.op)?.label ?? f.op
  const value = Array.isArray(f.value) ? f.value.join(', ') : f.value === null ? '' : String(f.value)
  return `${f.column} ${op}${value ? ` ${value}` : ''}`
}

function DeleteMetric({ sourceId, metric }: { sourceId: string; metric: MetricDefinition }) {
  const remove = useDeleteMetric(sourceId)
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete metric ${metric.name}`}>
          <TrashIcon />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {metric.label}?</AlertDialogTitle>
          <AlertDialogDescription>
            The analyst stops using this definition for new questions. Past analyses keep the numbers they computed.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction
            className="bg-danger hover:bg-danger/90 text-white"
            onClick={() =>
              remove.mutate(metric.id, {
                onSuccess: () => toast(`${metric.label} deleted`),
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function MetricCard({
  sourceId,
  metric,
  canManage,
  onEdit,
}: {
  sourceId: string
  metric: MetricDefinition
  canManage: boolean
  onEdit: () => void
}) {
  const format = METRIC_FORMATS.find((f) => f.value === metric.format)?.label ?? metric.format
  return (
    <li className="flex flex-col gap-2 px-4 py-3" data-testid="metric-row">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-foreground text-sm font-medium">{metric.label}</p>
          <p className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className="text-foreground/80 font-mono">{metric.name}</span>
            <span>on</span>
            <span className="font-mono">{metric.table_name}</span>
            <Pill>{format}</Pill>
          </p>
        </div>
        {canManage && (
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="ghost" size="icon-sm" aria-label={`Edit metric ${metric.name}`} onClick={onEdit}>
              <PencilSimpleIcon />
            </Button>
            <DeleteMetric sourceId={sourceId} metric={metric} />
          </div>
        )}
      </div>
      <code className="bg-muted/50 text-foreground block rounded-md border px-2.5 py-1.5 font-mono text-xs break-all">
        {metric.expression}
      </code>
      {metric.filters.length > 0 && (
        <p className="text-muted-foreground text-xs">
          Where <span className="text-foreground/80 font-mono">{metric.filters.map(filterText).join(' and ')}</span>
        </p>
      )}
      {metric.description && <p className="text-muted-foreground text-sm">{metric.description}</p>}
    </li>
  )
}

/**
 * Saved metric definitions for a source. The analyst uses these exact expressions whenever a question
 * mentions the metric, so "revenue per order" means the same thing in every answer.
 */
export function MetricsPanel({
  sourceId,
  tables,
  canManage,
}: {
  sourceId: string
  tables: Table[]
  canManage: boolean
}) {
  const metrics = useMetrics(sourceId)
  const [editing, setEditing] = useState<MetricDefinition | 'new' | null>(null)
  const open = editing !== null
  const current = editing === 'new' ? null : editing

  return (
    <section className="flex flex-col gap-4" aria-labelledby="metrics-title" data-testid="metrics-panel">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="metrics-title" className="text-foreground text-sm font-medium">
            Saved metrics
          </h2>
          <p className="text-muted-foreground mt-0.5 max-w-2xl text-sm">
            Define a business metric once. Whenever a question mentions it, the analyst computes it with exactly this
            expression and these filters instead of improvising one, so every answer agrees.
          </p>
        </div>
        {canManage && (
          <Button onClick={() => setEditing('new')} className="shrink-0" disabled={tables.length === 0}>
            <PlusIcon data-icon="inline-start" />
            New metric
          </Button>
        )}
      </div>

      {metrics.isPending && (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading metrics">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      )}
      {metrics.isError && <ErrorState error={metrics.error} onRetry={() => void metrics.refetch()} />}
      {metrics.data?.length === 0 && (
        <EmptyState
          icon={<FunctionIcon className="size-4" />}
          title="No saved metrics yet"
          description={
            canManage
              ? 'Create one for each number your team argues about, for example average order value as SUM(revenue) / COUNT(*).'
              : 'The owner of this source has not defined any metrics. The analyst derives metrics from the schema instead.'
          }
        />
      )}
      {(metrics.data?.length ?? 0) > 0 && (
        <ul className="bg-card divide-y rounded-lg border">
          {metrics.data?.map((m) => (
            <MetricCard key={m.id} sourceId={sourceId} metric={m} canManage={canManage} onEdit={() => setEditing(m)} />
          ))}
        </ul>
      )}

      <Dialog open={open} onOpenChange={(next) => !next && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl" data-testid="metric-dialog">
          <DialogHeader>
            <DialogTitle>{current ? `Edit ${current.label}` : 'New metric'}</DialogTitle>
            <DialogDescription>
              The expression must aggregate, for example SUM(revenue) / COUNT(*). It is checked against the table and
              the SQL validator before it is saved.
            </DialogDescription>
          </DialogHeader>
          {open && (
            <MetricForm
              key={current?.id ?? 'new'}
              sourceId={sourceId}
              tables={tables}
              metric={current}
              onCancel={() => setEditing(null)}
              onSaved={(m) => {
                toast.success(current ? `${m.label} updated` : `${m.label} saved`)
                setEditing(null)
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
