import { ShieldWarningIcon } from '@phosphor-icons/react'
import type { Table } from '@/api/types'
import { ConfidenceBar } from '@/components/common/ConfidenceBar'
import { Pill } from '@/components/common/StatusBadge'
import { ColumnEditor } from './ColumnEditor'

export function SchemaGrid({ sourceId, table }: { sourceId: string; table: Table }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[760px] text-left text-sm">
        <caption className="sr-only">Schema of {table.display_name}</caption>
        <thead className="bg-surface-2 text-muted-foreground text-xs">
          <tr>
            {['Column', 'Original name', 'Type', 'Role', 'Semantic type', 'Confidence', 'PII', ''].map((h, i) => (
              <th key={i} scope="col" className="border-b px-3 py-2 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...table.columns]
            .sort((a, b) => a.ordinal - b.ordinal)
            .map((c) => (
              <tr key={c.id} className="hover:bg-muted/30 border-b last:border-b-0">
                <td className="text-foreground px-3 py-2 font-mono text-xs font-medium">{c.name}</td>
                <td className="text-muted-foreground max-w-48 truncate px-3 py-2 text-xs" title={c.original_name}>
                  {c.original_name}
                </td>
                <td className="text-foreground px-3 py-2 text-xs">
                  {c.inferred_type}
                  <span className="text-muted-foreground ml-1">({c.physical_type})</span>
                </td>
                <td className="text-foreground px-3 py-2 text-xs">{c.role}</td>
                <td className="text-foreground px-3 py-2 text-xs">
                  {c.semantic_type ?? <span className="text-muted-foreground">unknown</span>}
                  {c.semantic_source === 'user' && <span className="text-brand-text ml-1 text-[10.5px]">edited</span>}
                </td>
                <td className="px-3 py-2">
                  <ConfidenceBar value={c.semantic_confidence} />
                </td>
                <td className="px-3 py-2">
                  {c.is_pii ? (
                    <Pill tone="warning" icon={<ShieldWarningIcon weight="fill" />}>
                      PII
                    </Pill>
                  ) : (
                    <span className="text-muted-foreground text-xs">No</span>
                  )}
                </td>
                <td className="px-2 py-2 text-right">
                  <ColumnEditor sourceId={sourceId} column={c} />
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  )
}
