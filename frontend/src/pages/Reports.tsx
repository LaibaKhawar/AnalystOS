import { FileTextIcon } from '@phosphor-icons/react'
import { Link } from 'react-router'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { Skeleton } from '@/components/ui/skeleton'
import { useReports } from '@/hooks/queries/reports'
import { formatCost, formatDateTime, noDashes } from '@/lib/format'

export default function Reports() {
  const reports = useReports()
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reports"
        description="Self-contained reports with the answer, charts, verified statements and the evidence behind each number."
      />
      {reports.isPending && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}
      {reports.isError && <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />}
      {reports.data?.length === 0 && (
        <EmptyState
          icon={<FileTextIcon className="size-4" />}
          title="No reports yet"
          description="Open a completed analysis in the workspace and choose Generate report. You can also ask the analyst to produce a report in your question."
        />
      )}
      {(reports.data?.length ?? 0) > 0 && (
        <ul className="bg-card divide-y rounded-lg border">
          {reports.data?.map((r) => (
            <li key={r.id}>
              <Link
                to={`/reports/${r.id}`}
                className="hover:bg-muted/40 focus-visible:ring-ring/60 flex items-start gap-3 px-4 py-3 outline-none focus-visible:ring-2"
              >
                <FileTextIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="text-foreground block truncate text-sm font-medium">{noDashes(r.title)}</span>
                  <span className="text-muted-foreground block truncate text-xs">
                    {r.content.headline ? noDashes(String(r.content.headline)) : ''}
                  </span>
                </span>
                <span className="text-muted-foreground hidden shrink-0 text-right text-xs sm:block">
                  <span className="block">{formatDateTime(r.created_at)}</span>
                  {r.content.dataset?.name && <span className="block">{r.content.dataset.name}</span>}
                  {typeof r.content.cost_usd === 'number' && (
                    <span className="block font-mono">{formatCost(r.content.cost_usd)}</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
