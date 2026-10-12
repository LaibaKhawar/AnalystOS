import type { AnalysisEvent } from '@/api/types'
import { noDashes } from '@/lib/format'

export type EventTone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger'

/** Safe, structured description of a progress event. Never includes model reasoning. */
export function describeEvent(event: AnalysisEvent): { text: string; tone: EventTone } {
  const msg = noDashes(event.message)
  switch (event.type) {
    case 'status':
      return { text: msg, tone: 'neutral' }
    case 'plan':
      return { text: msg.replace(/^Plan with/, 'Plan ready:'), tone: 'brand' }
    case 'replan':
      return { text: msg, tone: 'warning' }
    case 'step_started':
      return { text: `Started: ${msg}`, tone: 'neutral' }
    case 'step_completed':
      return { text: `Completed: ${msg}`, tone: 'success' }
    case 'step_failed':
      return { text: `Failed: ${msg}`, tone: 'danger' }
    case 'step_skipped':
      return { text: msg, tone: 'neutral' }
    case 'retry':
      return { text: msg, tone: 'warning' }
    case 'scope_check':
      return { text: `Scope check: ${msg}`, tone: 'warning' }
    case 'verification':
      return { text: msg, tone: 'success' }
    case 'clarification':
      return { text: 'Needs clarification before running', tone: 'warning' }
    case 'completed':
      return { text: 'Analysis complete', tone: 'success' }
    case 'failed':
      return { text: `Analysis failed: ${msg}`, tone: 'danger' }
    case 'cancelled':
      return { text: 'Analysis cancelled', tone: 'neutral' }
    default:
      return { text: msg, tone: 'neutral' }
  }
}

/** The headline label for the progress indicator: the latest status-like event. */
export function currentPhase(events: AnalysisEvent[], fallback: string): string {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i]
    if (e.type === 'status') return noDashes(e.message)
    if (e.type === 'step_started') return `Running: ${noDashes(e.message)}`
    if (e.type === 'retry') return noDashes(e.message)
    if (e.type === 'scope_check') return 'Correcting the scope of the plan'
    if (e.type === 'plan') return 'Executing the plan'
  }
  return fallback
}
