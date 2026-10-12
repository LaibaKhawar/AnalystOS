import type { Answer } from '@/api/types'

const SCOPE_PREFIX = /^scope:\s*/i

export interface ScopeSummary {
  /** Restrictions the first plan added that the question did not ask for. */
  found: number
  /** How many of those were removed before running. */
  fixed: number
  /** Restrictions still in the plan that ran: a caveat on the answer. */
  remaining: string[]
}

/**
 * Summarize the scope check. Prefers answer.scope; older answers only carry "Scope: ..." assumptions.
 * Returns null when nothing was narrowed.
 */
export function scopeSummary(answer: Answer | undefined): ScopeSummary | null {
  if (!answer) return null
  const fromAssumptions = (answer.assumptions ?? [])
    .filter((a) => SCOPE_PREFIX.test(a))
    .map((a) => a.replace(SCOPE_PREFIX, ''))
  const scope = answer.scope
  const remaining = scope?.remaining?.length ? scope.remaining.map((r) => r.detail) : fromAssumptions
  const found = Math.max(scope?.issues_found ?? 0, remaining.length)
  const fixed = scope?.fixed ?? 0
  if (found === 0 && fixed === 0 && remaining.length === 0) return null
  return { found, fixed, remaining }
}

/** Assumptions without the "Scope: ..." entries, which the scope note shows instead. */
export function plainAssumptions(answer: Answer | undefined): string[] {
  return (answer?.assumptions ?? []).filter((a) => !SCOPE_PREFIX.test(a))
}
