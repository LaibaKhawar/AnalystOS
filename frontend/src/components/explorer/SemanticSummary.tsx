import type { SemanticEntry, Table } from '@/api/types'
import { ConfidenceBar } from '@/components/common/ConfidenceBar'

const GROUPS: { key: 'metrics' | 'dimensions' | 'time' | 'identifiers' | 'text'; title: string; hint: string }[] = [
  { key: 'metrics', title: 'Metrics', hint: 'Numbers the analyst can sum, average or compare.' },
  { key: 'dimensions', title: 'Dimensions', hint: 'Categories to group and segment by.' },
  { key: 'time', title: 'Time', hint: 'Columns used for periods and trends.' },
  { key: 'identifiers', title: 'Identifiers', hint: 'Keys, never aggregated as numbers.' },
  { key: 'text', title: 'Free text', hint: 'Descriptions and notes.' },
]

export function SemanticSummary({ table }: { table: Table }) {
  const sem = table.semantic
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {GROUPS.map((g) => {
          const entries = (sem[g.key] as SemanticEntry[] | undefined) ?? []
          if (g.key === 'text' && entries.length === 0) return null
          return (
            <section key={g.key} className="bg-card rounded-lg border p-4">
              <h4 className="text-foreground text-sm font-medium">{g.title}</h4>
              <p className="text-muted-foreground text-xs">{g.hint}</p>
              {entries.length === 0 ? (
                <p className="text-muted-foreground mt-3 text-xs">None detected.</p>
              ) : (
                <ul className="mt-3 flex flex-col gap-1.5">
                  {entries.map((e) => (
                    <li key={e.column} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="min-w-0">
                        <span className="text-foreground font-mono">{e.column}</span>
                        {e.semantic_type && <span className="text-muted-foreground ml-2">{e.semantic_type}</span>}
                      </span>
                      {typeof e.confidence === 'number' && <ConfidenceBar value={e.confidence} />}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )
        })}
      </div>
      {((sem.pii_columns?.length ?? 0) > 0 || (sem.uncertain_columns?.length ?? 0) > 0) && (
        <div className="bg-muted/30 rounded-lg border p-4 text-sm">
          {(sem.pii_columns?.length ?? 0) > 0 && (
            <p className="text-foreground">
              PII columns: <span className="font-mono">{sem.pii_columns?.join(', ')}</span>
            </p>
          )}
          {(sem.uncertain_columns?.length ?? 0) > 0 && (
            <p className="text-muted-foreground mt-1">
              Uncertain meaning, worth confirming in the schema tab:{' '}
              <span className="text-foreground font-mono">{sem.uncertain_columns?.join(', ')}</span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
