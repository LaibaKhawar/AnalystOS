import { ArrowRightIcon, CheckCircleIcon, CircleIcon, MinusCircleIcon, XCircleIcon } from '@phosphor-icons/react'
import type { Analysis } from '@/api/types'
import { Pill } from '@/components/common/StatusBadge'
import { planRows } from '@/components/analysis/plan'
import { formatDuration, noDashes } from '@/lib/format'
import { cn } from '@/lib/utils'

function StepIcon({ status }: { status: string }) {
  const cls = 'size-4 shrink-0'
  if (status === 'done') return <CheckCircleIcon className={cn(cls, 'text-brand')} weight="fill" aria-label="Done" />
  if (status === 'running')
    return (
      <ArrowRightIcon className={cn(cls, 'text-brand motion-safe:animate-pulse')} weight="bold" aria-label="Running" />
    )
  if (status === 'failed') return <XCircleIcon className={cn(cls, 'text-danger')} weight="fill" aria-label="Failed" />
  if (status === 'skipped') return <MinusCircleIcon className={cn(cls, 'text-muted-foreground')} aria-label="Skipped" />
  return <CircleIcon className={cn(cls, 'text-muted-foreground')} aria-label="Pending" />
}

function duration(start: string | null, end: string | null): string | null {
  if (!start || !end) return null
  return formatDuration(new Date(end).getTime() - new Date(start).getTime())
}

export function PlanPanel({ analysis }: { analysis: Analysis }) {
  const rows = planRows(analysis)
  const plan = analysis.plan ?? {}
  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
        {analysis.status === 'queued' || analysis.status === 'running'
          ? 'The plan appears here as soon as the analyst finishes planning.'
          : 'No plan was recorded for this analysis.'}
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      {plan.goal && (
        <div>
          <p className="text-muted-foreground text-[11px] font-medium uppercase">Goal</p>
          <p className="text-foreground mt-0.5 text-sm">{noDashes(plan.goal)}</p>
        </div>
      )}
      <ol className="flex flex-col gap-1" aria-label="Plan steps">
        {rows.map((row) => (
          <li key={row.key} className="hover:bg-muted/40 grid grid-cols-[auto_1fr] gap-2.5 rounded-lg px-2 py-2">
            <span className="mt-0.5">
              <StepIcon status={row.status} />
            </span>
            <div className="min-w-0">
              <p className="text-foreground text-sm">
                <span className="tabular text-muted-foreground mr-1.5">{row.ordinal + 1}.</span>
                {noDashes(row.title)}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <code className="bg-muted text-muted-foreground rounded-xs px-1.5 py-0.5 font-mono text-[10.5px]">
                  {row.tool}
                </code>
                {row.replanned && <Pill tone="warning">Added by replanning</Pill>}
                {duration(row.startedAt, row.completedAt) && (
                  <span className="tabular text-muted-foreground text-[11px]">
                    {duration(row.startedAt, row.completedAt)}
                  </span>
                )}
              </div>
              {row.summary && (row.status === 'failed' || row.status === 'skipped') && (
                <p className="text-muted-foreground mt-1 text-xs break-words">{noDashes(row.summary.slice(0, 300))}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
      {(plan.assumptions?.length ?? 0) > 0 && (
        <div>
          <p className="text-muted-foreground text-[11px] font-medium uppercase">Assumptions</p>
          <ul className="text-foreground/90 mt-1 list-disc pl-5 text-xs">
            {plan.assumptions?.map((a, i) => (
              <li key={i}>{noDashes(a)}</li>
            ))}
          </ul>
        </div>
      )}
      {analysis.replans > 0 && (
        <p className="text-muted-foreground text-xs">
          Plan revised {analysis.replans} time(s) after reviewing results.
        </p>
      )}
    </div>
  )
}
