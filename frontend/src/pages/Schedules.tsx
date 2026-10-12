import { CalendarDotsIcon, PlusIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import type { Schedule } from '@/api/types'
import { AccessNotice } from '@/components/common/AccessNotice'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { ScheduleCard } from '@/components/schedules/ScheduleCard'
import { ScheduleForm } from '@/components/schedules/ScheduleForm'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useSchedules } from '@/hooks/queries/schedules'
import { useSources } from '@/hooks/queries/sources'
import { useRoleAbilities } from '@/hooks/usePermissions'
import { sourceAbilities, VIEWER_EXPLANATION } from '@/lib/permissions'
import { useAuth } from '@/providers/auth-context'

function SchedulesSkeleton() {
  return (
    <div className="bg-card flex flex-col divide-y rounded-lg border" aria-busy="true" aria-label="Loading schedules">
      {[0, 1].map((i) => (
        <div key={i} className="flex flex-col gap-3 p-4">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-full max-w-lg" />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {[0, 1, 2, 3, 4].map((j) => (
              <Skeleton key={j} className="h-8" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Schedules() {
  const schedules = useSchedules()
  const sources = useSources()
  const { user } = useAuth()
  const { canCreate } = useRoleAbilities()
  const [editing, setEditing] = useState<Schedule | 'new' | null>(null)
  const askable = (sources.data ?? []).filter((s) => s.status === 'ready' && sourceAbilities(s, user).canAsk)
  const current = editing === 'new' ? null : editing
  const sourceById = new Map((sources.data ?? []).map((s) => [s.id, s]))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Schedules"
        description="Ask the same question on a timer. Each run is a full, verified analysis; anomalies at or above your threshold raise an alert."
        actions={
          canCreate && (
            <Button onClick={() => setEditing('new')} disabled={sources.isPending} data-testid="new-schedule">
              <PlusIcon data-icon="inline-start" />
              New schedule
            </Button>
          )
        }
      />
      {!canCreate && (
        <AccessNotice title="Scheduling is not available for your role">{VIEWER_EXPLANATION}</AccessNotice>
      )}

      {schedules.isPending && <SchedulesSkeleton />}
      {schedules.isError && <ErrorState error={schedules.error} onRetry={() => void schedules.refetch()} />}
      {schedules.data?.length === 0 && (
        <EmptyState
          icon={<CalendarDotsIcon className="size-4" />}
          title="No schedules yet"
          description={
            canCreate ? (
              'Create one to watch a metric: for example, ask every morning which region is behind and get an alert when something looks unusual.'
            ) : (
              <>
                Schedules run questions automatically. Browse{' '}
                <Link className="text-brand-text underline" to="/datasets">
                  shared datasets
                </Link>{' '}
                in the meantime.
              </>
            )
          }
          action={
            canCreate && askable.length === 0 && sources.data ? (
              <Button asChild variant="outline">
                <Link to="/datasets">Upload a dataset first</Link>
              </Button>
            ) : undefined
          }
        />
      )}
      {(schedules.data?.length ?? 0) > 0 && (
        <ul className="bg-card divide-y rounded-lg border" data-testid="schedule-list">
          {schedules.data?.map((s) => {
            const source = sourceById.get(s.data_source_id)
            return (
              <ScheduleCard
                key={s.id}
                schedule={s}
                source={source}
                canRun={canCreate && Boolean(source && sourceAbilities(source, user).canAsk)}
                onEdit={() => setEditing(s)}
              />
            )
          })}
        </ul>
      )}

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl" data-testid="schedule-dialog">
          <DialogHeader>
            <DialogTitle>{current ? `Edit ${current.name}` : 'New schedule'}</DialogTitle>
            <DialogDescription>
              Runs in its own conversation, so you can open any run in the workspace and see its evidence.
            </DialogDescription>
          </DialogHeader>
          {editing !== null &&
            (askable.length === 0 && !current ? (
              <EmptyState
                title="No data source to schedule"
                description="You need a ready dataset or connection that you can ask questions about. Upload one, or ask its owner for analyst access."
              />
            ) : (
              <ScheduleForm
                key={current?.id ?? 'new'}
                sources={
                  current && !askable.some((s) => s.id === current.data_source_id) ? (sources.data ?? []) : askable
                }
                schedule={current}
                onCancel={() => setEditing(null)}
                onSaved={(s) => {
                  toast.success(current ? `${s.name} updated` : `${s.name} scheduled`)
                  setEditing(null)
                }}
              />
            ))}
        </DialogContent>
      </Dialog>
    </div>
  )
}
