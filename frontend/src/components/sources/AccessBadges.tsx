import { EyeIcon, ShareNetworkIcon } from '@phosphor-icons/react'
import type { DataSource } from '@/api/types'
import { Pill } from '@/components/common/StatusBadge'
import { ACCESS_LABEL, sourceAccess } from '@/lib/permissions'

/** "Shared with you" and the access level, for sources the user does not own. Owners see nothing. */
export function AccessBadges({ source }: { source: Pick<DataSource, 'access' | 'owned'> }) {
  if (source.owned !== false) return null
  const access = sourceAccess(source)
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="shared-badge">
      <Pill tone="brand" icon={<ShareNetworkIcon />}>
        Shared with you
      </Pill>
      <Pill tone="neutral" icon={access === 'read' ? <EyeIcon /> : undefined}>
        {ACCESS_LABEL[access]}
      </Pill>
    </span>
  )
}
