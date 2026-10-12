/**
 * Labeled progress indicator (Watermelon UI `labeled-progress-indicator-base`), customized:
 * the label is driven by real analysis progress events instead of a timer, the bar width is the
 * real share of completed plan steps, accent token, 8px radius, no blur/3D, reduced-motion aware.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'

export interface LabeledProgressIndicatorProps {
  label: string
  /** 0..1, or null for indeterminate. */
  progress: number | null
  detail?: string
  className?: string
}

export function LabeledProgressIndicator({ label, progress, detail, className }: LabeledProgressIndicatorProps) {
  const reduce = useReducedMotion()
  const pct = progress === null ? null : Math.max(0.04, Math.min(1, progress)) * 100
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <div className="relative min-h-5 flex-1 overflow-hidden" aria-live="polite">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={label}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
              transition={{ type: 'spring', stiffness: 500, damping: 40 }}
              className="text-foreground block truncate text-sm font-medium"
            >
              {label}
            </motion.span>
          </AnimatePresence>
        </div>
        {detail && <span className="tabular text-muted-foreground shrink-0 text-xs">{detail}</span>}
      </div>
      <div
        className="bg-muted h-1.5 w-full overflow-hidden rounded-xs"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct === null ? undefined : Math.round(pct)}
      >
        {pct === null ? (
          <motion.div
            className="bg-brand h-full w-1/3 rounded-xs"
            animate={reduce ? undefined : { x: ['-100%', '300%'] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
          />
        ) : (
          <motion.div
            className="bg-brand h-full rounded-xs"
            initial={false}
            animate={{ width: `${pct}%` }}
            transition={{ duration: reduce ? 0 : 0.6, ease: 'easeOut' }}
          />
        )}
      </div>
    </div>
  )
}
