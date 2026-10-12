import { describe, expect, it } from 'vitest'
import type { Claim } from '@/api/types'
import { claimBadge, groupClaims } from './claims'

let n = 0
const claim = (over: Partial<Claim>): Claim => ({
  id: `c${n++}`,
  ordinal: n,
  section: 'finding',
  kind: 'fact',
  text: 'x',
  original_text: null,
  status: 'verified',
  numbers: [],
  verification: {},
  evidence: [],
  ...over,
})

describe('groupClaims', () => {
  it('groups facts, interpretations and recommendations in order', () => {
    const claims = [
      claim({ section: 'driver', kind: 'fact', ordinal: 1 }),
      claim({ section: 'summary', kind: 'fact', ordinal: 5 }),
      claim({ section: 'interpretation', kind: 'interpretation', status: 'qualified', ordinal: 2 }),
      claim({ section: 'recommendation', kind: 'recommendation', status: 'no_numbers', ordinal: 3 }),
      claim({ section: 'anomaly', kind: 'fact', ordinal: 4 }),
    ]
    const groups = groupClaims(claims)
    expect(groups.map((g) => g.key)).toEqual(['facts', 'interpretations', 'recommendations'])
    expect(groups[0].claims.map((c) => c.section)).toEqual(['summary', 'anomaly', 'driver'])
    expect(groups[1].claims[0].status).toBe('qualified')
  })

  it('treats a causal fact downgraded to interpretation as an interpretation', () => {
    const groups = groupClaims([claim({ section: 'finding', kind: 'interpretation' })])
    expect(groups[0].key).toBe('interpretations')
  })

  it('drops removed claims, caveats and empty groups', () => {
    const groups = groupClaims([
      claim({ status: 'removed' }),
      claim({ kind: 'caveat', section: 'caveat' }),
      claim({ kind: 'recommendation', section: 'recommendation' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('recommendations')
  })

  it('labels statuses', () => {
    expect(claimBadge('verified')).toEqual({ label: 'Verified', tone: 'success' })
    expect(claimBadge('qualified').label).toBe('Qualified')
    expect(claimBadge('no_numbers').label).toBe('No numbers')
  })
})
