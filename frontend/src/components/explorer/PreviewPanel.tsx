import { DataTable } from '@/components/common/DataTable'
import { ErrorState } from '@/components/common/States'
import { Skeleton } from '@/components/ui/skeleton'
import { usePreview } from '@/hooks/queries/sources'

export function PreviewPanel({ sourceId, tableId }: { sourceId: string; tableId: string }) {
  const preview = usePreview(sourceId, tableId)
  if (preview.isPending)
    return (
      <div className="flex flex-col gap-1.5 rounded-lg border p-3" aria-busy="true">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-5" />
        ))}
      </div>
    )
  if (preview.isError)
    return (
      <ErrorState error={preview.error} title="Could not load the preview" onRetry={() => void preview.refetch()} />
    )
  const d = preview.data
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground text-xs">
        First {d.rows.length} rows.{d.masked_columns.length > 0 && ` Masked as PII: ${d.masked_columns.join(', ')}.`}
      </p>
      <DataTable
        columns={d.columns}
        rows={d.rows}
        masked={d.masked_columns}
        maxHeight="max-h-[480px]"
        caption="Data preview"
      />
    </div>
  )
}
