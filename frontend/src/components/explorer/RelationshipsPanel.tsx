import { GitForkIcon, KeyIcon, SealCheckIcon } from '@phosphor-icons/react'
import type { DataSource, Relationship } from '@/api/types'
import { sourceRelationships } from '@/lib/relationships'
import { EmptyState } from '@/components/common/States'
import { Pill } from '@/components/common/StatusBadge'
import { formatPercent } from '@/lib/format'

function ColumnRef({ table, column }: { table: string; column: string }) {
  return (
    <span className="text-foreground font-mono text-xs break-all">
      {table}
      <span className="text-muted-foreground">.</span>
      {column}
    </span>
  )
}

function RelationshipRow({ rel }: { rel: Relationship }) {
  const declared = rel.source === 'declared'
  const label = `${rel.child_table}.${rel.child_column} references ${rel.parent_table}.${rel.parent_column}`
  return (
    <li
      className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:gap-4 sm:px-4"
      data-testid="relationship"
      aria-label={label}
    >
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2" aria-hidden="true">
        <ColumnRef table={rel.child_table} column={rel.child_column} />
        <span className="text-muted-foreground font-mono text-xs">-&gt;</span>
        <ColumnRef table={rel.parent_table} column={rel.parent_column} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {declared ? (
          <Pill tone="success" icon={<SealCheckIcon weight="fill" />}>
            Declared foreign key
          </Pill>
        ) : (
          <Pill tone="neutral" icon={<KeyIcon />}>
            Inferred
          </Pill>
        )}
        <span className="text-muted-foreground text-xs">
          <span className="tabular text-foreground font-mono">{formatPercent(rel.containment, 0)}</span> of values match
          {rel.sampled ? ', from a sample' : ''}
        </span>
      </div>
    </li>
  )
}

/** Detected join keys between this source's tables, as the agent sees them when it writes JOINs. */
export function RelationshipsPanel({ source }: { source: DataSource }) {
  const rels = sourceRelationships(source)
  if (rels.length === 0) {
    return (
      <EmptyState
        icon={<GitForkIcon className="size-4" />}
        title="No join keys detected"
        description={
          source.table_count > 1
            ? 'No column pair passed the checks: a key must be unique in the parent table and contain at least 90 percent of the child values. The analyst will not join these tables on a guess.'
            : 'This source has a single table, so there is nothing to join. Upload a workbook with several sheets or connect a database to see relationships.'
        }
      />
    )
  }
  const declared = rels.filter((r) => r.source === 'declared').length
  return (
    <section className="flex flex-col gap-3" aria-labelledby="rels-title" data-testid="relationships-panel">
      <div>
        <h2 id="rels-title" className="text-foreground text-sm font-medium">
          Join keys
        </h2>
        <p className="text-muted-foreground mt-0.5 max-w-2xl text-sm">
          {rels.length} {rels.length === 1 ? 'relationship' : 'relationships'}, {declared} declared by the database and{' '}
          {rels.length - declared} inferred from the data. Inferred keys are accepted only when the parent column is
          unique and most child values exist in it. The analyst uses these to write correct JOINs.
        </p>
      </div>
      <ul className="bg-card divide-y rounded-lg border">
        {rels.map((rel) => (
          <RelationshipRow
            key={`${rel.child_table}.${rel.child_column}>${rel.parent_table}.${rel.parent_column}`}
            rel={rel}
          />
        ))}
      </ul>
    </section>
  )
}
