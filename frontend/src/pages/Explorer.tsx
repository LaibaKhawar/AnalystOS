import { ChatCenteredTextIcon, CheckCircleIcon, WarningIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { SourceStatusBadge } from '@/components/common/StatusBadge'
import { PreviewPanel } from '@/components/explorer/PreviewPanel'
import { ProfilePanel } from '@/components/explorer/ProfilePanel'
import { SchemaGrid } from '@/components/explorer/SchemaGrid'
import { SemanticSummary } from '@/components/explorer/SemanticSummary'
import { AccessNotice } from '@/components/common/AccessNotice'
import { RelationshipsPanel } from '@/components/explorer/RelationshipsPanel'
import { MetricsPanel } from '@/components/metrics/MetricsPanel'
import { AccessBadges } from '@/components/sources/AccessBadges'
import { DeleteSourceButton } from '@/components/sources/DeleteSourceButton'
import { ShareDialog } from '@/components/sources/ShareDialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { ContinuousTabs } from '@/components/watermelon/continuous-tabs'
import { tabPanelProps } from '@/lib/tabs'
import { useCreateConversation } from '@/hooks/queries/conversations'
import { useSource, useTables } from '@/hooks/queries/sources'
import { useMetrics } from '@/hooks/queries/metrics'
import { useRoleAbilities, useSourceAbilities } from '@/hooks/usePermissions'
import { VIEWER_EXPLANATION } from '@/lib/permissions'
import { sourceRelationships } from '@/lib/relationships'
import { formatBytes, formatInteger } from '@/lib/format'

type Section = 'schema' | 'preview' | 'profile' | 'semantics' | 'metrics' | 'relationships'

function ExplorerSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading dataset">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <Skeleton className="h-9 w-80 max-w-full" />
      <Skeleton className="h-96" />
    </div>
  )
}

export default function Explorer() {
  const { sourceId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const source = useSource(sourceId)
  const tables = useTables(sourceId)
  const create = useCreateConversation()
  const metrics = useMetrics(sourceId)
  const abilities = useSourceAbilities(source.data)
  const { canCreate } = useRoleAbilities()
  const [section, setSection] = useState<Section>('schema')
  const [tableId, setTableId] = useState<string | null>(null)
  const justUploaded = params.get('uploaded') === '1'

  if (source.isPending) return <ExplorerSkeleton />
  if (source.isError)
    return (
      <ErrorState error={source.error} title="Could not open this data source" onRetry={() => void source.refetch()} />
    )

  const s = source.data
  const canManage = abilities?.canManage ?? false
  const canAsk = abilities?.canAsk ?? false
  const relationshipCount = sourceRelationships(s).length
  const largest = tables.data?.reduce<(typeof tables.data)[number] | undefined>(
    (best, t) => (!best || t.row_count > best.row_count ? t : best),
    undefined,
  )
  const table = tables.data?.find((t) => t.id === tableId) ?? largest
  const warnings = (s.ingestion_report?.tables ?? []).flatMap((t) =>
    t.warnings.map((w) => `${t.display_name ?? t.name}: ${w}`),
  )

  const ask = () =>
    create.mutate(
      { sourceId: s.id },
      { onSuccess: (c) => navigate(`/workspace/${c.id}`), onError: (e) => toast.error(errorMessage(e)) },
    )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={s.name}
        description={
          s.kind === 'file'
            ? `${(s.file_type ?? '').toUpperCase()} file, ${formatBytes(s.size_bytes)}, ${formatInteger(s.table_count)} ${s.table_count === 1 ? 'table' : 'tables'}, ${formatInteger(s.row_count)} rows`
            : `${s.kind} connection to ${s.database ?? ''}, ${formatInteger(s.table_count)} tables`
        }
        actions={
          <>
            <AccessBadges source={s} />
            <SourceStatusBadge status={s.status} />
            {canManage && <DeleteSourceButton source={s} onDeleted={() => navigate('/datasets')} />}
            {canManage && <ShareDialog source={s} />}
            {canAsk && (
              <Button onClick={ask} disabled={create.isPending || s.status !== 'ready'} data-testid="ask-question">
                <ChatCenteredTextIcon data-icon="inline-start" />
                {create.isPending ? 'Opening workspace' : 'Ask a question'}
              </Button>
            )}
          </>
        }
      />

      {!canAsk && (
        <AccessNotice
          tone="read"
          title={
            canCreate ? 'You have read-only access to this source' : 'Asking questions is not available for your role'
          }
          testId="read-only-notice"
        >
          {canCreate
            ? 'You can explore the schema, preview, profile, metrics and join keys. Ask the owner to share it with you as an analyst to ask questions about it.'
            : VIEWER_EXPLANATION}
        </AccessNotice>
      )}

      {justUploaded && (
        <div
          className="border-brand/30 bg-brand-soft flex items-start justify-between gap-3 rounded-lg border p-3 text-sm"
          role="status"
        >
          <span className="flex items-start gap-2">
            <CheckCircleIcon className="text-brand mt-0.5 size-4 shrink-0" weight="fill" />
            <span className="text-foreground">
              Uploaded and profiled. Review the schema below, then ask a question.
            </span>
          </span>
          <Button variant="ghost" size="xs" onClick={() => setParams({}, { replace: true })}>
            Dismiss
          </Button>
        </div>
      )}

      {warnings.length > 0 && (
        <div
          className="border-warning/30 bg-warning-soft rounded-lg border p-3"
          role="status"
          data-testid="ingestion-warnings"
        >
          <p className="text-foreground flex items-center gap-1.5 text-sm font-medium">
            <WarningIcon className="text-warning size-4" weight="fill" />
            Ingestion warnings
          </p>
          <ul className="text-foreground/90 mt-1 list-disc pl-6 text-sm">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {tables.isPending && <Skeleton className="h-96" />}
      {tables.isError && <ErrorState error={tables.error} onRetry={() => void tables.refetch()} />}
      {tables.data && tables.data.length === 0 && (
        <EmptyState
          title="No tables found"
          description={
            s.kind === 'file'
              ? 'The file had no readable sheets. Upload it again or check the format.'
              : 'The connection has no tables the analyst may read. Check allowed tables, or refresh the connection.'
          }
        />
      )}

      {table && (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {section === 'metrics' || section === 'relationships' ? (
              <p className="text-muted-foreground text-sm">
                Across all {formatInteger(s.table_count)} {s.table_count === 1 ? 'table' : 'tables'} of this source
              </p>
            ) : tables.data && tables.data.length > 1 ? (
              <div className="flex items-center gap-2">
                <label htmlFor="table-select" className="text-muted-foreground text-xs">
                  Table
                </label>
                <Select value={table.id} onValueChange={setTableId}>
                  <SelectTrigger id="table-select" className="w-64 max-w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {tables.data.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.display_name || t.name} ({formatInteger(t.row_count)} rows)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">
                Table <span className="text-foreground font-mono">{table.name}</span>, {formatInteger(table.row_count)}{' '}
                rows, {table.column_count} columns
              </p>
            )}
            <div className="overflow-x-auto">
              <ContinuousTabs<Section>
                ariaLabel="Explorer sections"
                idPrefix="explorer"
                value={section}
                onChange={setSection}
                tabs={[
                  { id: 'schema', label: 'Schema' },
                  { id: 'preview', label: 'Preview' },
                  { id: 'profile', label: 'Profile' },
                  { id: 'semantics', label: 'Semantics' },
                  { id: 'metrics', label: 'Metrics', count: metrics.data?.length },
                  { id: 'relationships', label: 'Relationships', count: relationshipCount },
                ]}
              />
            </div>
          </div>
          <div {...tabPanelProps('explorer', section)}>
            {section === 'schema' && <SchemaGrid sourceId={s.id} table={table} editable={canManage} />}
            {section === 'preview' && <PreviewPanel sourceId={s.id} tableId={table.id} />}
            {section === 'profile' && <ProfilePanel table={table} />}
            {section === 'semantics' && <SemanticSummary table={table} />}
            {section === 'metrics' && <MetricsPanel sourceId={s.id} tables={tables.data ?? []} canManage={canManage} />}
            {section === 'relationships' && <RelationshipsPanel source={s} />}
          </div>
        </>
      )}
    </div>
  )
}
