/**
 * Step indicator (Watermelon UI `step-indicator-base`), customized for analysis plans:
 * one segment per plan step colored by its real status, a tooltip that slides between segments
 * (the original clip-path morph, simplified), keyboard focusable, Phosphor icons, theme tokens.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export type StepSegmentStatus = 'done' | 'running' | 'pending' | 'failed' | 'skipped'

export interface StepSegment {
  id: string
  label: string
  status: StepSegmentStatus
}

const SEGMENT: Record<StepSegmentStatus, string> = {
  done: 'bg-brand',
  running: 'bg-brand/50 motion-safe:animate-pulse',
  pending: 'bg-muted-foreground/20',
  failed: 'bg-danger',
  skipped: 'bg-muted-foreground/35',
}

const STATUS_WORD: Record<StepSegmentStatus, string> = {
  done: 'Done',
  running: 'Running',
  pending: 'Pending',
  failed: 'Failed',
  skipped: 'Skipped',
}

export function StepIndicator({ steps, className }: { steps: StepSegment[]; className?: string }) {
  const [active, setActive] = useState<number | null>(null)
  const [offset, setOffset] = useState(0)
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const container = useRef<HTMLDivElement | null>(null)
  const reduce = useReducedMotion()

  const show = (index: number) => {
    const el = refs.current[index]
    if (el) setOffset(el.offsetLeft + el.offsetWidth / 2)
    setActive(index)
  }

  if (steps.length === 0) return null
  const current = active === null ? null : steps[active]

  return (
    <div ref={container} className={cn('relative pt-1', className)} onMouseLeave={() => setActive(null)}>
      <AnimatePresence>
        {current && (
          <motion.div
            key="tip"
            role="tooltip"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={reduce ? { duration: 0 } : { type: 'spring', bounce: 0, duration: 0.3 }}
            className="pointer-events-none absolute bottom-full z-20 mb-2 -translate-x-1/2 transition-[left] duration-200"
            style={{ left: offset }}
          >
            <div className="bg-foreground text-background max-w-64 truncate rounded-md px-2.5 py-1.5 text-xs font-medium shadow-md">
              {active !== null && `${active + 1}. `}
              {current.label}
              <span className="ml-1.5 opacity-70">{STATUS_WORD[current.status]}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-center gap-1" aria-label="Plan progress">
        {steps.map((step, index) => (
          <button
            key={step.id}
            ref={(el) => {
              refs.current[index] = el
            }}
            type="button"
            aria-label={`Step ${index + 1}: ${step.label}, ${STATUS_WORD[step.status]}`}
            onMouseEnter={() => show(index)}
            onFocus={() => show(index)}
            onBlur={() => setActive(null)}
            className="group relative h-3 flex-1 cursor-default outline-none"
          >
            <span
              className={cn(
                'absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-xs transition-colors',
                'group-focus-visible:ring-ring/60 group-focus-visible:ring-offset-background group-focus-visible:ring-2 group-focus-visible:ring-offset-2',
                SEGMENT[step.status],
              )}
            />
          </button>
        ))}
      </div>
    </div>
  )
}
