import { HourglassIcon, LockKeyIcon, WarningCircleIcon } from '@phosphor-icons/react'
import { errorMessage, isForbidden, isRateLimited } from '@/api/client'
import { cn } from '@/lib/utils'

/**
 * Inline form-level error. Pass `message` for client text, or `error` to show the server's message with a
 * clear title for missing permissions (403 forbidden) and rate limits (429, with the wait time).
 */
export function FormError({ message, error }: { message?: string | null; error?: unknown }) {
  const text = message ?? (error ? errorMessage(error) : null)
  if (!text) return null
  const forbidden = error !== undefined && isForbidden(error)
  const limited = error !== undefined && isRateLimited(error)
  const Icon = forbidden ? LockKeyIcon : limited ? HourglassIcon : WarningCircleIcon
  return (
    <div
      role="alert"
      className={cn(
        'text-foreground flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm',
        limited ? 'border-warning/30 bg-warning-soft' : 'border-danger/30 bg-danger-soft',
      )}
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', limited ? 'text-warning' : 'text-danger')} weight="fill" />
      <span>
        {forbidden && <span className="font-medium">You do not have permission. </span>}
        {text}
      </span>
    </div>
  )
}
