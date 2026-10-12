import type { Claim } from '@/api/types'

export type ClaimGroupKey = 'facts' | 'interpretations' | 'recommendations'

export interface ClaimGroup {
  key: ClaimGroupKey
  title: string
  description: string
  claims: Claim[]
}

const FACT_SECTIONS = ['summary', 'finding', 'trend', 'anomaly', 'segment', 'driver'] as const

const SECTION_ORDER: Record<string, number> = Object.fromEntries(FACT_SECTIONS.map((s, i) => [s, i]))

/**
 * Group claims into the three answer blocks.
 * - facts: kind "fact" (sections summary/finding/trend/anomaly/segment/driver)
 * - interpretations: kind "interpretation", including qualified hypotheses
 * - recommendations: kind "recommendation"
 * Removed claims and caveats are excluded (caveats render from answer.caveats).
 */
export function groupClaims(claims: Claim[]): ClaimGroup[] {
  const visible = claims.filter((c) => c.status !== 'removed' && c.kind !== 'caveat' && c.section !== 'headline')
  const facts: Claim[] = []
  const interpretations: Claim[] = []
  const recommendations: Claim[] = []
  for (const claim of visible) {
    if (claim.kind === 'recommendation' || claim.section === 'recommendation') recommendations.push(claim)
    else if (claim.kind === 'interpretation' || claim.section === 'interpretation') interpretations.push(claim)
    else facts.push(claim)
  }
  facts.sort((a, b) => {
    const sa = SECTION_ORDER[a.section] ?? 99
    const sb = SECTION_ORDER[b.section] ?? 99
    return sa === sb ? a.ordinal - b.ordinal : sa - sb
  })
  interpretations.sort((a, b) => a.ordinal - b.ordinal)
  recommendations.sort((a, b) => a.ordinal - b.ordinal)
  const groups: ClaimGroup[] = [
    {
      key: 'facts',
      title: 'Facts',
      description: 'Computed from your data. Every number is matched to a query result.',
      claims: facts,
    },
    {
      key: 'interpretations',
      title: 'Interpretations',
      description: 'Readings of the facts. Hypotheses are marked as qualified.',
      claims: interpretations,
    },
    {
      key: 'recommendations',
      title: 'Recommendations',
      description: 'Suggested next actions based on the findings.',
      claims: recommendations,
    },
  ]
  return groups.filter((g) => g.claims.length > 0)
}

export type ClaimBadge = { label: string; tone: 'success' | 'warning' | 'neutral' | 'danger' }

export function claimBadge(status: string): ClaimBadge {
  switch (status) {
    case 'verified':
      return { label: 'Verified', tone: 'success' }
    case 'qualified':
      return { label: 'Qualified', tone: 'warning' }
    case 'no_numbers':
      return { label: 'No numbers', tone: 'neutral' }
    case 'removed':
      return { label: 'Removed', tone: 'danger' }
    default:
      return { label: status.replace(/_/g, ' '), tone: 'neutral' }
  }
}

export function sectionLabel(section: string): string | null {
  if (section === 'summary' || section === 'finding') return null
  return section.charAt(0).toUpperCase() + section.slice(1)
}
