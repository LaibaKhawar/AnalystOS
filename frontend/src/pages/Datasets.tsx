import { DatabaseIcon, TableIcon } from '@phosphor-icons/react'
import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { errorMessage } from '@/api/client'
import { sourcesApi } from '@/api/endpoints'
import type { DataSource } from '@/api/types'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { SourceStatusBadge } from '@/components/common/StatusBadge'
import { Field } from '@/components/forms/Field'
import { AccessNotice } from '@/components/common/AccessNotice'
import { AccessBadges } from '@/components/sources/AccessBadges'
import { DeleteSourceButton } from '@/components/sources/DeleteSourceButton'
import { UploadDropzone, type UploadItem } from '@/components/ui/file-upload-4'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ContinuousTabs } from '@/components/watermelon/continuous-tabs'
import { qk } from '@/hooks/queries/keys'
import { useSources } from '@/hooks/queries/sources'
import { useRoleAbilities, useSourceAbilities } from '@/hooks/usePermissions'
import { formatBytes, formatInteger, formatRelative } from '@/lib/format'
import { VIEWER_EXPLANATION } from '@/lib/permissions'
import { validateUpload } from '@/lib/upload'

type Filter = 'all' | 'file' | 'database'

function SourceRow({ source }: { source: DataSource }) {
  const isFile = source.kind === 'file'
  const abilities = useSourceAbilities(source)
  return (
    <li className="flex items-center gap-3 px-3 py-3 sm:px-4">
      <span className="bg-muted/40 flex size-8 shrink-0 items-center justify-center rounded-lg border">
        {isFile ? (
          <TableIcon className="text-muted-foreground size-4" />
        ) : (
          <DatabaseIcon className="text-muted-foreground size-4" />
        )}
      </span>
      <Link
        to={`/sources/${source.id}`}
        className="focus-visible:ring-ring/60 min-w-0 flex-1 rounded-md outline-none focus-visible:ring-2"
      >
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-foreground truncate text-sm font-medium hover:underline">{source.name}</span>
          <AccessBadges source={source} />
        </span>
        <span className="text-muted-foreground block truncate text-xs">
          {isFile
            ? `${(source.file_type ?? '').toUpperCase()}, ${formatBytes(source.size_bytes)}`
            : `${source.kind}, ${source.database ?? ''}`}
          , {formatInteger(source.table_count)} {source.table_count === 1 ? 'table' : 'tables'},{' '}
          {formatInteger(source.row_count)} rows, added {formatRelative(source.created_at)}
        </span>
      </Link>
      <span className="hidden sm:block">
        <SourceStatusBadge status={source.status} />
      </span>
      {abilities?.canManage && <DeleteSourceButton source={source} />}
    </li>
  )
}

export default function Datasets() {
  const sources = useSources()
  const { canCreate } = useRoleAbilities()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [items, setItems] = useState<UploadItem[]>([])
  const [name, setName] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const files = useRef(new Map<string, File>())

  const patch = (id: string, change: Partial<UploadItem>) =>
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...change } : i)))

  const start = (id: string, file: File) => {
    patch(id, { status: 'uploading', progress: 0, error: undefined })
    const handle = sourcesApi.upload(file, name, (fraction) =>
      patch(id, { progress: fraction, status: fraction >= 1 ? 'processing' : 'uploading' }),
    )
    handle.promise
      .then((source) => {
        patch(id, { status: 'completed', progress: 1 })
        client.setQueryData(qk.source(source.id), source)
        void client.invalidateQueries({ queryKey: qk.sources })
        void client.invalidateQueries({ queryKey: qk.dashboard })
        setName('')
        navigate(`/sources/${source.id}?uploaded=1`)
      })
      .catch((error: unknown) => patch(id, { status: 'error', error: errorMessage(error) }))
  }

  const onFiles = (list: File[]) => {
    const file = list[0]
    if (!file) return
    const id = `${file.name}-${Date.now()}`
    files.current.set(id, file)
    const check = validateUpload(file)
    setItems((prev) => [
      {
        id,
        name: file.name,
        size: file.size,
        progress: 0,
        status: check.ok ? 'uploading' : 'error',
        error: check.ok ? undefined : check.message,
      },
      ...prev,
    ])
    if (check.ok) start(id, file)
  }

  const visible = (sources.data ?? []).filter(
    (s) => filter === 'all' || (filter === 'file' ? s.kind === 'file' : s.kind !== 'file'),
  )
  const uploading = items.some((i) => i.status === 'uploading' || i.status === 'processing')

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Datasets"
        description="Upload CSV or Excel files. Each file is profiled on arrival: types, roles, missing values, outliers and likely PII."
      />

      {!canCreate && (
        <AccessNotice title="Uploading is not available for your role">
          {VIEWER_EXPLANATION} Datasets shared with you are listed below.
        </AccessNotice>
      )}

      {canCreate && (
        <section aria-labelledby="upload-title" className="bg-card rounded-lg border p-4 sm:p-5">
          <h2 id="upload-title" className="text-foreground text-sm font-medium">
            Upload a file
          </h2>
          <Field label="Dataset name" optional hint="Defaults to the file name." className="mt-4 max-w-sm">
            {(p) => (
              <Input
                {...p}
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
                disabled={uploading}
              />
            )}
          </Field>
          <UploadDropzone
            className="mt-4"
            items={items}
            onFiles={onFiles}
            disabled={uploading}
            onRemove={(id) => setItems((prev) => prev.filter((i) => i.id !== id))}
            onRetry={(id) => {
              const file = files.current.get(id)
              if (file && validateUpload(file).ok) start(id, file)
            }}
          />
        </section>
      )}

      <section aria-labelledby="sources-title" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="sources-title" className="text-foreground text-sm font-medium">
            Your data sources
          </h2>
          <ContinuousTabs<Filter>
            ariaLabel="Filter sources"
            value={filter}
            onChange={setFilter}
            tabs={[
              { id: 'all', label: 'All', count: sources.data?.length },
              { id: 'file', label: 'Files', count: sources.data?.filter((s) => s.kind === 'file').length },
              { id: 'database', label: 'Databases', count: sources.data?.filter((s) => s.kind !== 'file').length },
            ]}
          />
        </div>
        {sources.isPending && (
          <div className="flex flex-col gap-2 rounded-lg border p-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="size-8" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-72 max-w-full" />
                </div>
              </div>
            ))}
          </div>
        )}
        {sources.isError && <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />}
        {sources.data && visible.length === 0 && (
          <EmptyState
            icon={<TableIcon className="size-4" />}
            title={filter === 'database' ? 'No database connections' : 'No datasets yet'}
            description={
              filter === 'database' ? (
                <>
                  Add PostgreSQL, MySQL or SQLite on the{' '}
                  <Link className="text-brand-text underline" to="/connections">
                    Connections
                  </Link>{' '}
                  page.
                </>
              ) : canCreate ? (
                'Drop a .csv or .xlsx file above. It will be profiled and ready to question in seconds.'
              ) : (
                'When someone shares a dataset or connection with you, it appears here.'
              )
            }
          />
        )}
        {visible.length > 0 && (
          <ul className="bg-card divide-y rounded-lg border" data-testid="source-list">
            {visible.map((s) => (
              <SourceRow key={s.id} source={s} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
