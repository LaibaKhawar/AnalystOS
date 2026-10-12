import { cn } from '@/lib/utils'

export const UNCERTAIN_THRESHOLD = 0.6

/** Semantic-type confidence as a thin bar plus percent; marks "uncertain" below 0.6. */
export function ConfidenceBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  const uncertain = value < UNCERTAIN_THRESHOLD
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span
        className="bg-muted h-1 w-14 overflow-hidden rounded-xs"
        role="meter"
        aria-label="Confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
      >
        <span className={cn('block h-full', uncertain ? 'bg-warning' : 'bg-brand')} style={{ width: `${pct}%` }} />
      </span>
      <span className="tabular text-muted-foreground text-xs">{Math.round(pct)}%</span>
      {uncertain && <span className="text-warning text-[11px] font-medium">uncertain</span>}
    </span>
  )
}
