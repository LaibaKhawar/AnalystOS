import { ArrowRightIcon, FileTextIcon, WarningIcon } from '@phosphor-icons/react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { Analysis, Claim } from '@/api/types'
import { ChartCard } from '@/components/charts/ChartCard'
import { ErrorState } from '@/components/common/States'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useCharts, useClaims, useCreateReport } from '@/hooks/queries/analyses'
import { useReports } from '@/hooks/queries/reports'
import { noDashes } from '@/lib/format'
import { ClaimGroups } from './ClaimList'
import { CostLine } from './CostLine'

function ListBlock({
  title,
  items,
  tone = 'neutral',
}: {
  title: string
  items: string[]
  tone?: 'neutral' | 'warning'
}) {
  if (items.length === 0) return null
  return (
    <section>
      <h4 className="text-muted-foreground mb-1.5 flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
        {tone === 'warning' && <WarningIcon className="text-warning size-3.5" weight="fill" />}
        {title}
      </h4>
      <ul className="text-foreground/90 flex list-disc flex-col gap-1 pl-5 text-sm">
        {items.map((item, i) => (
          <li key={i}>{noDashes(item)}</li>
        ))}
      </ul>
    </section>
  )
}

function ClaimsSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading statements">
      <Skeleton className="h-3 w-16" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex gap-3 px-2.5">
          <Skeleton className="size-4 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-16" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function AnswerView({
  analysis,
  onOpenClaim,
  onFollowUp,
  disabledFollowUps,
}: {
  analysis: Analysis
  onOpenClaim: (claim: Claim) => void
  onFollowUp: (question: string) => void
  disabledFollowUps: boolean
}) {
  const navigate = useNavigate()
  const charts = useCharts(analysis.id, analysis.status)
  const claims = useClaims(analysis.id, analysis.status)
  const reports = useReports()
  const createReport = useCreateReport()
  const answer = analysis.answer ?? {}
  const existingReport = reports.data?.find((r) => r.analysis_id === analysis.id)
  const v = answer.verification

  const generate = () =>
    createReport.mutate(analysis.id, {
      onSuccess: (report) => navigate(`/reports/${report.id}`),
      onError: (error) => toast.error(errorMessage(error)),
    })

  return (
    <div className="flex flex-col gap-5" data-testid="analysis-answer">
      <div>
        <p
          className="text-foreground text-lg leading-snug font-semibold tracking-[-0.01em]"
          data-testid="answer-headline"
        >
          {noDashes(answer.headline ?? analysis.summary ?? 'Analysis complete')}
        </p>
        {v && (
          <p className="text-muted-foreground mt-1.5 text-xs">
            {v.verified ?? 0} statements verified against query results
            {(v.removed ?? 0) > 0 ? `, ${v.removed} unsupported removed` : ''}
            {(v.repaired ?? 0) > 0 ? `, ${v.repaired} rewritten and re-verified` : ''}. Select any statement to see its
            evidence.
          </p>
        )}
      </div>

      {charts.isPending && <Skeleton className="h-80 w-full" />}
      {charts.isError && (
        <ErrorState compact error={charts.error} title="Charts did not load" onRetry={() => void charts.refetch()} />
      )}
      {charts.data && charts.data.length > 0 && (
        <div className="grid grid-cols-1 gap-3">
          {charts.data.map((chart) => (
            <ChartCard key={chart.id} chart={chart} />
          ))}
        </div>
      )}

      {claims.isPending && <ClaimsSkeleton />}
      {claims.isError && (
        <ErrorState
          compact
          error={claims.error}
          title="Statements did not load"
          onRetry={() => void claims.refetch()}
        />
      )}
      {claims.data && <ClaimGroups claims={claims.data} onOpen={onOpenClaim} className="-mx-2.5" />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ListBlock title="Caveats" items={answer.caveats ?? []} tone="warning" />
        <ListBlock title="Assumptions" items={answer.assumptions ?? []} />
      </div>
      <ListBlock title="Steps that failed" items={answer.failed_steps ?? []} tone="warning" />

      {(answer.follow_up_questions?.length ?? 0) > 0 && (
        <section>
          <h4 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">Ask next</h4>
          <div className="flex flex-wrap gap-2">
            {answer.follow_up_questions?.map((q) => (
              <button
                key={q}
                type="button"
                disabled={disabledFollowUps}
                onClick={() => onFollowUp(q)}
                className="bg-background text-foreground hover:border-brand/50 hover:bg-brand-soft focus-visible:ring-ring/60 inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors outline-none focus-visible:ring-2 active:scale-[0.98] disabled:opacity-50"
              >
                <span className="min-w-0">{noDashes(q)}</span>
                <ArrowRightIcon className="text-muted-foreground size-3 shrink-0" />
              </button>
            ))}
          </div>
        </section>
      )}

      <footer className="flex flex-col gap-3 border-t pt-3 sm:flex-row sm:items-center sm:justify-between">
        <CostLine analysis={analysis} />
        {existingReport ? (
          <Button variant="outline" size="sm" onClick={() => navigate(`/reports/${existingReport.id}`)}>
            <FileTextIcon data-icon="inline-start" />
            Open report
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={generate} disabled={createReport.isPending}>
            <FileTextIcon data-icon="inline-start" />
            {createReport.isPending ? 'Generating report' : 'Generate report'}
          </Button>
        )}
      </footer>
    </div>
  )
}
