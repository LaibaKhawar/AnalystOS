import {
  ArrowsClockwiseIcon,
  CheckCircleIcon,
  CircleIcon,
  FunnelIcon,
  ListChecksIcon,
  SealCheckIcon,
  WarningCircleIcon,
  XCircleIcon,
} from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { AnalysisEvent } from '@/api/types'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { describeEvent, type EventTone } from './events'

const TONE_TEXT: Record<EventTone, string> = {
  neutral: 'text-muted-foreground',
  brand: 'text-brand-text',
  success: 'text-brand-text',
  warning: 'text-warning',
  danger: 'text-danger',
}

function EventIcon({ event }: { event: AnalysisEvent }) {
  const cls = 'size-3.5'
  switch (event.type) {
    case 'plan':
      return <ListChecksIcon className={cls} />
    case 'step_completed':
    case 'completed':
      return <CheckCircleIcon className={cls} weight="fill" />
    case 'step_failed':
    case 'failed':
      return <XCircleIcon className={cls} weight="fill" />
    case 'retry':
    case 'replan':
      return <ArrowsClockwiseIcon className={cls} />
    case 'verification':
      return <SealCheckIcon className={cls} weight="fill" />
    case 'scope_check':
      return <FunnelIcon className={cls} />
    case 'clarification':
      return <WarningCircleIcon className={cls} />
    default:
      return <CircleIcon className={cn(cls, 'opacity-60')} weight="bold" />
  }
}

/** Live activity feed of structured progress events. */
export function ActivityFeed({ events, className }: { events: AnalysisEvent[]; className?: string }) {
  const reduce = useReducedMotion()
  if (events.length === 0) return null
  return (
    <ol className={cn('flex flex-col gap-1.5', className)} aria-label="Analysis activity" data-testid="activity-feed">
      <AnimatePresence initial={false}>
        {events.map((event) => {
          const { text, tone } = describeEvent(event)
          return (
            <motion.li
              key={event.id}
              initial={reduce ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className="grid grid-cols-[auto_1fr_auto] items-start gap-2 text-xs"
            >
              <span className={cn('mt-0.5', TONE_TEXT[tone])}>
                <EventIcon event={event} />
              </span>
              <span className="text-foreground/90 min-w-0 break-words">{text}</span>
              <time className="tabular text-muted-foreground" dateTime={event.created_at}>
                {formatTime(event.created_at)}
              </time>
            </motion.li>
          )
        })}
      </AnimatePresence>
    </ol>
  )
}
