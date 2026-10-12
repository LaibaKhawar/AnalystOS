import { ArrowClockwiseIcon, WarningCircleIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/api/client'
import { cn } from '@/lib/utils'

/** Inline, contextual error with a retry action. Always shows the backend's error.message. */
export function ErrorState({
  error,
  title = 'Could not load this',
  onRetry,
  className,
  compact = false,
}: {
  error: unknown
  title?: string
  onRetry?: () => void
  className?: string
  compact?: boolean
}) {
  return (
    <div
      role="alert"
      className={cn(
        'border-danger/30 bg-danger-soft flex items-start gap-3 rounded-lg border text-sm',
        compact ? 'p-3' : 'p-4',
        className,
      )}
    >
      <WarningCircleIcon className="text-danger mt-0.5 size-4 shrink-0" weight="fill" />
      <div className="min-w-0 flex-1">
        <p className="text-foreground font-medium">{title}</p>
        <p className="text-muted-foreground mt-0.5 break-words">{errorMessage(error)}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0">
          <ArrowClockwiseIcon data-icon="inline-start" />
          Retry
        </Button>
      )}
    </div>
  )
}

/** Composed empty state: says what is missing and how to populate it. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: string
  description: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-start gap-3 rounded-lg border border-dashed p-6 sm:p-8', className)}>
      {icon && (
        <span className="bg-muted/50 text-muted-foreground flex size-9 items-center justify-center rounded-lg border">
          {icon}
        </span>
      )}
      <div>
        <p className="text-foreground text-sm font-medium">{title}</p>
        <div className="text-muted-foreground mt-1 max-w-md text-sm">{description}</div>
      </div>
      {action}
    </div>
  )
}
