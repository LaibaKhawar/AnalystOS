import { DownloadSimpleIcon, WarningIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { downloadFile, errorMessage } from '@/api/client'
import { analysesApi } from '@/api/endpoints'
import type { ClaimEvidence, EvidenceItem } from '@/api/types'
import { DataTable } from '@/components/common/DataTable'
import { Pill } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { CodeBlock } from '@/components/ui/code-block'
import { claimBadge } from '@/lib/claims'
import { formatCell, formatDateTime, formatDuration, humanize, noDashes } from '@/lib/format'

const SOURCE_LABEL: Record<string, string> = {
  sql_query: 'SQL query',
  python: 'Python (sandboxed)',
  derived: 'Derived calculation',
  statistics: 'Statistics',
  metadata: 'Dataset metadata',
}

function ValuesTable({ values }: { values: Record<string, unknown> }) {
  const entries = Object.entries(values)
  if (entries.length === 0) return null
  return (
    <dl className="bg-surface-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border px-3 py-2 text-xs">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="tabular text-foreground truncate text-right font-mono">{formatCell(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

function DownloadCsv({ analysisId, resultId }: { analysisId: string; resultId: string }) {
  const [state, setState] = useState<{ pending: boolean; error: string | null }>({ pending: false, error: null })
  const download = async () => {
    setState({ pending: true, error: null })
    try {
      await downloadFile(analysesApi.resultCsvPath(analysisId, resultId), `${resultId}.csv`)
      setState({ pending: false, error: null })
    } catch (error) {
      setState({ pending: false, error: errorMessage(error) })
    }
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="outline" size="sm" onClick={download} disabled={state.pending}>
        <DownloadSimpleIcon data-icon="inline-start" />
        {state.pending ? 'Preparing CSV' : 'Download result CSV'}
      </Button>
      {state.error && <p className="text-danger text-xs">{state.error}</p>}
    </div>
  )
}

function EvidenceCard({
  item,
  analysisId,
  index,
  preview,
}: {
  item: EvidenceItem
  analysisId: string
  index: number
  preview: boolean
}) {
  return (
    <article className="bg-card flex flex-col gap-3 rounded-lg border p-4" data-testid="evidence-item">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-muted-foreground text-xs">Evidence {index + 1}</p>
          <p className="text-foreground mt-0.5 text-sm font-medium">
            {item.finding ? (
              <>
                <span className="text-brand-text mr-1.5 font-mono">{item.finding.label}</span>
                {noDashes(item.finding.statement)}
              </>
            ) : (
              noDashes(item.description ?? 'Computed value')
            )}
          </p>
        </div>
        <Pill tone="brand">{SOURCE_LABEL[item.source_type] ?? humanize(item.source_type)}</Pill>
      </header>

      <ValuesTable values={item.values} />

      {item.formula && (
        <div className="text-xs">
          <p className="text-muted-foreground mb-1">Formula</p>
          <code className="bg-surface-2 text-foreground block rounded-lg border px-3 py-2 font-mono break-words">
            {item.formula}
          </code>
        </div>
      )}

      {item.sql.map((sql) => (
        <CodeBlock
          key={sql.id}
          code={sql.sql}
          language="sql"
          title={`${sql.status}${sql.row_count !== null ? `, ${sql.row_count} rows` : ''}${sql.duration_ms !== null ? `, ${formatDuration(sql.duration_ms)}` : ''}`}
        />
      ))}
      {item.python.map((py) => (
        <CodeBlock key={py.id} code={py.code} language="python" title={`${py.status}, sandboxed`} />
      ))}

      {item.result && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="text-foreground text-xs font-medium">{noDashes(item.result.name)}</p>
              <p className="text-muted-foreground text-[11px]">
                {item.result.row_count} rows{item.result.truncated ? ', truncated' : ''}
                {item.result.rows.length < item.result.row_count ? `, first ${item.result.rows.length} shown` : ''}
              </p>
            </div>
            {!preview && <DownloadCsv analysisId={analysisId} resultId={item.result.id} />}
          </div>
          <DataTable
            columns={item.result.columns}
            rows={item.result.rows}
            maxRows={100}
            caption={item.result.name}
            maxHeight="max-h-64"
          />
        </div>
      )}

      {item.execution && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 border-t pt-3 text-[11px] sm:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">Execution</dt>
            <dd className="text-foreground truncate font-mono" title={item.execution.id}>
              {item.execution.id}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Tool</dt>
            <dd className="text-foreground truncate">{item.execution.tool}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Status</dt>
            <dd className="text-foreground">
              {item.execution.status}, attempt {item.execution.attempt}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Ran at</dt>
            <dd className="text-foreground">{formatDateTime(item.execution.created_at)}</dd>
          </div>
        </dl>
      )}
    </article>
  )
}

export function EvidenceContent({
  data,
  analysisId,
  preview = false,
}: {
  data: ClaimEvidence
  analysisId: string
  preview?: boolean
}) {
  const { claim, evidence } = data
  const badge = claimBadge(claim.status)
  const notes = claim.verification?.notes ?? []
  const unsupported = claim.verification?.unsupported ?? []
  const matches = claim.verification?.matches ?? []
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={badge.tone}>{badge.label}</Pill>
          <span className="text-muted-foreground text-xs">
            {humanize(claim.kind)}, {claim.section}
          </span>
        </div>
        <blockquote
          className="border-brand text-foreground border-l-2 pl-3 text-[15px] leading-relaxed"
          data-testid="evidence-claim-text"
        >
          {noDashes(claim.text)}
        </blockquote>
        {claim.original_text && claim.original_text !== claim.text && (
          <p className="text-muted-foreground text-xs">
            Rewritten after verification. Original draft: {noDashes(claim.original_text)}
          </p>
        )}
      </section>

      {matches.length > 0 && (
        <section>
          <h3 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">Number checks</h3>
          <ul className="flex flex-col gap-1.5 text-xs">
            {matches.map((m, i) => (
              <li
                key={`${m.token}-${i}`}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border px-3 py-2"
              >
                <span className="text-foreground font-mono font-medium">{m.token}</span>
                <span className="text-muted-foreground">matched</span>
                <span className="text-brand-text font-mono">{m.finding_label}</span>
                {m.value_key && (
                  <span className="text-muted-foreground">
                    ({m.value_key} = {formatCell(m.value)})
                  </span>
                )}
                {m.derived_formula && (
                  <span className="text-muted-foreground w-full font-mono">{m.derived_formula}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(notes.length > 0 || unsupported.length > 0) && (
        <section className="flex flex-col gap-2">
          {unsupported.length > 0 && (
            <div className="border-warning/30 bg-warning-soft text-foreground flex items-start gap-2 rounded-lg border px-3 py-2 text-xs">
              <WarningIcon className="text-warning mt-0.5 size-3.5 shrink-0" weight="fill" />
              <span>Unsupported numbers: {unsupported.join(', ')}</span>
            </div>
          )}
          {notes.length > 0 && (
            <ul className="text-muted-foreground list-disc pl-5 text-xs">
              {notes.map((note, i) => (
                <li key={i}>{noDashes(note)}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="flex flex-col gap-3">
        <h3 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Evidence</h3>
        {evidence.length === 0 ? (
          <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-4 text-sm">
            {claim.status === 'no_numbers'
              ? 'This statement contains no numbers, so there is nothing to trace. It is shown as context, not as a computed fact.'
              : 'No evidence items are attached to this statement.'}
          </p>
        ) : (
          evidence.map((item, i) => (
            <EvidenceCard key={item.id} item={item} analysisId={analysisId} index={i} preview={preview} />
          ))
        )}
      </section>
    </div>
  )
}
