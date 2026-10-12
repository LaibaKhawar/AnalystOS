import {
  ChatCenteredTextIcon,
  ClockIcon,
  CurrencyDollarIcon,
  DatabaseIcon,
  FileTextIcon,
  PlugsConnectedIcon,
  TableIcon,
  UploadSimpleIcon,
} from '@phosphor-icons/react'
import { Link } from 'react-router'
import { LogoMark } from '@/components/brand/Logo'
import { KeyValue, StatTile } from '@/components/common/Stat'
import { EmptyState, ErrorState } from '@/components/common/States'
import { AnalysisStatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusIndicator } from '@/components/ui/status-indicator'
import { useRecentAnalyses } from '@/hooks/queries/analyses'
import { useSources } from '@/hooks/queries/sources'
import { useDashboard, useSystemStatus } from '@/hooks/queries/system'
import { formatBytes, formatCost, formatDuration, formatInteger, formatRelative, noDashes } from '@/lib/format'
import { useAuth } from '@/providers/auth-context'

function Stats() {
  const dash = useDashboard()
  if (dash.isError)
    return <ErrorState error={dash.error} title="Could not load usage stats" onRetry={() => void dash.refetch()} />
  const d = dash.data
  const loading = dash.isPending
  const running = d?.analyses_by_status?.running ?? 0
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="stat-tiles">
      <StatTile
        label="Datasets"
        icon={<TableIcon />}
        loading={loading}
        value={formatInteger(d?.datasets)}
        hint="Uploaded files"
      />
      <StatTile
        label="Connections"
        icon={<DatabaseIcon />}
        loading={loading}
        value={formatInteger(d?.connections)}
        hint={`${formatInteger(d?.connections_ready)} ready`}
      />
      <StatTile
        label="Analyses"
        icon={<ChatCenteredTextIcon />}
        loading={loading}
        value={formatInteger(d?.analyses)}
        hint={running ? `${running} running now` : `${formatInteger(d?.analyses_by_status?.completed ?? 0)} completed`}
      />
      <StatTile
        label="LLM cost"
        icon={<CurrencyDollarIcon />}
        loading={loading}
        value={formatCost(d?.total_cost_usd)}
        hint={`${formatInteger(d?.total_tokens)} tokens`}
      />
      <StatTile
        label="Avg latency"
        icon={<ClockIcon />}
        loading={loading}
        value={formatDuration(d?.avg_latency_ms ?? undefined)}
        hint="Question to verified answer"
      />
      <StatTile
        label="Reports"
        icon={<FileTextIcon />}
        loading={loading}
        value={formatInteger(d?.reports)}
        hint="Shareable HTML and PDF"
      />
    </div>
  )
}

function RecentDatasets() {
  const sources = useSources()
  return (
    <section className="bg-card min-w-0 rounded-lg border" aria-labelledby="recent-ds">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 id="recent-ds" className="text-foreground text-sm font-medium">
          Recent data sources
        </h2>
        <Link to="/datasets" className="text-brand-text text-xs hover:underline">
          All datasets
        </Link>
      </div>
      <div className="p-2">
        {sources.isPending && (
          <div className="flex flex-col gap-2 p-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        )}
        {sources.isError && <ErrorState compact error={sources.error} onRetry={() => void sources.refetch()} />}
        {sources.data?.length === 0 && (
          <EmptyState
            className="m-2"
            icon={<UploadSimpleIcon className="size-4" />}
            title="No data yet"
            description="Upload a CSV or Excel file, or connect a PostgreSQL, MySQL or SQLite database."
            action={
              <Button asChild size="sm">
                <Link to="/datasets">Upload a file</Link>
              </Button>
            }
          />
        )}
        <ul>
          {sources.data?.slice(0, 6).map((s) => (
            <li key={s.id}>
              <Link
                to={`/sources/${s.id}`}
                className="hover:bg-muted/60 focus-visible:ring-ring/60 flex items-center gap-3 rounded-md px-2 py-2 outline-none focus-visible:ring-2"
              >
                {s.kind === 'file' ? (
                  <TableIcon className="text-muted-foreground size-4" />
                ) : (
                  <DatabaseIcon className="text-muted-foreground size-4" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="text-foreground block truncate text-sm">{s.name}</span>
                  <span className="text-muted-foreground block text-[11px]">
                    {s.kind === 'file' ? `${(s.file_type ?? '').toUpperCase()}, ${formatBytes(s.size_bytes)}` : s.kind},{' '}
                    {formatInteger(s.table_count)} tables, {formatInteger(s.row_count)} rows
                  </span>
                </span>
                <span className="text-muted-foreground text-[11px]">{formatRelative(s.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function RecentAnalyses() {
  const analyses = useRecentAnalyses(8)
  return (
    <section className="bg-card min-w-0 rounded-lg border" aria-labelledby="recent-an">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 id="recent-an" className="text-foreground text-sm font-medium">
          Recent analyses
        </h2>
        <Link to="/workspace" className="text-brand-text text-xs hover:underline">
          Open workspace
        </Link>
      </div>
      <div className="p-2">
        {analyses.isPending && (
          <div className="flex flex-col gap-2 p-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        )}
        {analyses.isError && <ErrorState compact error={analyses.error} onRetry={() => void analyses.refetch()} />}
        {analyses.data?.length === 0 && (
          <EmptyState
            className="m-2"
            icon={<ChatCenteredTextIcon className="size-4" />}
            title="No analyses yet"
            description="Open a dataset and choose Ask a question. Answers show up here with their status and cost."
          />
        )}
        <ul>
          {analyses.data?.map((a) => (
            <li key={a.id}>
              <Link
                to={`/workspace/${a.conversation_id}?analysis=${a.id}`}
                className="hover:bg-muted/60 focus-visible:ring-ring/60 flex items-start gap-3 rounded-md px-2 py-2 outline-none focus-visible:ring-2"
              >
                <span className="min-w-0 flex-1">
                  <span className="text-foreground block truncate text-sm">{noDashes(a.question)}</span>
                  <span className="text-muted-foreground block truncate text-[11px]">
                    {a.summary ? noDashes(a.summary) : a.error ? noDashes(a.error) : formatRelative(a.created_at)}
                  </span>
                </span>
                <AnalysisStatusBadge status={a.status} />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function SystemPanel() {
  const status = useSystemStatus()
  const s = status.data
  return (
    <section className="bg-card min-w-0 rounded-lg border" aria-labelledby="sys">
      <div className="border-b px-4 py-3">
        <h2 id="sys" className="text-foreground text-sm font-medium">
          System status
        </h2>
      </div>
      <div className="px-4 py-2">
        {status.isPending && (
          <div className="flex flex-col gap-2 py-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-5" />
            ))}
          </div>
        )}
        {status.isError && (
          <ErrorState compact error={status.error} className="my-2" onRetry={() => void status.refetch()} />
        )}
        {s && (
          <dl className="divide-y">
            <KeyValue label="Language model">
              <StatusIndicator
                state={s.llm.status === 'ok' ? 'active' : 'down'}
                label={s.llm.status === 'ok' ? 'Reachable' : s.llm.status}
                labelClassName="text-sm"
              />
            </KeyValue>
            <KeyValue label="Model">
              <span className="font-mono text-xs">{s.llm.model}</span>
            </KeyValue>
            <KeyValue label="Python sandbox">
              <StatusIndicator
                state={s.sandbox.status === 'ok' ? 'active' : 'down'}
                label={s.sandbox.status === 'ok' ? 'Available' : 'Unavailable'}
              />
            </KeyValue>
            <KeyValue label="Sandbox limits">
              {s.sandbox.limits.cpus} CPU, {s.sandbox.limits.memory_mb} MB, {s.sandbox.limits.timeout_seconds}s, network{' '}
              {s.sandbox.limits.network}
            </KeyValue>
            <KeyValue label="SQL limits">
              {formatInteger(s.sql.max_rows)} rows, {s.sql.timeout_seconds}s timeout
            </KeyValue>
            <KeyValue label="Worker">{s.worker_mode === 'celery' ? 'Background worker' : 'Inline'}</KeyValue>
          </dl>
        )}
      </div>
    </section>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-center gap-3">
          <LogoMark className="size-9" />
          <div>
            <h1 className="text-foreground text-xl font-semibold tracking-[-0.015em] sm:text-2xl">
              {user ? `Welcome back, ${user.name.split(' ')[0]}` : 'Dashboard'}
            </h1>
            <p className="text-muted-foreground mt-0.5 text-sm">The analyst that shows its work.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link to="/connections">
              <PlugsConnectedIcon data-icon="inline-start" />
              Connect database
            </Link>
          </Button>
          <Button asChild>
            <Link to="/datasets">
              <UploadSimpleIcon data-icon="inline-start" />
              Upload data
            </Link>
          </Button>
        </div>
      </header>
      <Stats />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <RecentAnalyses />
        <div className="flex flex-col gap-4">
          <RecentDatasets />
          <SystemPanel />
        </div>
      </div>
    </div>
  )
}
