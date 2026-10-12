import type { Analysis, Claim } from '@/api/types'
import { AnalysisStatusBadge } from '@/components/common/StatusBadge'
import { useAnalysis, isActive } from '@/hooks/queries/analyses'
import { useAnalysisStream } from '@/hooks/useAnalysisStream'
import { formatRelative, noDashes } from '@/lib/format'
import { cn } from '@/lib/utils'
import { AnswerView } from './AnswerView'
import { ClarificationView, FailedView } from './OutcomeViews'
import { RunningView } from './RunningView'

export function AnalysisTurn({
  initial,
  selected,
  onSelect,
  onOpenClaim,
  onFollowUp,
  onClarify,
  conversationBusy,
}: {
  initial: Analysis
  selected: boolean
  onSelect: (id: string) => void
  onOpenClaim: (analysisId: string, claim: Claim) => void
  onFollowUp: (question: string) => void
  onClarify: (text: string) => Promise<void>
  conversationBusy: boolean
}) {
  const query = useAnalysis(initial.id, initial)
  const analysis = query.data ?? initial
  const stream = useAnalysisStream(analysis)
  const active = isActive(analysis.status)

  return (
    <article
      className="flex flex-col gap-3"
      aria-labelledby={`q-${analysis.id}`}
      data-testid="analysis-turn"
      data-status={analysis.status}
      data-analysis-id={analysis.id}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-muted-foreground text-[11px] font-medium">You asked</p>
          <h3 id={`q-${analysis.id}`} className="text-foreground mt-0.5 text-[15px] font-medium">
            {noDashes(analysis.question)}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <AnalysisStatusBadge status={analysis.status} />
          <time className="text-muted-foreground text-[11px]" dateTime={analysis.created_at}>
            {formatRelative(analysis.created_at)}
          </time>
        </div>
      </header>
      <div
        onClick={() => onSelect(analysis.id)}
        onFocusCapture={() => onSelect(analysis.id)}
        className={cn(
          'bg-card rounded-lg border p-4 transition-colors sm:p-5',
          selected ? 'border-brand/40 ring-brand/20 ring-1' : 'hover:border-foreground/15',
        )}
      >
        {active && <RunningView analysis={analysis} stream={stream} />}
        {analysis.status === 'completed' && (
          <AnswerView
            analysis={analysis}
            onOpenClaim={(claim) => onOpenClaim(analysis.id, claim)}
            onFollowUp={onFollowUp}
            disabledFollowUps={conversationBusy}
          />
        )}
        {analysis.status === 'needs_clarification' && (
          <ClarificationView analysis={analysis} onAnswer={onClarify} disabled={conversationBusy} />
        )}
        {(analysis.status === 'failed' || analysis.status === 'cancelled') && <FailedView analysis={analysis} />}
      </div>
    </article>
  )
}
