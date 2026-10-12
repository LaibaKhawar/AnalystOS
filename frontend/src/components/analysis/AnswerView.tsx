import {
  ArrowRightIcon,
  CaretRightIcon,
  CheckCircleIcon,
  FileTextIcon,
  QuestionIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { Analysis, Claim } from '@/api/types'
import { ChartCard } from '@/components/charts/ChartCard'
import { ErrorState } from '@/components/common/States'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAnalysisReport, useCharts, useClaims, useCreateReport } from '@/hooks/queries/analyses'
import { claimBadge, headlineClaim } from '@/lib/claims'
import { noDashes } from '@/lib/format'
import { ClaimGroups } from './ClaimList'
import { CostLine } from './CostLine'
import { ScopeNote } from './ScopeNote'
import { plainAssumptions } from '@/lib/scope'

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

/** The answer headline. When the API stored it as a verified claim, it opens that claim's evidence. */
function Headline({ text, claim, onOpen }: { text: string; claim: Claim | undefined; onOpen: (claim: Claim) => void }) {
  const className = 'text-foreground text-lg leading-snug font-semibold tracking-[-0.01em]'
  if (!claim) {
    return (
      <p className={className} data-testid="answer-headline">
        {text}
      </p>
    )
  }
  const badge = claimBadge(claim.status)
  const Icon = claim.status === 'verified' ? CheckCircleIcon : QuestionIcon
  return (
    <button
      type="button"
      onClick={() => onOpen(claim)}
      data-testid="answer-headline"
      data-status={claim.status}
      aria-label={`${text}. ${badge.label}. Open evidence for the headline`}
      className="group hover:bg-muted/60 focus-visible:ring-ring/60 -mx-2 -my-1 flex w-[calc(100%+1rem)] items-start gap-2 rounded-lg px-2 py-1 text-left transition-colors outline-none focus-visible:ring-2 active:scale-[0.995]"
    >
      <span className={className}>{text}</span>
      <span className="mt-1.5 flex shrink-0 items-center gap-0.5">
        <Icon
          className={claim.status === 'verified' ? 'text-brand size-4' : 'text-warning size-4'}
          weight={claim.status === 'verified' ? 'fill' : 'bold'}
          aria-hidden="true"
        />
        <CaretRightIcon className="text-muted-foreground size-3.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
      </span>
    </button>
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
  const report = useAnalysisReport(analysis.id, analysis.status)
  const createReport = useCreateReport()
  const answer = analysis.answer ?? {}
  const existingReport = report.data ?? null
  const v = answer.verification
  const headline = noDashes(answer.headline ?? analysis.summary ?? 'Analysis complete')

  const generate = () =>
    createReport.mutate(analysis.id, {
      onSuccess: (report) => navigate(`/reports/${report.id}`),
      onError: (error) => toast.error(errorMessage(error)),
    })

  return (
    <div className="flex flex-col gap-5" data-testid="analysis-answer">
      <div>
        <Headline text={headline} claim={headlineClaim(claims.data)} onOpen={onOpenClaim} />
        {v && (
          <p className="text-muted-foreground mt-1.5 text-xs">
            {v.verified ?? 0} statements verified against query results
            {(v.removed ?? 0) > 0 ? `, ${v.removed} unsupported removed` : ''}
            {(v.repaired ?? 0) > 0 ? `, ${v.repaired} rewritten and re-verified` : ''}. Select the headline or any
            statement to see its evidence.
          </p>
        )}
      </div>

      <ScopeNote answer={answer} />

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
        <ListBlock title="Assumptions" items={plainAssumptions(answer)} />
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
        {report.isPending ? (
          <Skeleton className="h-7 w-32" />
        ) : existingReport ? (
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
