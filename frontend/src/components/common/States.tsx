import { ArrowClockwiseIcon, HourglassIcon, LockKeyIcon, WarningCircleIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { errorMessage, isForbidden, isRateLimited } from '@/api/client'
import { cn } from '@/lib/utils'

/** Title and icon for errors that need a specific explanation: missing permission and rate limits. */
function errorKind(error: unknown): { title: string; icon: ReactNode } | null {
  if (isForbidden(error))
    return { title: 'You do not have permission', icon: <LockKeyIcon className="text-danger mt-0.5 size-4 shrink-0" /> }
  if (isRateLimited(error))
    return { title: 'Slow down', icon: <HourglassIcon className="text-warning mt-0.5 size-4 shrink-0" /> }
  return null
}

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
  const kind = errorKind(error)
  const limited = isRateLimited(error)
  return (
    <div
      role="alert"
      data-error-code={kind ? (limited ? 'rate_limited' : 'forbidden') : undefined}
      className={cn(
        'flex items-start gap-3 rounded-lg border text-sm',
        limited ? 'border-warning/30 bg-warning-soft' : 'border-danger/30 bg-danger-soft',
        compact ? 'p-3' : 'p-4',
        className,
      )}
    >
      {kind?.icon ?? <WarningCircleIcon className="text-danger mt-0.5 size-4 shrink-0" weight="fill" />}
      <div className="min-w-0 flex-1">
        <p className="text-foreground font-medium">{kind?.title ?? title}</p>
        <p className="text-muted-foreground mt-0.5 break-words">{errorMessage(error)}</p>
      </div>
      {onRetry && !isForbidden(error) && (
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
