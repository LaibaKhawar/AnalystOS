/**
 * Status indicator (Watermelon UI `status-indicator`), customized: theme tokens instead of
 * raw green/red, the ping animation only for genuinely live states and only when motion is allowed.
 * Used exclusively for real live status (LLM reachability, sandbox, connections, running analyses).
 */
import { cn } from '@/lib/utils'

export type IndicatorState = 'active' | 'down' | 'fixing' | 'idle'

interface StatusIndicatorProps {
  state: IndicatorState
  label?: string
  className?: string
  labelClassName?: string
  pulse?: boolean
}

const DOT: Record<IndicatorState, string> = {
  active: 'bg-success',
  down: 'bg-danger',
  fixing: 'bg-warning',
  idle: 'bg-muted-foreground/60',
}

export function StatusIndicator({
  state = 'idle',
  label,
  className,
  labelClassName,
  pulse = false,
}: StatusIndicatorProps) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className="relative flex size-2 items-center justify-center" aria-hidden="true">
        {pulse && (
          <span
            className={cn('absolute inline-flex size-2 rounded-full opacity-60 motion-safe:animate-ping', DOT[state])}
          />
        )}
        <span className={cn('relative inline-flex size-2 rounded-full', DOT[state])} />
      </span>
      {label && <span className={cn('text-foreground text-sm', labelClassName)}>{label}</span>}
    </span>
  )
}
