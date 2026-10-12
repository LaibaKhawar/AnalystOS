import { ArrowClockwiseIcon, QuestionIcon, WarningCircleIcon } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { Analysis } from '@/api/types'
import { Field } from '@/components/forms/Field'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useRetryAnalysis } from '@/hooks/queries/analyses'
import { noDashes } from '@/lib/format'

export function ClarificationView({
  analysis,
  onAnswer,
  disabled,
}: {
  analysis: Analysis
  onAnswer: (text: string) => Promise<void>
  disabled: boolean
}) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const question =
    analysis.answer?.headline ?? analysis.plan?.clarification_question ?? 'Could you clarify the question?'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (text.trim().length < 3) {
      setError('Write at least a few words so the analyst can continue.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await onAnswer(text.trim())
      setText('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="analysis-clarification">
      <div className="border-warning/30 bg-warning-soft flex items-start gap-3 rounded-lg border p-4">
        <QuestionIcon className="text-warning mt-0.5 size-5 shrink-0" weight="bold" />
        <div>
          <p className="text-warning text-xs font-medium">The analyst needs one detail before running</p>
          <p className="text-foreground mt-1 text-base font-medium">{noDashes(question)}</p>
        </div>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <Field label="Your answer" error={error}>
          {(p) => (
            <Textarea
              {...p}
              rows={2}
              value={text}
              disabled={disabled || pending}
              onChange={(e) => setText(e.target.value)}
              className="resize-none"
            />
          )}
        </Field>
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={disabled || pending}>
            {pending ? 'Sending' : 'Answer and continue'}
          </Button>
        </div>
      </form>
    </div>
  )
}

export function FailedView({ analysis }: { analysis: Analysis }) {
  const retry = useRetryAnalysis()
  const cancelled = analysis.status === 'cancelled'
  return (
    <div className="flex flex-col gap-3" data-testid="analysis-failed">
      <div
        role={cancelled ? undefined : 'alert'}
        className={
          cancelled
            ? 'bg-muted/40 flex items-start gap-3 rounded-lg border p-4'
            : 'border-danger/30 bg-danger-soft flex items-start gap-3 rounded-lg border p-4'
        }
      >
        <WarningCircleIcon
          className={cancelled ? 'text-muted-foreground mt-0.5 size-5' : 'text-danger mt-0.5 size-5'}
          weight="fill"
        />
        <div className="min-w-0 flex-1">
          <p className="text-foreground text-sm font-medium">
            {cancelled ? 'This analysis was cancelled' : 'This analysis failed'}
          </p>
          <p className="text-muted-foreground mt-1 text-sm break-words">
            {noDashes(
              analysis.error ?? (cancelled ? 'Cancelled before it finished.' : 'No error details were recorded.'),
            )}
          </p>
        </div>
      </div>
      <div className="flex justify-end">
        <Button
          size="sm"
          variant={cancelled ? 'outline' : 'default'}
          disabled={retry.isPending}
          onClick={() =>
            retry.mutate(analysis.id, {
              onError: (error) => toast.error(errorMessage(error)),
            })
          }
        >
          <ArrowClockwiseIcon data-icon="inline-start" />
          {retry.isPending ? 'Retrying' : 'Retry'}
        </Button>
      </div>
    </div>
  )
}
