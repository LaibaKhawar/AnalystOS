import { ArrowRightIcon, PencilSimpleIcon, PlayIcon, TrashIcon, WebhooksLogoIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { DataSource, Schedule } from '@/api/types'
import { Pill } from '@/components/common/StatusBadge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useDeleteSchedule, useRunSchedule, useSaveSchedule } from '@/hooks/queries/schedules'
import { formatDateTime, formatRelative, formatUntil, noDashes } from '@/lib/format'
import { draftFromSchedule, intervalLabel, SEVERITIES, toScheduleInput } from '@/lib/schedules'

function DeleteSchedule({ schedule }: { schedule: Schedule }) {
  const remove = useDeleteSchedule()
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete schedule ${schedule.name}`}>
          <TrashIcon />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {schedule.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            No more runs are started. Analyses it already ran stay in the workspace and its alerts stay in your inbox.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction
            className="bg-danger hover:bg-danger/90 text-white"
            onClick={() =>
              remove.mutate(schedule.id, {
                onSuccess: () => toast(`${schedule.name} deleted`),
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const STATUS: Record<string, { tone: 'success' | 'brand' | 'danger' | 'neutral'; label: string }> = {
  completed: { tone: 'success', label: 'Completed' },
  running: { tone: 'brand', label: 'Running' },
  queued: { tone: 'neutral', label: 'Queued' },
  failed: { tone: 'danger', label: 'Failed' },
}

function LastStatus({ status }: { status: string }) {
  const known = STATUS[status] ?? { tone: 'neutral' as const, label: status }
  return (
    <Pill tone={known.tone} className="ml-1.5 align-middle">
      <span data-testid="schedule-last-status">{known.label}</span>
    </Pill>
  )
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-[11px]">{label}</dt>
      <dd className="text-foreground mt-0.5 truncate text-xs">{children}</dd>
    </div>
  )
}

export function ScheduleCard({
  schedule,
  source,
  canRun,
  onEdit,
}: {
  schedule: Schedule
  source: DataSource | undefined
  /** False when the user lost ask access to the source (or is a viewer): runs and edits would be refused. */
  canRun: boolean
  onEdit: () => void
}) {
  const run = useRunSchedule()
  const toggle = useSaveSchedule()
  const severity = SEVERITIES.find((s) => s.value === schedule.alert_min_severity)?.label ?? schedule.alert_min_severity
  const error = run.error ?? toggle.error

  return (
    <li className="flex flex-col gap-3 p-4" data-testid="schedule-row" data-schedule-id={schedule.id}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-foreground text-sm font-medium">{schedule.name}</span>
            {schedule.enabled ? <Pill tone="success">Active</Pill> : <Pill>Paused</Pill>}
          </p>
          <p className="text-muted-foreground mt-1 text-sm">{noDashes(schedule.question)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Switch
            checked={schedule.enabled}
            aria-label={schedule.enabled ? `Pause ${schedule.name}` : `Resume ${schedule.name}`}
            disabled={toggle.isPending || !canRun}
            onCheckedChange={(enabled) =>
              toggle.mutate({ id: schedule.id, input: { ...toScheduleInput(draftFromSchedule(schedule)), enabled } })
            }
            className="mr-2"
          />
          <Button
            variant="outline"
            size="sm"
            disabled={run.isPending || !canRun}
            onClick={() =>
              run.mutate(schedule.id, {
                onSuccess: () => toast.success(`${schedule.name} is running. Its answer appears under Last run.`),
              })
            }
            data-testid="schedule-run"
          >
            <PlayIcon data-icon="inline-start" weight="fill" />
            {run.isPending ? 'Starting' : 'Run now'}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Edit schedule ${schedule.name}`}
            onClick={onEdit}
            disabled={!canRun}
          >
            <PencilSimpleIcon />
          </Button>
          <DeleteSchedule schedule={schedule} />
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
        <Meta label="Data source">
          {source ? (
            <Link to={`/sources/${source.id}`} className="hover:underline">
              {source.name}
            </Link>
          ) : (
            'No longer available'
          )}
        </Meta>
        <Meta label="Runs">{intervalLabel(schedule.interval_minutes)}</Meta>
        <Meta label="Alerts">
          <span className="inline-flex items-center gap-1">
            {severity}
            {schedule.webhook_url && (
              <WebhooksLogoIcon className="text-muted-foreground size-3.5" aria-label="Webhook configured" />
            )}
          </span>
        </Meta>
        <Meta label="Next run">
          {schedule.enabled ? (
            <time dateTime={schedule.next_run_at} title={formatDateTime(schedule.next_run_at)}>
              {formatUntil(schedule.next_run_at)}
            </time>
          ) : (
            'Paused'
          )}
        </Meta>
        <Meta label="Last run">
          {schedule.last_run_at ? (
            <time dateTime={schedule.last_run_at} title={formatDateTime(schedule.last_run_at)}>
              {formatRelative(schedule.last_run_at)}
            </time>
          ) : (
            'Never'
          )}
          {schedule.last_status && <LastStatus status={schedule.last_status} />}
        </Meta>
      </dl>
      {schedule.last_analysis_id && (
        <Link
          to={`/workspace/by-analysis/${schedule.last_analysis_id}`}
          className="text-brand-text focus-visible:ring-ring/60 inline-flex w-fit items-center gap-1 rounded-md text-xs font-medium outline-none hover:underline focus-visible:ring-2"
          data-testid="schedule-last-analysis"
        >
          Open the last analysis
          <ArrowRightIcon className="size-3" />
        </Link>
      )}
      {error && (
        <p className="text-danger text-xs" role="alert">
          {errorMessage(error)}
        </p>
      )}
    </li>
  )
}
