import { ArrowRightIcon, CheckIcon, WarningIcon, WebhooksLogoIcon } from '@phosphor-icons/react'
import { Link } from 'react-router'
import type { Alert } from '@/api/types'
import { Pill } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { useMarkAlertRead } from '@/hooks/queries/alerts'
import { deliveryLabel, severityLabel, severityTone } from '@/lib/alerts'
import { formatDateTime, formatRelative, noDashes } from '@/lib/format'
import { cn } from '@/lib/utils'

/** One alert: severity, title, message, delivery status, time, link to the analysis and "mark read". */
export function AlertItem({
  alert,
  compact = false,
  onNavigate,
}: {
  alert: Alert
  compact?: boolean
  onNavigate?: () => void
}) {
  const markRead = useMarkAlertRead()
  const unread = alert.read_at === null
  const delivery = deliveryLabel(alert.delivery_status)
  return (
    <li
      className={cn('flex flex-col gap-1.5', compact ? 'px-3 py-2.5' : 'px-4 py-3', unread && 'bg-brand-soft/40')}
      data-testid="alert-item"
      data-unread={unread || undefined}
    >
      <div className="flex items-start gap-2">
        <span
          className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', unread ? 'bg-brand' : 'bg-transparent')}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5">
            <Pill
              tone={severityTone(alert.severity)}
              icon={alert.severity === 'high' ? <WarningIcon weight="fill" /> : undefined}
            >
              {severityLabel(alert.severity)}
            </Pill>
            <span className={cn('text-foreground text-sm', unread && 'font-medium')}>{noDashes(alert.title)}</span>
            {unread && <span className="sr-only">(unread)</span>}
          </p>
          <p
            className={cn(
              'text-muted-foreground mt-1 text-xs whitespace-pre-line',
              compact && 'line-clamp-2 whitespace-normal',
            )}
          >
            {noDashes(alert.message)}
          </p>
          <p className="text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            <time dateTime={alert.created_at} title={formatDateTime(alert.created_at)}>
              {formatRelative(alert.created_at)}
            </time>
            <span
              className={cn(
                'inline-flex items-center gap-1',
                delivery.ok === false && 'text-danger',
                delivery.ok === true && 'text-brand-text',
              )}
            >
              <WebhooksLogoIcon className="size-3" />
              {delivery.text}
            </span>
            {alert.analysis_id && (
              <Link
                to={`/workspace/by-analysis/${alert.analysis_id}`}
                onClick={onNavigate}
                className="text-brand-text focus-visible:ring-ring/60 inline-flex items-center gap-0.5 rounded-sm font-medium outline-none hover:underline focus-visible:ring-2"
              >
                Open analysis
                <ArrowRightIcon className="size-3" />
              </Link>
            )}
          </p>
        </div>
        {unread && (
          <Button
            variant="ghost"
            size="xs"
            onClick={() => markRead.mutate(alert.id)}
            disabled={markRead.isPending}
            aria-label={`Mark "${alert.title}" as read`}
          >
            <CheckIcon data-icon="inline-start" />
            Mark read
          </Button>
        )}
      </div>
    </li>
  )
}
