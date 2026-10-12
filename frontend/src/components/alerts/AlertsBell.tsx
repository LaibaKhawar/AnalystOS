import { BellIcon, BellRingingIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link } from 'react-router'
import { ErrorState } from '@/components/common/States'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { useUnreadAlertCount, useUnreadAlerts } from '@/hooks/queries/alerts'
import { AlertItem } from './AlertItem'

const SHOWN = 5

/** Bell with the unread alert count (polled every minute) and a panel that loads the latest unread alerts on open. */
export function AlertsBell() {
  const [open, setOpen] = useState(false)
  const unreadCount = useUnreadAlertCount()
  const unread = useUnreadAlerts(open)
  const count = unreadCount.data ?? 0
  const label = count > 0 ? `Alerts, ${count} unread` : 'Alerts, none unread'
  const Icon = count > 0 ? BellRingingIcon : BellIcon

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={label} className="relative" data-testid="alerts-bell">
          <Icon className="size-4" weight={count > 0 ? 'fill' : 'regular'} />
          {count > 0 && (
            <span
              className="bg-brand text-background tabular absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] leading-none font-semibold"
              data-testid="alerts-count"
              aria-hidden="true"
            >
              {count > 99 ? '99+' : count}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <p className="text-foreground text-sm font-medium">Alerts</p>
          <Link
            to="/alerts"
            onClick={() => setOpen(false)}
            className="text-brand-text focus-visible:ring-ring/60 rounded-sm text-xs outline-none hover:underline focus-visible:ring-2"
          >
            View all
          </Link>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {unread.isPending && (
            <div className="flex flex-col gap-2 p-3" aria-busy="true" aria-label="Loading alerts">
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          )}
          {unread.isError && (
            <ErrorState compact error={unread.error} className="m-3" onRetry={() => void unread.refetch()} />
          )}
          {unread.data?.length === 0 && (
            <p className="text-muted-foreground px-3 py-6 text-center text-sm">
              No unread alerts. Scheduled analyses raise one when they find an anomaly or fail.
            </p>
          )}
          {count > 0 && (
            <ul className="divide-y">
              {unread.data?.slice(0, SHOWN).map((a) => (
                <AlertItem key={a.id} alert={a} compact onNavigate={() => setOpen(false)} />
              ))}
            </ul>
          )}
          {count > SHOWN && (
            <p className="text-muted-foreground border-t px-3 py-2 text-xs">
              {count - SHOWN} more unread on the alerts page.
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
