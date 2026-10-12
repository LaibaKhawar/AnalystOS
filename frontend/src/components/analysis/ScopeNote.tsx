import { FunnelIcon, WarningIcon } from '@phosphor-icons/react'
import type { Answer } from '@/api/types'
import { noDashes } from '@/lib/format'
import { scopeSummary } from '@/lib/scope'

const places = (n: number) => `${n} ${n === 1 ? 'place' : 'places'}`

/**
 * Result of the scope check: a quiet note when the plan narrowed the question and was corrected before running,
 * and a visible caveat when restrictions the question did not ask for are still in the answer.
 */
export function ScopeNote({ answer }: { answer: Answer | undefined }) {
  const scope = scopeSummary(answer)
  if (!scope) return null

  if (scope.remaining.length === 0) {
    return (
      <p
        className="text-muted-foreground flex items-start gap-1.5 text-xs"
        data-testid="scope-note"
        data-state="fixed"
        role="note"
      >
        <FunnelIcon className="text-brand mt-0.5 size-3.5 shrink-0" />
        <span>
          Scope corrected: the first plan narrowed your question in {places(scope.fixed || scope.found)} (a filter or
          period you did not ask for). It was fixed before running, so this answer covers the whole question.
        </span>
      </p>
    )
  }

  return (
    <div
      className="border-warning/30 bg-warning-soft rounded-lg border px-3 py-2.5 text-sm"
      data-testid="scope-note"
      data-state="remaining"
      role="note"
    >
      <p className="text-foreground flex items-center gap-1.5 font-medium">
        <WarningIcon className="text-warning size-4 shrink-0" weight="fill" />
        This answer is narrower than your question
      </p>
      <p className="text-muted-foreground mt-0.5 text-xs">
        {scope.fixed > 0
          ? `The plan added restrictions in ${places(scope.found)}; ${scope.fixed} ${scope.fixed === 1 ? 'was' : 'were'} corrected, but these remain:`
          : 'The plan kept restrictions you did not ask for. Read the numbers with these in mind:'}
      </p>
      <ul className="text-foreground/90 mt-1.5 list-disc pl-5 text-sm">
        {scope.remaining.map((detail, i) => (
          <li key={i}>{noDashes(detail)}</li>
        ))}
      </ul>
    </div>
  )
}
