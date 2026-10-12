import { CaretRightIcon, CheckCircleIcon, InfoIcon, QuestionIcon } from '@phosphor-icons/react'
import type { Claim } from '@/api/types'
import { Pill } from '@/components/common/StatusBadge'
import { claimBadge, groupClaims, sectionLabel } from '@/lib/claims'
import { noDashes } from '@/lib/format'
import { cn } from '@/lib/utils'

function ClaimIcon({ status }: { status: string }) {
  if (status === 'verified') return <CheckCircleIcon className="text-brand size-4" weight="fill" aria-hidden="true" />
  if (status === 'qualified') return <QuestionIcon className="text-warning size-4" weight="bold" aria-hidden="true" />
  return <InfoIcon className="text-muted-foreground size-4" aria-hidden="true" />
}

export function ClaimRow({ claim, onOpen }: { claim: Claim; onOpen: (claim: Claim) => void }) {
  const badge = claimBadge(claim.status)
  const section = sectionLabel(claim.section)
  const evidenceCount = claim.evidence.length
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(claim)}
        data-testid="claim"
        data-status={claim.status}
        className="group hover:bg-muted/60 focus-visible:ring-ring/60 grid w-full grid-cols-[auto_1fr_auto] items-start gap-3 rounded-lg px-2.5 py-2 text-left transition-colors outline-none focus-visible:ring-2 active:scale-[0.995]"
        aria-label={`${noDashes(claim.text)}. ${badge.label}. Open evidence`}
      >
        <span className="mt-0.5">
          <ClaimIcon status={claim.status} />
        </span>
        <span className="min-w-0">
          <span className="text-foreground text-sm leading-relaxed">{noDashes(claim.text)}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            <Pill tone={badge.tone}>{badge.label}</Pill>
            {section && <span className="text-muted-foreground text-[11px]">{section}</span>}
            {evidenceCount > 0 && (
              <span className="text-muted-foreground text-[11px]">
                {evidenceCount} evidence {evidenceCount === 1 ? 'item' : 'items'}
              </span>
            )}
          </span>
        </span>
        <CaretRightIcon className="text-muted-foreground mt-1 size-3.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
      </button>
    </li>
  )
}

export function ClaimGroups({
  claims,
  onOpen,
  className,
}: {
  claims: Claim[]
  onOpen: (claim: Claim) => void
  className?: string
}) {
  const groups = groupClaims(claims)
  if (groups.length === 0) {
    return (
      <p className={cn('text-muted-foreground text-sm', className)}>
        No verified statements were kept for this answer.
      </p>
    )
  }
  return (
    <div className={cn('flex flex-col gap-5', className)}>
      {groups.map((group) => (
        <section key={group.key} aria-labelledby={`claims-${group.key}`}>
          <div className="mb-1 flex items-baseline justify-between gap-3 px-2.5">
            <h4
              id={`claims-${group.key}`}
              className="text-muted-foreground text-xs font-semibold tracking-wide uppercase"
            >
              {group.title}
            </h4>
            <span className="tabular text-muted-foreground text-[11px]">{group.claims.length}</span>
          </div>
          <ul className="flex flex-col">
            {group.claims.map((claim) => (
              <ClaimRow key={claim.id} claim={claim} onOpen={onOpen} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
