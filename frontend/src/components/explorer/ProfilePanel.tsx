import { WarningIcon } from '@phosphor-icons/react'
import type { Column, Table } from '@/api/types'
import { StatTile } from '@/components/common/Stat'
import { formatCell, formatInteger, formatNumber, formatPercent, humanize } from '@/lib/format'
import { cn } from '@/lib/utils'

const NUMERIC = new Set(['integer', 'float', 'number', 'decimal'])

function MissingBar({ pct }: { pct: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="bg-muted h-1 w-16 overflow-hidden rounded-xs" aria-hidden="true">
        <span
          className={cn('block h-full', pct > 20 ? 'bg-warning' : 'bg-chart-3')}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </span>
      <span className="tabular">{formatPercent(pct, 1, true)}</span>
    </span>
  )
}

function ColumnProfile({ column }: { column: Column }) {
  const s = column.stats
  const numeric = NUMERIC.has(column.inferred_type)
  const top = s.top_values ?? []
  const maxCount = Math.max(1, ...top.map((t) => t.count))
  const rows: [string, string][] = [
    ['Distinct', formatInteger(s.distinct_count)],
    ['Nulls', formatInteger(s.null_count)],
  ]
  if (numeric) {
    rows.push(
      ['Min', formatNumber(s.min)],
      ['Max', formatNumber(s.max)],
      ['Mean', formatNumber(s.mean)],
      ['Median', formatNumber(s.median)],
      ['Std dev', formatNumber(s.std)],
    )
    if (s.outlier_count_iqr !== undefined) rows.push(['Outliers (IQR)', formatInteger(s.outlier_count_iqr)])
  } else if (column.inferred_type === 'date' || column.inferred_type === 'datetime') {
    rows.push(['From', formatCell(s.min)], ['To', formatCell(s.max)])
    if (s.granularity) rows.push(['Granularity', s.granularity])
  }
  return (
    <article className="bg-card flex flex-col gap-3 rounded-lg border p-4" data-testid="column-profile">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="text-foreground truncate font-mono text-sm font-medium">{column.name}</h4>
          <p className="text-muted-foreground text-xs">
            {column.inferred_type}, {column.role}
          </p>
        </div>
        <div className="text-muted-foreground text-right text-xs">
          <p>Missing</p>
          <MissingBar pct={s.missing_pct ?? 0} />
        </div>
      </header>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="tabular text-foreground truncate font-mono">{v}</dd>
          </div>
        ))}
      </dl>
      {!numeric && top.length > 0 && (
        <div>
          <p className="text-muted-foreground mb-1 text-[11px]">Top values</p>
          <ul className="flex flex-col gap-1">
            {top.slice(0, 5).map((t) => (
              <li key={String(t.value)} className="grid grid-cols-[1fr_auto] items-center gap-2 text-xs">
                <span className="relative truncate">
                  <span
                    className="bg-chart-1/15 absolute inset-y-0 left-0 rounded-xs"
                    style={{ width: `${(t.count / maxCount) * 100}%` }}
                    aria-hidden="true"
                  />
                  <span className="text-foreground relative px-1">{formatCell(t.value)}</span>
                </span>
                <span className="tabular text-muted-foreground">{formatInteger(t.count)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(s.flags?.length ?? 0) > 0 && <p className="text-warning text-[11px]">{s.flags?.map(humanize).join(', ')}</p>}
    </article>
  )
}

export function ProfilePanel({ table }: { table: Table }) {
  const p = table.profile
  const warnings = p.warnings ?? []
  return (
    <div className="flex flex-col gap-5" data-testid="profile-panel">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Rows" value={formatInteger(p.row_count ?? table.row_count)} />
        <StatTile label="Columns" value={formatInteger(p.column_count ?? table.column_count)} />
        <StatTile label="Duplicate rows" value={formatInteger(p.duplicate_rows ?? 0)} />
        <StatTile label="Missing cells" value={formatPercent(p.missing_cells_pct ?? 0, 1, true)} />
      </div>
      {warnings.length > 0 && (
        <div className="border-warning/30 bg-warning-soft rounded-lg border p-3" role="status">
          <p className="text-foreground flex items-center gap-1.5 text-sm font-medium">
            <WarningIcon className="text-warning size-4" weight="fill" />
            Data quality warnings
          </p>
          <ul className="text-foreground/90 mt-1 list-disc pl-6 text-sm">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {[...table.columns]
          .sort((a, b) => a.ordinal - b.ordinal)
          .map((c) => (
            <ColumnProfile key={c.id} column={c} />
          ))}
      </div>
    </div>
  )
}
