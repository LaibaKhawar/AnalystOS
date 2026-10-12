import type { Analysis, AnalysisEvent, StepStatus } from '@/api/types'
import type { StepSegment, StepSegmentStatus } from '@/components/watermelon/step-indicator'

export interface PlanRow {
  key: string
  ordinal: number
  title: string
  tool: string
  status: StepStatus
  replanned: boolean
  summary: string | null
  expected: string | null
  startedAt: string | null
  completedAt: string | null
}

const EVENT_STATUS: Record<string, StepStatus> = {
  step_started: 'running',
  retry: 'running',
  step_completed: 'done',
  step_failed: 'failed',
  step_skipped: 'skipped',
}

/**
 * Latest step status per step record, from live progress events. Events carry `step_record_id`, the id of
 * the matching analysis.steps entry, so a status is never applied to the wrong row when steps are added by
 * a replan or arrive out of order.
 */
export function liveStepStatuses(events: AnalysisEvent[]): Map<string, StepStatus> {
  const map = new Map<string, StepStatus>()
  for (const event of events) {
    const status = EVENT_STATUS[event.type]
    const id = event.payload.step_record_id
    if (status && typeof id === 'string' && id) map.set(id, status)
  }
  return map
}

/**
 * Merge plan.steps (what was planned) with analysis.steps (what ran) by position, then overlay live
 * statuses from progress events matched by step record id.
 */
export function planRows(analysis: Analysis, live?: Map<string, StepStatus>): PlanRow[] {
  const planned = analysis.plan?.steps ?? []
  const ran = [...(analysis.steps ?? [])].sort((a, b) => a.ordinal - b.ordinal)
  const count = Math.max(planned.length, ran.length)
  const rows: PlanRow[] = []
  for (let i = 0; i < count; i += 1) {
    const p = planned[i]
    const r = ran.find((s) => s.ordinal === i) ?? ran[i]
    rows.push({
      key: r?.id ?? p?.id ?? String(i),
      ordinal: i,
      title: r?.title ?? p?.title ?? `Step ${i + 1}`,
      tool: r?.tool ?? p?.tool ?? '',
      status: (r && live?.get(r.id)) ?? r?.status ?? 'pending',
      replanned: r?.added_by_replan ?? false,
      summary: r?.result_summary ?? null,
      expected: p?.expected_output || r?.purpose || null,
      startedAt: r?.started_at ?? null,
      completedAt: r?.completed_at ?? null,
    })
  }
  return rows
}

const SEG: Record<string, StepSegmentStatus> = {
  done: 'done',
  running: 'running',
  pending: 'pending',
  failed: 'failed',
  skipped: 'skipped',
}

export function planSegments(rows: PlanRow[]): StepSegment[] {
  return rows.map((r) => ({ id: r.key, label: r.title, status: SEG[r.status] ?? 'pending' }))
}

export function planProgress(rows: PlanRow[]): number | null {
  if (rows.length === 0) return null
  const finished = rows.filter((r) => ['done', 'failed', 'skipped'].includes(r.status)).length
  return finished / rows.length
}
