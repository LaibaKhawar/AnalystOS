import { StopIcon } from '@phosphor-icons/react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { Analysis } from '@/api/types'
import { Button } from '@/components/ui/button'
import { LabeledProgressIndicator } from '@/components/watermelon/labeled-progress-indicator'
import { StepIndicator } from '@/components/watermelon/step-indicator'
import { useCancelAnalysis } from '@/hooks/queries/analyses'
import type { AnalysisStream } from '@/hooks/useAnalysisStream'
import { ActivityFeed } from './ActivityFeed'
import { currentPhase } from './events'
import { liveStepStatuses, planProgress, planRows, planSegments } from './plan'

export function RunningView({ analysis, stream }: { analysis: Analysis; stream: AnalysisStream }) {
  const cancel = useCancelAnalysis()
  const rows = planRows(analysis, liveStepStatuses(stream.events))
  const progress = planProgress(rows)
  const done = rows.filter((r) => r.status === 'done').length
  const label =
    analysis.status === 'queued' && stream.events.length === 0
      ? 'Waiting for a worker to pick this up'
      : currentPhase(stream.events, 'Starting the analysis')

  const onCancel = () =>
    cancel.mutate(analysis.id, {
      onSuccess: () => toast('Cancellation requested. The current step will finish first.'),
      onError: (error) => toast.error(errorMessage(error)),
    })

  return (
    <div className="flex flex-col gap-4" data-testid="analysis-running">
      <LabeledProgressIndicator
        label={label}
        progress={rows.length ? progress : null}
        detail={rows.length ? `${done} of ${rows.length} steps` : undefined}
      />
      {rows.length > 0 && <StepIndicator steps={planSegments(rows)} />}
      <ActivityFeed events={stream.events} className="max-h-64 overflow-y-auto pr-1" />
      <div className="flex items-center justify-between gap-3">
        <p className="text-muted-foreground text-xs">
          {stream.mode === 'polling'
            ? 'Live stream unavailable, checking for updates every 2 seconds.'
            : 'Streaming progress live.'}
        </p>
        <Button variant="outline" size="sm" onClick={onCancel} disabled={cancel.isPending}>
          <StopIcon data-icon="inline-start" weight="fill" />
          {cancel.isPending ? 'Cancelling' : 'Cancel'}
        </Button>
      </div>
    </div>
  )
}
