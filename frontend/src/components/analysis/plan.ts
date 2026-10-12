import type { Analysis, StepStatus } from '@/api/types'
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

/** Merge plan.steps (what was planned) with analysis.steps (what ran) by position. */
export function planRows(analysis: Analysis): PlanRow[] {
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
      status: r?.status ?? 'pending',
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
