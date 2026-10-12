import { CheckCircleIcon, XCircleIcon } from '@phosphor-icons/react'
import type { PythonRecord } from '@/api/types'
import { DataTable } from '@/components/common/DataTable'
import { ErrorState } from '@/components/common/States'
import { CodeBlock } from '@/components/ui/code-block'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { useArtifact, useExecution } from '@/hooks/queries/analyses'
import { formatCell, formatDuration, humanize, noDashes } from '@/lib/format'

function Artifact({
  analysisId,
  pythonId,
  file,
  title,
}: {
  analysisId: string
  pythonId: string
  file: string
  title: string | null
}) {
  const img = useArtifact(analysisId, pythonId, file)
  if (img.isPending) return <Skeleton className="h-48 w-full" />
  if (img.isError)
    return <ErrorState compact error={img.error} title={`Could not load ${file}`} onRetry={() => void img.refetch()} />
  return (
    <figure className="overflow-hidden rounded-lg border bg-white">
      <img src={img.data} alt={title ?? file} className="w-full" />
      <figcaption className="bg-card text-muted-foreground border-t px-3 py-1.5 text-xs">{title ?? file}</figcaption>
    </figure>
  )
}

function PythonSection({ py, analysisId }: { py: PythonRecord; analysisId: string }) {
  const limits = py.limits ?? {}
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-muted-foreground text-xs font-semibold uppercase">Python in sandbox</h3>
      <CodeBlock
        code={py.code}
        language="python"
        title={`${py.status}, exit ${py.exit_code ?? '-'}, ${formatDuration(py.duration_ms)}`}
      />
      {Object.keys(limits).length > 0 && (
        <p className="text-muted-foreground text-xs">
          Limits:{' '}
          {Object.entries(limits)
            .map(([k, v]) => `${humanize(k)} ${formatCell(v)}`)
            .join(', ')}
        </p>
      )}
      {py.stdout && (
        <div>
          <p className="text-muted-foreground mb-1 text-xs">stdout</p>
          <pre className="bg-surface-2 text-foreground max-h-48 overflow-auto rounded-lg border p-3 font-mono text-[11.5px] whitespace-pre-wrap">
            {py.stdout}
          </pre>
        </div>
      )}
      {py.stderr && (
        <div>
          <p className="text-danger mb-1 text-xs">stderr</p>
          <pre className="border-danger/30 bg-danger-soft text-foreground max-h-48 overflow-auto rounded-lg border p-3 font-mono text-[11.5px] whitespace-pre-wrap">
            {py.stderr}
          </pre>
        </div>
      )}
      {py.artifacts.map((a) => (
        <Artifact key={a.file} analysisId={analysisId} pythonId={py.id} file={a.file} title={a.title} />
      ))}
    </section>
  )
}

export function ExecutionDetailSheet({
  analysisId,
  executionId,
  onClose,
}: {
  analysisId: string
  executionId: string | null
  onClose: () => void
}) {
  const detail = useExecution(analysisId, executionId)
  const d = detail.data
  return (
    <Sheet open={Boolean(executionId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-xl lg:max-w-2xl">
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle>Execution {d ? `: ${d.execution.tool}` : ''}</SheetTitle>
          <SheetDescription>Validated SQL, sandboxed code and the rows each tool produced.</SheetDescription>
        </SheetHeader>
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-5 py-5">
          {detail.isPending && executionId && (
            <div className="flex flex-col gap-3" aria-busy="true">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-40" />
              <Skeleton className="h-32" />
            </div>
          )}
          {detail.isError && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
          {d && (
            <>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
                <div>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd className="text-foreground">{d.execution.status}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Attempt</dt>
                  <dd className="text-foreground">{d.execution.attempt}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Duration</dt>
                  <dd className="text-foreground">{formatDuration(d.execution.duration_ms)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Id</dt>
                  <dd className="text-foreground truncate font-mono">{d.execution.id}</dd>
                </div>
              </dl>
              {d.execution.retry_reason && (
                <p className="border-warning/30 bg-warning-soft text-foreground rounded-lg border px-3 py-2 text-xs">
                  Retry reason: {noDashes(d.execution.retry_reason)}
                </p>
              )}
              {d.execution.error && (
                <p className="border-danger/30 bg-danger-soft text-foreground rounded-lg border px-3 py-2 text-xs">
                  {noDashes(d.execution.error)}
                </p>
              )}
              {d.sql.map((s) => (
                <section key={s.id} className="flex flex-col gap-2">
                  <h3 className="text-muted-foreground text-xs font-semibold uppercase">Validated SQL ({s.dialect})</h3>
                  <CodeBlock
                    code={s.sql_executed ?? s.sql_original}
                    language="sql"
                    title={`${s.status}${s.row_count !== null ? `, ${s.row_count} rows` : ''}${s.truncated ? ', truncated' : ''}, ${formatDuration(s.duration_ms)}`}
                  />
                  <p className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-xs">
                    {s.validation?.ok ? (
                      <CheckCircleIcon className="text-brand size-3.5" weight="fill" />
                    ) : (
                      <XCircleIcon className="text-danger size-3.5" weight="fill" />
                    )}
                    {s.validation?.ok ? 'Passed read-only validation' : 'Failed validation'}
                    {s.validation?.statement_type && `, ${s.validation.statement_type}`}
                    {s.validation?.applied_limit !== undefined &&
                      `, row limit ${formatCell(s.validation.applied_limit)}`}
                    {(s.validation?.tables?.length ?? 0) > 0 && `, tables: ${s.validation?.tables?.join(', ')}`}
                  </p>
                  {(s.validation?.errors ?? []).map((e, i) => (
                    <p key={i} className="text-danger text-xs">
                      {e}
                    </p>
                  ))}
                  {s.error && <p className="text-danger text-xs">{s.error}</p>}
                </section>
              ))}
              {d.python.map((py) => (
                <PythonSection key={py.id} py={py} analysisId={analysisId} />
              ))}
              {d.results.map((r) => (
                <section key={r.id} className="flex flex-col gap-2">
                  <h3 className="text-muted-foreground text-xs font-semibold uppercase">Result: {noDashes(r.name)}</h3>
                  <p className="text-muted-foreground text-xs">
                    {r.row_count} rows{r.truncated ? ', truncated' : ''}
                  </p>
                  <DataTable columns={r.columns} rows={r.rows} caption={r.name} />
                </section>
              ))}
              {d.sql.length === 0 && d.python.length === 0 && d.results.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  This tool did not run SQL or Python directly. Its input and output are recorded below.
                </p>
              )}
              <CodeBlock
                code={JSON.stringify(d.execution.input, null, 2)}
                language="text"
                title="Tool input"
                maxCollapsedLines={12}
              />
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
