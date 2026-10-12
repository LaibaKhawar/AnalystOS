import { ArrowUpIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

export function AskBox({
  value,
  onChange,
  onSubmit,
  disabled,
  disabledReason,
  sourceName,
  focusKey,
}: {
  value: string
  onChange: (v: string) => void
  onSubmit: (question: string) => Promise<void>
  disabled: boolean
  disabledReason?: string
  sourceName?: string
  focusKey?: number
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (focusKey) ref.current?.focus()
  }, [focusKey])

  const submit = async (event?: FormEvent) => {
    event?.preventDefault()
    const q = value.trim()
    if (q.length < 3) {
      setError('Ask a full question, for example "Which region grew fastest last quarter?"')
      return
    }
    setPending(true)
    setError(null)
    try {
      await onSubmit(q)
      onChange('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the analysis.')
    } finally {
      setPending(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!disabled && !pending) void submit()
    }
  }

  const blocked = disabled || pending
  return (
    <form onSubmit={submit} className="flex flex-col gap-1.5">
      <label htmlFor="ask-input" className="text-muted-foreground text-xs font-medium">
        Ask about {sourceName ?? 'this data source'}
      </label>
      <div className="bg-card focus-within:ring-ring/40 flex items-end gap-2 rounded-lg border p-2 focus-within:ring-2">
        <Textarea
          id="ask-input"
          ref={ref}
          rows={2}
          value={value}
          disabled={blocked}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'ask-error' : 'ask-hint'}
          className="max-h-40 min-h-10 resize-none border-0 bg-transparent px-1.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
          data-testid="ask-input"
        />
        <Button
          type="submit"
          size="icon"
          disabled={blocked || value.trim().length === 0}
          aria-label="Run analysis"
          data-testid="ask-submit"
        >
          <ArrowUpIcon weight="bold" />
        </Button>
      </div>
      {error ? (
        <p id="ask-error" className="text-danger text-xs" role="alert">
          {error}
        </p>
      ) : (
        <p id="ask-hint" className="text-muted-foreground text-[11px]">
          {disabled && disabledReason
            ? disabledReason
            : 'Enter to run, Shift Enter for a new line. Answers cite the queries behind every number.'}
        </p>
      )}
    </form>
  )
}
