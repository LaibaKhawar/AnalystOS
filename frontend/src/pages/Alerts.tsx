import { BellIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link } from 'react-router'
import { AlertItem } from '@/components/alerts/AlertItem'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { Skeleton } from '@/components/ui/skeleton'
import { ContinuousTabs } from '@/components/watermelon/continuous-tabs'
import { useAlerts } from '@/hooks/queries/alerts'

type Filter = 'all' | 'unread'

export default function Alerts() {
  const alerts = useAlerts(false, true)
  const [filter, setFilter] = useState<Filter>('all')
  const unread = alerts.data?.filter((a) => a.read_at === null) ?? []
  const visible = filter === 'unread' ? unread : (alerts.data ?? [])

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Alerts"
        description="Raised by scheduled analyses when they find anomalies at or above the schedule's threshold, or when a run fails."
      />
      <div className="flex justify-end">
        <ContinuousTabs<Filter>
          ariaLabel="Filter alerts"
          idPrefix="alerts"
          value={filter}
          onChange={setFilter}
          tabs={[
            { id: 'all', label: 'All', count: alerts.data?.length },
            { id: 'unread', label: 'Unread', count: alerts.data ? unread.length : undefined },
          ]}
        />
      </div>
      {alerts.isPending && (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading alerts">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}
      {alerts.isError && <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />}
      {alerts.data && visible.length === 0 && (
        <EmptyState
          icon={<BellIcon className="size-4" />}
          title={filter === 'unread' ? 'All caught up' : 'No alerts yet'}
          description={
            <>
              Alerts come from{' '}
              <Link className="text-brand-text underline" to="/schedules">
                schedules
              </Link>
              . Create one and choose how severe an anomaly must be before you hear about it.
            </>
          }
        />
      )}
      {visible.length > 0 && (
        <ul className="bg-card divide-y overflow-hidden rounded-lg border" data-testid="alert-list">
          {visible.map((a) => (
            <AlertItem key={a.id} alert={a} />
          ))}
        </ul>
      )}
    </div>
  )
}
